"""Persistent per-recipient Telegram delivery; ambiguous sends are not replayed."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

import aiosqlite
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.types import InlineKeyboardMarkup

from app.db import db
from app.utils.safe_send import _apply_sound_preference

logger = logging.getLogger(__name__)
SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_delivery_batches (
 event_key TEXT PRIMARY KEY, text TEXT NOT NULL, keyboard TEXT, expires REAL NOT NULL,
 created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS telegram_deliveries (
 event_key TEXT NOT NULL REFERENCES telegram_delivery_batches(event_key),
 telegram_id INTEGER NOT NULL, timezone TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0, updated REAL NOT NULL,
 message_id INTEGER, error TEXT,
 PRIMARY KEY(event_key, telegram_id)
);
CREATE INDEX IF NOT EXISTS idx_telegram_deliveries_due ON telegram_deliveries(status,next_attempt);
CREATE TABLE IF NOT EXISTS delivery_payloads (
 event_key TEXT PRIMARY KEY REFERENCES telegram_delivery_batches(event_key),
 channel TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delivery_progress (
 event_key TEXT NOT NULL, recipient INTEGER NOT NULL, step INTEGER NOT NULL,
 PRIMARY KEY(event_key,recipient)
);
"""


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        await conn.executescript(SCHEMA)
        yield conn


async def enqueue(event_key, text, keyboard, users, expires, *, payload=None, channel='telegram', initial_status='pending'):
    """Freeze payload and audience atomically; retries cannot add recipients."""
    now = time.time()
    async with connection() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        cursor = await conn.execute(
            'INSERT OR IGNORE INTO telegram_delivery_batches VALUES(?,?,?,?,?)',
            (event_key, text, keyboard.model_dump_json(exclude_none=True) if keyboard else None, expires, now))
        if cursor.rowcount:
            if payload is not None:
                await conn.execute('INSERT INTO delivery_payloads VALUES(?,?,?)', (event_key,channel,json.dumps(payload)))
            await conn.executemany(
                'INSERT OR IGNORE INTO telegram_deliveries(event_key,telegram_id,timezone,updated,status) VALUES(?,?,?,?,?)',
                [(event_key, int(user[0]), user[1] or 'Europe/Moscow', now, initial_status) for user in users])
        await conn.commit()


async def delivery_counts(event_key):
    async with connection() as conn:
        rows = await (await conn.execute(
            'SELECT status,COUNT(*) n FROM telegram_deliveries WHERE event_key=? GROUP BY status', (event_key,))).fetchall()
        return {row['status']: row['n'] for row in rows}


async def drain(bot=None, *, event_key=None, limit=50):
    from app.utils.notifications import is_quiet_hours
    for _ in range(limit):
        now = time.time()
        async with connection() as conn:
            await conn.execute('BEGIN IMMEDIATE')
            cooldown = await (await conn.execute("SELECT MAX(next_attempt) FROM telegram_deliveries WHERE error='rate_limited'")).fetchone()
            telegram_ready = not cooldown[0] or cooldown[0] <= now
            # A process might have died after Telegram accepted a message.
            await conn.execute("UPDATE telegram_deliveries SET status='unknown',error='worker_interrupted' WHERE status='sending' AND updated<?", (now-600,))
            await conn.execute("UPDATE telegram_deliveries SET status='expired',updated=? WHERE status IN ('pending','retry') AND event_key IN (SELECT event_key FROM telegram_delivery_batches WHERE expires<=?)", (now, now))
            await conn.execute("UPDATE telegram_deliveries SET status='cancelled',updated=? WHERE status IN ('pending','retry') AND event_key NOT IN (SELECT event_key FROM delivery_payloads WHERE channel='webpush') AND ((telegram_id>0 AND NOT EXISTS (SELECT 1 FROM users u WHERE u.telegram_id=telegram_deliveries.telegram_id AND u.archived_at IS NULL)) OR (telegram_id<0 AND NOT EXISTS (SELECT 1 FROM group_chats g WHERE g.chat_id=telegram_deliveries.telegram_id)))", (now,))
            row = await (await conn.execute(
                "SELECT d.*,b.text,b.keyboard,b.expires,p.channel,p.payload FROM telegram_deliveries d JOIN telegram_delivery_batches b USING(event_key) LEFT JOIN delivery_payloads p USING(event_key) "
                "WHERE d.status IN ('pending','retry') AND d.next_attempt<=? AND (? IS NULL OR d.event_key=?) AND (p.channel='webpush' OR ?) ORDER BY d.next_attempt,d.updated LIMIT 1",
                (now,event_key,event_key,bool(bot is not None and telegram_ready)))).fetchone()
            if row:
                await conn.execute("UPDATE telegram_deliveries SET status='sending',attempts=attempts+1,updated=? WHERE event_key=? AND telegram_id=?", (now,row['event_key'],row['telegram_id']))
            await conn.commit()
        if not row:
            return
        status, error, message_id, retry_at = 'sent', None, None, 0
        try:
            if row['payload']:
                from app.services.delivery_adapters import dispatch
                status, error, message_id, retry_at = await dispatch(bot, dict(row))
            else:
                status, error, message_id, retry_at = await _legacy_text(bot, row)
        except TelegramRetryAfter as exc:
            status = 'retry' if row['attempts'] < 7 else 'failed'
            retry_at = time.time() + max(float(exc.retry_after), min(30 * 2**row['attempts'], 3600))
            error = 'rate_limited'
        except TelegramForbiddenError:
            status, error = 'blocked', 'telegram_forbidden'
        except TelegramBadRequest:
            status, error = 'failed', 'telegram_bad_request'
        except (TelegramNetworkError, TelegramServerError, TimeoutError):
            status, error = 'unknown', 'delivery_not_confirmed'
        except Exception:
            logger.exception('Outbox delivery failed for %s', row['event_key'])
            status, error = 'unknown', 'unexpected_delivery_error'
        async with connection() as conn:
            await conn.execute(
                'UPDATE telegram_deliveries SET status=?,error=?,message_id=?,next_attempt=?,updated=? WHERE event_key=? AND telegram_id=?',
                (status,error,message_id,retry_at,time.time(),row['event_key'],row['telegram_id']))
            await conn.commit()
        logger.info('Delivery event=%s recipient=%s status=%s', row['event_key'],row['telegram_id'],status)
        await asyncio.sleep(0.05)


async def _legacy_text(bot, row):
    from app.utils.notifications import is_quiet_hours
    kwargs = dict(parse_mode='HTML', disable_notification=is_quiet_hours(row['timezone']))
    await _apply_sound_preference(row['telegram_id'], kwargs)
    if row['keyboard']:
        kwargs['reply_markup'] = InlineKeyboardMarkup.model_validate(json.loads(row['keyboard']))
    result = await bot.send_message(chat_id=row['telegram_id'], text=row['text'], **kwargs)
    return 'sent', None, result.message_id if isinstance(result.message_id, int) else None, 0
