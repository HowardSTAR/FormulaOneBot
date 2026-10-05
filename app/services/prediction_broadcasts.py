"""Confirmed broadcasts of saved prediction results to Telegram and the web inbox."""
import hashlib
import html
import json
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from app.db import db
from app.services.prediction_notifications import prediction_results_message
from app.utils.mini_app_links import mini_app_button
from app.utils.telegram_presentation import personal_buttons

RESULT_FIELDS = (
    'pole_driver', 'winner_driver', 'second_driver', 'third_driver',
    'fourth_driver', 'fifth_driver', 'fastest_lap_driver',
    'first_retirement_driver', 'safety_car',
)


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        yield conn


async def snapshot(conn, season, round_num):
    actual = await (await conn.execute(
        'SELECT * FROM prediction_round_results WHERE season=? AND round=?',
        (season, round_num),
    )).fetchone()
    if actual is None:
        raise ValueError('Этап ещё не рассчитан. Сначала дождитесь расчёта прогнозов.')
    rows = await (await conn.execute(
        '''SELECT rp.user_id,rp.points,rp.max_points,rp.sprint_pole_driver,
                  rp.sprint_winner_driver,pp.display_name
           FROM race_predictions rp LEFT JOIN prediction_profiles pp ON pp.user_id=rp.user_id
           WHERE rp.season=? AND rp.round=?
           ORDER BY rp.points DESC,rp.updated_at ASC,pp.display_name COLLATE NOCASE,rp.user_id''',
        (season, round_num),
    )).fetchall()
    if any(row['points'] is None or row['max_points'] is None for row in rows):
        raise ValueError('Есть нерассчитанные прогнозы. Сначала завершите расчёт этапа.')
    top = [{**dict(row), 'display_name': row['display_name'] or f"Участник #{row['user_id']}"}
           for row in rows[:3]]
    fields = list(RESULT_FIELDS)
    if any(actual[key] is not None or any(row[key] is not None for row in rows)
           for key in ('sprint_pole_driver', 'sprint_winner_driver')):
        fields.extend(('sprint_pole_driver', 'sprint_winner_driver'))
    provisional = any(actual[key] is None for key in fields)
    event = {'season': season, 'round': round_num, 'event_name': actual['event_name']}
    title, text = prediction_results_message(
        {**event, 'event_name': f"{actual['event_name']} · {season}, этап {round_num}"},
        top, provisional=provisional,
    )
    # Content and every participant's result define a version, never a click or recovery ID.
    version = {'event': event, 'answers': {key: actual[key] for key in fields},
               'results': sorted((dict(row) for row in rows), key=lambda row: row['user_id']),
               'text': text}
    fingerprint = hashlib.sha256(json.dumps(version, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'season': season, 'round': round_num, 'event_name': actual['event_name'],
            'fingerprint': fingerprint, 'title': title, 'text': text,
            'body': html.unescape(re.sub(r'<[^>]*>', '', text)),
            'provisional': provisional, 'participants': len(rows)}


def event_key(result):
    return f"prediction:results-manual:{result['season']}:{result['round']}:{result['fingerprint']}"


async def recipients(conn):
    telegram = await (await conn.execute(
        'SELECT telegram_id,timezone FROM users WHERE telegram_id IS NOT NULL AND archived_at IS NULL',
    )).fetchall()
    web = await (await conn.execute(
        '''SELECT m.user_id FROM web_notification_members m JOIN users u ON u.id=m.user_id
           WHERE u.archived_at IS NULL''',
    )).fetchall()
    return telegram, web


async def counts(conn, key):
    telegram = (await (await conn.execute(
        'SELECT COUNT(*) FROM telegram_deliveries WHERE event_key=?', (key,),
    )).fetchone())[0]
    web = (await (await conn.execute(
        'SELECT COUNT(*) FROM web_notifications WHERE event_key=?', (key,),
    )).fetchone())[0]
    return {'telegram': telegram, 'web': web}


async def preview(season, round_num):
    async with connection() as conn:
        await conn.execute('BEGIN')
        result = await snapshot(conn, season, round_num)
        key = event_key(result)
        sent = await (await conn.execute(
            'SELECT 1 FROM telegram_delivery_batches WHERE event_key=?', (key,),
        )).fetchone()
        if sent:
            audience = await counts(conn, key)
        else:
            telegram, web = await recipients(conn)
            audience = {'telegram': len(telegram), 'web': len(web)}
        return {**result, 'recipients': audience, 'already_sent': bool(sent)}


async def send(season, round_num, fingerprint, actor_id):
    # Configuration-only button lookup: the HTTP handler never sends to Telegram.
    keyboard = await mini_app_button(None, '🏆 Таблица прогнозов', '/predictions',
                                     tab='leaderboard', season=season, round=round_num)
    keyboard = personal_buttons(season, round_num, keyboard)
    now = time.time()
    async with connection() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        result = await snapshot(conn, season, round_num)
        if result['fingerprint'] != fingerprint:
            raise ValueError('Итоги изменились. Обновите предпросмотр перед отправкой.')
        key = event_key(result)
        sent = await (await conn.execute(
            'SELECT 1 FROM telegram_delivery_batches WHERE event_key=?', (key,),
        )).fetchone()
        if sent:
            return {'recipients': await counts(conn, key), 'already_sent': True}
        telegram, web = await recipients(conn)
        if not telegram and not web:
            raise ValueError('Нет доступных получателей в Telegram и вебе.')
        # Both channels and audit commit together into the existing durable queues.
        await conn.execute('INSERT INTO telegram_delivery_batches VALUES(?,?,?,?,?)',
                           (key, result['text'], keyboard.model_dump_json(exclude_none=True), now + 7*86400, now))
        await conn.executemany(
            'INSERT INTO telegram_deliveries(event_key,telegram_id,timezone,updated) VALUES(?,?,?,?)',
            [(key, user['telegram_id'], user['timezone'] or 'Europe/Moscow', now) for user in telegram],
        )
        await conn.execute('INSERT INTO web_notification_events VALUES(?,?)', (key, now))
        for user in web:
            notification = await conn.execute(
                'INSERT INTO web_notifications(user_id,event_key,title,body,url,created_at) VALUES(?,?,?,?,?,?)',
                (user['user_id'], key, result['title'], result['body'],
                 f'/predictions?tab=leaderboard&season={season}&round={round_num}', now),
            )
            await conn.execute(
                '''INSERT INTO web_push_outbox(notification_id,subscription_id,next_attempt)
                   SELECT ?,id,? FROM web_push_subscriptions WHERE user_id=?''',
                (notification.lastrowid, now, user['user_id']),
            )
        audience = {'telegram': len(telegram), 'web': len(web)}
        await conn.execute(
            'INSERT INTO admin_audit_log(actor_user_id,action,details_json,created_at) VALUES(?,?,?,?)',
            (actor_id, 'prediction_results.sent',
             json.dumps({'season': season, 'round': round_num, **audience}),
             datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()
        return {'recipients': audience, 'already_sent': False}
