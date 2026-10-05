"""Transactional weekly rank changes; coalesced, restart-safe delivery."""
import html
import time
from datetime import datetime, timezone

from app.db import db
from app.services.engagement import weekly_period, time_label

SCHEMA = '''
CREATE TABLE IF NOT EXISTS weekly_race_overtakes (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 score_id INTEGER NOT NULL REFERENCES race_game_scores(id) ON DELETE CASCADE,
 week TEXT NOT NULL, track_id TEXT NOT NULL, previous_time INTEGER NOT NULL,
 created REAL NOT NULL, expires REAL NOT NULL, processed INTEGER NOT NULL DEFAULT 0,
 UNIQUE(user_id,score_id)
);
CREATE INDEX IF NOT EXISTS weekly_race_overtakes_pending ON weekly_race_overtakes(processed,expires);
CREATE TABLE IF NOT EXISTS weekly_race_alert_cooldowns (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 week TEXT NOT NULL, sent_at REAL NOT NULL, PRIMARY KEY(user_id,week)
);
'''
COOLDOWN = 3600
TITLE = 'Твоё время в заезде недели обошли'


async def record_overtakes(conn, score_id):
    """Run inside the score's write transaction, never from a retrospective scan."""
    score = await (await conn.execute('SELECT * FROM race_game_scores WHERE id=?', (score_id,))).fetchone()
    now = datetime.fromisoformat(score['created_at'].replace('Z', '+00:00'))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    track, start, end = weekly_period(now)
    if score['track_id'] != track['id']:
        return
    challenger = await (await conn.execute('SELECT display_name FROM reaction_leaderboard_profiles WHERE telegram_id=? AND leaderboard_opt_in=1', (score['telegram_id'],))).fetchone()
    if not challenger:
        return
    params = (track['id'], start.isoformat(), end.isoformat(), score_id)
    previous = await (await conn.execute('''SELECT s.telegram_id,MIN(s.time_ms) time_ms
        FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id)
        WHERE p.leaderboard_opt_in=1 AND s.track_id=? AND datetime(s.created_at)>=datetime(?)
        AND datetime(s.created_at)<datetime(?) AND s.id<>? GROUP BY s.telegram_id''', params)).fetchall()
    own = next((row['time_ms'] for row in previous if row['telegram_id'] == score['telegram_id']), None)
    if own is not None and score['time_ms'] >= own:
        return
    # Equal times share a place. Only a genuine crossing creates an event.
    for rival in previous:
        if rival['telegram_id'] == score['telegram_id'] or not score['time_ms'] < rival['time_ms']:
            continue
        if own is not None and own < rival['time_ms']:
            continue
        user = await (await conn.execute('SELECT id FROM users WHERE telegram_id=? AND archived_at IS NULL', (rival['telegram_id'],))).fetchone()
        if not user:
            continue
        cursor = await conn.execute('''INSERT OR IGNORE INTO weekly_race_overtakes
            (user_id,score_id,week,track_id,previous_time,created,expires) VALUES(?,?,?,?,?,?,?)''',
            (user['id'],score_id,start.date().isoformat(),track['id'],rival['time_ms'],now.timestamp(),end.timestamp()))
        if not cursor.rowcount:
            continue
        # Personal participation alerts also appear before the first inbox visit.
        key = f"weekly-overtaken:{start.date().isoformat()}:{user['id']}"
        text = f"{challenger['display_name']} — {time_label(score['time_ms'])}. Твоё время: {time_label(rival['time_ms'])}. Попробуй перебить его!"
        url = f"/race-game?track={track['id']}&weekly=1"
        await conn.execute('''INSERT INTO web_notifications(user_id,event_key,title,body,url,created_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,event_key) DO UPDATE SET
            body=excluded.body,url=excluded.url,created_at=excluded.created_at,read_at=NULL''',
            (user['id'],key,TITLE,text,url,now.timestamp()))
        notification = await (await conn.execute('SELECT id FROM web_notifications WHERE user_id=? AND event_key=?', (user['id'],key))).fetchone()
        await conn.execute('''INSERT INTO web_notification_expirations VALUES(?,?)
            ON CONFLICT(notification_id) DO UPDATE SET expires=excluded.expires''', (notification['id'],end.timestamp()))


async def active_event(conn, event_id, *, now=None):
    now = time.time() if now is None else now
    event = await (await conn.execute('''SELECT e.*,s.telegram_id challenger,s.time_ms,
        u.telegram_id recipient,u.timezone,p.display_name FROM weekly_race_overtakes e
        JOIN users u ON u.id=e.user_id AND u.archived_at IS NULL
        JOIN race_game_scores s ON s.id=e.score_id
        JOIN reaction_leaderboard_profiles p ON p.telegram_id=s.telegram_id AND p.leaderboard_opt_in=1
        JOIN reaction_leaderboard_profiles mine ON mine.telegram_id=u.telegram_id AND mine.leaderboard_opt_in=1
        WHERE e.id=? AND e.expires>?''', (event_id,now))).fetchone()
    if not event:
        return None
    best = await (await conn.execute('''SELECT MIN(time_ms) FROM race_game_scores WHERE telegram_id=?
        AND track_id=? AND datetime(created_at)>=datetime(?) AND datetime(created_at)<datetime(?)''',
        (event['recipient'],event['track_id'],event['week'],datetime.fromtimestamp(event['expires'],timezone.utc).isoformat()))).fetchone()
    return dict(event) if best[0] is not None and best[0] > event['time_ms'] else None


async def personal_weekly(user_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    track, start, end = weekly_period(now)
    async with db.write_lock:
        user = await (await db.conn.execute('SELECT telegram_id FROM users WHERE id=? AND archived_at IS NULL', (user_id,))).fetchone()
        if not user or not user['telegram_id']:
            return None
        rows = await (await db.conn.execute('''SELECT s.telegram_id,p.display_name,MIN(s.time_ms) time_ms
            FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id)
            WHERE p.leaderboard_opt_in=1 AND s.track_id=? AND datetime(s.created_at)>=datetime(?)
            AND datetime(s.created_at)<datetime(?) GROUP BY s.telegram_id,p.display_name ORDER BY time_ms,s.telegram_id''',
            (track['id'],start.isoformat(),end.isoformat()))).fetchall()
        me = next((row for row in rows if row['telegram_id']==user['telegram_id']),None)
        if not me:
            return None
        event = await (await db.conn.execute('''SELECT MAX(e.id) FROM weekly_race_overtakes e
            JOIN race_game_scores s ON s.id=e.score_id
            JOIN reaction_leaderboard_profiles p ON p.telegram_id=s.telegram_id AND p.leaderboard_opt_in=1
            WHERE e.user_id=? AND e.week=? AND e.expires>? AND s.time_ms<?''',
            (user_id,start.date().isoformat(),now.timestamp(),me['time_ms']))).fetchone()
    faster = [row for row in rows if row['time_ms'] < me['time_ms']]
    return {'week':start.date().isoformat(), 'end':end.isoformat(),'track_id':track['id'],'name':track['name'],
            'time_ms':me['time_ms'],'place':len(faster)+1,'alert_id':event[0] if faster else None,
            'rival':{'name':faster[0]['display_name'],'time_ms':faster[0]['time_ms']} if faster else None}


async def dispatch_overtakes(bot, *, now=None):
    from app.services.telegram_outbox import connection, drain
    from app.utils.mini_app_links import mini_app_button
    current = time.time() if now is None else now.timestamp()
    async with connection() as conn:
        due = await (await conn.execute('''SELECT 1 FROM weekly_race_overtakes e
            LEFT JOIN weekly_race_alert_cooldowns c USING(user_id,week)
            WHERE e.processed=0 AND e.expires>? AND (c.sent_at IS NULL OR c.sent_at<=?) LIMIT 1''',
            (current,current-COOLDOWN))).fetchone()
    if not due:
        return
    # Resolve the destination before acquiring SQLite's writer lock.
    track, _, _ = weekly_period(datetime.fromtimestamp(current,timezone.utc))
    keyboard = await mini_app_button(bot, 'Попробовать перебить →', '/race-game', track=track['id'],weekly=1)
    if keyboard is None:
        return
    async with connection() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        events = await (await conn.execute('''SELECT e.id,e.user_id,e.week FROM weekly_race_overtakes e
            LEFT JOIN weekly_race_alert_cooldowns c USING(user_id,week)
            WHERE e.processed=0 AND e.expires>? AND (c.sent_at IS NULL OR c.sent_at<=?)
            ORDER BY e.created,e.id LIMIT 100''',(current,current-COOLDOWN))).fetchall()
        handled = set()
        for row in events:
            pair = (row['user_id'],row['week'])
            if pair in handled:
                continue
            handled.add(pair)
            pending = await (await conn.execute('SELECT id FROM weekly_race_overtakes WHERE user_id=? AND week=? AND processed=0 ORDER BY id DESC',pair)).fetchall()
            active = [event for item in pending if (event := await active_event(conn,item['id'],now=current))]
            if active:
                event = min(active,key=lambda e:e['time_ms'])
                key = f"weekly-overtake:{event['id']}"
                text = (f"🏎 <b>{TITLE}</b>\n{html.escape(event['display_name'])} — <b>{time_label(event['time_ms'])}</b>.\n"
                        'Попробуй перебить его! До конца недели ещё можно улучшить результат.')
                await conn.execute('INSERT OR IGNORE INTO telegram_delivery_batches VALUES(?,?,?,?,?)',
                    (key,text,keyboard.model_dump_json(exclude_none=True),min(event['expires'],current+COOLDOWN),current))
                await conn.execute('''INSERT OR IGNORE INTO telegram_deliveries
                    (event_key,telegram_id,timezone,updated) VALUES(?,?,?,?)''', (key,event['recipient'],event['timezone'],current))
                await conn.execute('''INSERT INTO weekly_race_alert_cooldowns VALUES(?,?,?)
                    ON CONFLICT(user_id,week) DO UPDATE SET sent_at=excluded.sent_at''',(*pair,current))
            await conn.execute('UPDATE weekly_race_overtakes SET processed=1 WHERE user_id=? AND week=? AND processed=0',pair)
        await conn.execute('UPDATE weekly_race_overtakes SET processed=1 WHERE processed=0 AND expires<=?',(current,))
        await conn.commit()
    await drain(bot,limit=30)
