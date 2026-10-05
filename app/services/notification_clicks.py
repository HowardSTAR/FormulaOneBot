"""First-party attribution of broadcast callbacks and destination-page arrivals."""
import hashlib
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosqlite

from app.db import db

logger = logging.getLogger(__name__)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS notification_button_links (
 token TEXT PRIMARY KEY, campaign TEXT NOT NULL, source_key TEXT NOT NULL,
 channel TEXT NOT NULL, button TEXT NOT NULL, destination TEXT NOT NULL,
 caption TEXT NOT NULL, created REAL NOT NULL,
 UNIQUE(source_key,channel,button)
);
CREATE TABLE IF NOT EXISTS notification_button_events (
 event_id TEXT PRIMARY KEY, token TEXT NOT NULL REFERENCES notification_button_links(token),
 viewer TEXT NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notification_button_events_created ON notification_button_events(created);
CREATE INDEX IF NOT EXISTS idx_notification_button_events_token ON notification_button_events(token,created);
CREATE INDEX IF NOT EXISTS idx_notification_button_events_viewer ON notification_button_events(viewer,created);
'''
LABELS = {'leaderboard': 'Таблица прогнозов', 'review': 'Мой разбор',
          'leagues': 'Мои лиги', 'community': 'С друзьями · итоги и новый заезд'}


def campaign_info(key):
    match = re.fullmatch(r'weekly-race:(\d{4}-\d{2}-\d{2})', key)
    if match:
        return key, f'Заезд недели · {match[1]}'
    normalized = re.sub(r'^prediction-results(-updated)?:',
                        lambda match: 'prediction:results-updated:' if match[1] else 'prediction:results:', key)
    match = re.fullmatch(r'prediction:(results|results-updated|results-manual):(\d{4}):(\d{1,2})(?::[a-f0-9]{64})?', normalized)
    if match:
        kind, season, round_num = match.groups()
        label = {'results': 'Итоги прогнозов', 'results-updated': 'Обновлённые итоги',
                 'results-manual': 'Ручная рассылка итогов'}[kind]
        return normalized, f'{label} · {season}, этап {round_num}'
    return None


async def register(conn, source_key, channel, button, destination):
    info = campaign_info(source_key)
    if not info or button not in LABELS:
        return None
    await conn.execute(
        'INSERT OR IGNORE INTO notification_button_links VALUES(?,?,?,?,?,?,?,?)',
        (secrets.token_urlsafe(24), info[0], source_key, channel, button, destination, info[1], time.time()),
    )
    row = await (await conn.execute(
        'SELECT token FROM notification_button_links WHERE source_key=? AND channel=? AND button=?',
        (source_key, channel, button),
    )).fetchone()
    return row['token']


def destination_button(url):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if parts.path == '/predictions' and query.get('tab') == 'leaderboard':
        return 'leaderboard'
    if parts.path == '/community' and query.get('weekly') == 'previous':
        return 'community'
    return None


async def tracked_url(conn, source_key, url, channel):
    button = destination_button(url)
    if not button:
        return url
    parts = urlsplit(url)
    token = await register(conn, source_key, channel, button, parts.path)
    if not token:
        return url
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'nb']
    query.append(('nb', token))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def tracked_keyboard(conn, source_key, keyboard):
    if not keyboard or not campaign_info(source_key):
        return keyboard
    keyboard = keyboard.model_copy(deep=True)
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.web_app:
                url = await tracked_url(conn, source_key, button.web_app.url, 'telegram')
                button.web_app = button.web_app.model_copy(update={'url': url})
            elif button.callback_data:
                match = re.fullmatch(r'personal:(review|leagues):\d{4}:\d{1,2}', button.callback_data)
                if match:
                    await register(conn, source_key, 'telegram', match[1], '/predictions')
    return keyboard


async def record(conn, token, event_id, visitor, user_id):
    now = time.time()
    viewer = viewer_key(visitor, user_id)
    cursor = await conn.execute(
        'INSERT OR IGNORE INTO notification_button_events VALUES(?,?,?,?,?)',
        (event_id, token, viewer, user_id, now),
    )
    await conn.execute('DELETE FROM notification_button_events WHERE created<?', (now - 366*86400,))
    return bool(cursor.rowcount)


def viewer_key(visitor, user_id):
    return hashlib.sha256(('notification:' + (f'user:{user_id}' if user_id else f'visitor:{visitor}')).encode()).hexdigest()


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path, timeout=1) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        yield conn


async def record_callback(callback, kind, user_id):
    """Identify the actual broadcast message; replayed callback IDs count once."""
    try:
        async with connection() as conn:
            batch = await (await conn.execute(
                '''SELECT event_key FROM telegram_deliveries WHERE telegram_id=? AND message_id=?
                   AND status='sent' ORDER BY updated DESC LIMIT 1''',
                (callback.message.chat.id, callback.message.message_id),
            )).fetchone()
            if not batch:
                return
            token = await register(conn, batch['event_key'], 'telegram', kind, '/predictions')
            if token:
                await record(conn, token, 'telegram:' + callback.id, str(callback.from_user.id), user_id)
                await conn.commit()
    except Exception:
        logger.warning('Could not record broadcast button callback', exc_info=True)


async def report(conn, since):
    rows = await (await conn.execute(
        '''SELECT l.campaign,l.caption,l.channel,l.button,MIN(l.created) sent_at,
                  COUNT(e.event_id) clicks,COUNT(DISTINCT e.viewer) unique_users
           FROM notification_button_links l LEFT JOIN notification_button_events e
             ON e.token=l.token AND e.created>=?
           WHERE l.created>=? OR EXISTS(
             SELECT 1 FROM notification_button_events recent WHERE recent.token=l.token AND recent.created>=?)
           GROUP BY l.campaign,l.caption,l.channel,l.button ORDER BY sent_at DESC,l.channel,l.button LIMIT 200''',
        (since, since, since),
    )).fetchall()
    summary = await (await conn.execute(
        '''SELECT COUNT(*) interactions,COUNT(DISTINCT e.viewer) unique_users,
           COALESCE(SUM(l.button IN ('review','leagues')),0) callbacks,
           COALESCE(SUM(l.button IN ('leaderboard','community')),0) arrivals
           FROM notification_button_events e JOIN notification_button_links l ON l.token=e.token
           WHERE e.created>=?''', (since,),
    )).fetchone()
    first = (await (await conn.execute('SELECT MIN(created) FROM notification_button_links')).fetchone())[0]
    return {'summary': dict(summary), 'first_tracked': first,
            'items': [{**dict(row), 'label': LABELS[row['button']],
                       'metric': 'callback' if row['button'] in ('review', 'leagues') else 'arrival'} for row in rows]}
