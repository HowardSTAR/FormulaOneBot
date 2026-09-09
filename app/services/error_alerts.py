"""Live admin-only incidents. No log replay and no recursive reporting."""
import asyncio
import hashlib
import html
import logging
import re
import sqlite3
import time
import traceback
import uuid
from pathlib import Path
import httpx
from aiogram.exceptions import (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter,
    TelegramForbiddenError, TelegramUnauthorizedError, TelegramConflictError)
from app.admin_config import get_primary_admin_telegram_id
from app.services.web_notifications import connection, initialize

logger = logging.getLogger(__name__)
LEVELS = {"minimal": "Минимальный", "low": "Низкий", "medium": "Средний", "critical": "Критический", "blocking": "Блокирующий"}
ICONS = {"minimal": "ℹ️", "low": "🟡", "medium": "🟠", "critical": "🔴", "blocking": "⛔"}
_fallback = {}
SCHEMA = """CREATE TABLE IF NOT EXISTS admin_error_incidents (
 fingerprint TEXT PRIMARY KEY, priority TEXT NOT NULL, occurrences INTEGER NOT NULL,
 first_at REAL NOT NULL, last_at REAL NOT NULL, last_notice REAL NOT NULL, event_key TEXT NOT NULL);"""


def priority_for(error):
    message = str(error).lower()
    if isinstance(error, (TelegramUnauthorizedError, TelegramConflictError, MemoryError)):
        return "blocking"
    if isinstance(error, OSError) and error.errno in (28, 30):
        return "blocking"
    if isinstance(error, sqlite3.DatabaseError):
        return "blocking" if any(s in message for s in ("malformed", "disk i/o", "unable to open", "disk is full", "readonly")) else "critical"
    if isinstance(error, TelegramBadRequest) and any(s in message for s in ("query is too old", "query id is invalid", "message is not modified")):
        return "minimal"
    if isinstance(error, (TelegramNetworkError, TelegramRetryAfter, TelegramForbiddenError, TimeoutError, ConnectionError, httpx.TransportError)):
        return "low"
    return "medium"


def redact(value):
    text = re.sub(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b", "[TOKEN]", str(value))
    text = re.sub(r"https?://[^\s<>\"']+", "[URL]", text)
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(authorization|password|passwd|token|secret|api[_-]?key|initdata|cookie)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    return text[:700]


async def record_incident(error, source, priority):
    now = time.time()
    frames = traceback.extract_tb(error.__traceback__)
    location = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else source
    fingerprint = hashlib.sha256(f"{source}:{type(error).__name__}:{location}:{priority}".encode()).hexdigest()
    async with connection() as conn:
        await initialize(conn)
        await conn.execute(SCHEMA)
        await conn.execute("BEGIN IMMEDIATE")
        old = await (await conn.execute("SELECT * FROM admin_error_incidents WHERE fingerprint=?", (fingerprint,))).fetchone()
        count = old["occurrences"] + 1 if old and now - old["last_at"] < 900 else 1
        if priority == "low" and count >= 5:
            priority = "medium"
        interval = 3600 if priority == "minimal" else 900
        emit = not old or now - old["last_notice"] >= interval or old["priority"] != priority
        event_key = f"admin-error:{priority}:{uuid.uuid4().hex}" if emit else old["event_key"]
        title = f"{ICONS[priority]} Ошибка бота · {LEVELS[priority]} приоритет"
        body = f"Источник: {source}\nТип: {type(error).__name__}\n{redact(error)}\nМесто: {location}\nПовторов в серии: {count}"
        await conn.execute("INSERT INTO admin_error_incidents VALUES(?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET priority=excluded.priority,occurrences=excluded.occurrences,last_at=excluded.last_at,last_notice=excluded.last_notice,event_key=excluded.event_key",
            (fingerprint, priority, count, now, now, now if emit else old["last_notice"], event_key))
        if emit:
            admins = await (await conn.execute("SELECT id FROM users WHERE role IN ('admin','superadmin') AND archived_at IS NULL")).fetchall()
            for admin in admins:
                cursor = await conn.execute("INSERT INTO web_notifications(user_id,event_key,title,body,url,created_at) VALUES(?,?,?,?,?,?)", (admin[0], event_key, title, body, "/notifications", now))
                await conn.execute("INSERT OR IGNORE INTO web_push_outbox(notification_id,subscription_id,next_attempt) SELECT ?,id,? FROM web_push_subscriptions WHERE user_id=?", (cursor.lastrowid, now, admin[0]))
        else:
            await conn.execute("UPDATE web_notifications SET body=? WHERE event_key=?", (body, event_key))
        await conn.commit()
    return emit, priority, title, body


async def report_error(error, *, bot=None, source="bot.update", priority=None):
    priority = priority or priority_for(error)
    if priority not in LEVELS:
        raise ValueError("Unknown error priority")
    try:
        emit, priority, title, body = await record_incident(error, source, priority)
    except Exception:
        logger.exception("Admin incident persistence unavailable")
        key, now = (source, type(error).__name__, priority), time.time()
        emit = now - _fallback.get(key, 0) >= 900
        if len(_fallback) > 1024:
            _fallback.clear()
        _fallback[key] = now if emit else _fallback.get(key, now)
        title = f"{ICONS[priority]} Ошибка бота · {LEVELS[priority]} приоритет"
        body = f"Источник: {source}\nТип: {type(error).__name__}\n{redact(error)}\nНе удалось сохранить алёрт на сайте."
    if emit and bot:
        try:
            admin_id = get_primary_admin_telegram_id()
            if admin_id:
                await asyncio.wait_for(bot.send_message(admin_id, f"<b>{html.escape(title)}</b>\n\n<pre>{html.escape(body)}</pre>", parse_mode="HTML"), timeout=10)
        except Exception:
            logger.warning("Admin Telegram alert unavailable; website persistence is independent")
    return priority
