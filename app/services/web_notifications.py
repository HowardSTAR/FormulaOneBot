"""Website inbox and a durable, bounded Web Push outbox. No Telegram dependency."""
import asyncio
import base64
import html
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import aiosqlite
from app.db import db

logger = logging.getLogger(__name__)
SCHEMA = """
CREATE TABLE IF NOT EXISTS web_notification_members (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 joined_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_notifications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 event_key TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL,
 created_at REAL NOT NULL, read_at REAL, UNIQUE(user_id,event_key)
);
CREATE INDEX IF NOT EXISTS web_notifications_user ON web_notifications(user_id,id DESC);
CREATE TABLE IF NOT EXISTS web_notification_events (event_key TEXT PRIMARY KEY, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS web_push_subscriptions (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 endpoint TEXT NOT NULL UNIQUE, subscription TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_push_outbox (
 notification_id INTEGER REFERENCES web_notifications(id) ON DELETE CASCADE,
 subscription_id INTEGER REFERENCES web_push_subscriptions(id) ON DELETE CASCADE,
 attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL, done INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(notification_id,subscription_id)
);
CREATE INDEX IF NOT EXISTS web_push_pending ON web_push_outbox(done,next_attempt);
CREATE TABLE IF NOT EXISTS web_notification_expirations (
 notification_id INTEGER PRIMARY KEY REFERENCES web_notifications(id) ON DELETE CASCADE,
 expires REAL NOT NULL
);
"""

@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=10000")
        yield conn

async def initialize(conn):
    await conn.executescript(SCHEMA)

def push_config():
    public = os.getenv("WEB_PUSH_PUBLIC_KEY", "")
    return {"enabled": bool(public and os.getenv("WEB_PUSH_PRIVATE_KEY") and os.getenv("WEB_PUSH_SUBJECT")), "public_key": public}

def validate_subscription(data: dict) -> None:
    # Explicit vendor allowlist prevents subscriptions from becoming an SSRF proxy.
    url = urlsplit(data.get("endpoint", ""))
    host = url.hostname or ""
    allowed = host in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"} or host.endswith(".notify.windows.com")
    if url.scheme != "https" or not allowed or url.port not in (None, 443) or url.username or url.password or url.fragment:
        raise ValueError("Неподдерживаемый адрес push-сервиса")
    for key, size in (("p256dh", 65), ("auth", 16)):
        value = data.get("keys", {}).get(key, "")
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
            raise ValueError("Некорректный ключ подписки")
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if len(raw) != size or (key == "p256dh" and raw[0] != 4):
            raise ValueError("Некорректный ключ подписки")

async def has_members():
    async with connection() as conn:
        try:
            row = await (await conn.execute("SELECT 1 FROM web_notification_members LIMIT 1")).fetchone()
            return bool(row)
        except aiosqlite.OperationalError:
            return False

async def publish(event_key: str, title: str, body: str, url: str, *, user_id=None, rows=None, expires=None):
    """Called only by live event triggers; existing startup watermarks stay authoritative."""
    if not await has_members():
        return
    now = time.time()
    text = html.unescape(re.sub(r"<[^>]*>", "", body))
    if not url.startswith("/") or url.startswith("//"):
        raise ValueError("Notification URL must be local")
    async with connection() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute("INSERT OR IGNORE INTO web_notification_events VALUES(?,?)", (event_key,now))
        event_time = (await (await conn.execute("SELECT created_at FROM web_notification_events WHERE event_key=?", (event_key,))).fetchone())[0]
        members = await (await conn.execute(
            "SELECT m.user_id FROM web_notification_members m JOIN users u ON u.id=m.user_id WHERE u.archived_at IS NULL AND m.joined_at<=?"
            + (" AND m.user_id=?" if user_id is not None else ""), (event_time,user_id) if user_id is not None else (event_time,),
        )).fetchall()
        for member in members:
            uid = member[0]
            personalized = text
            if rows:
                drivers = {r[0].upper() for r in await (await conn.execute("SELECT driver_code FROM favorite_drivers WHERE user_id=?", (uid,))).fetchall()}
                teams = {r[0].lower() for r in await (await conn.execute("SELECT constructor_name FROM favorite_teams WHERE user_id=?", (uid,))).fetchall()}
                favorites = [r for r in rows if str(r.get("code", "")).upper() in drivers or str(r.get("team", "")).lower() in teams]
                if favorites:
                    personalized += "\n\n⭐ Ваше избранное\n" + "\n".join(f"P{r.get('position', '—')} · {r.get('name', '')} · {r.get('team', '')}" for r in favorites)
            cursor = await conn.execute("INSERT OR IGNORE INTO web_notifications(user_id,event_key,title,body,url,created_at) VALUES(?,?,?,?,?,?)", (uid,event_key,title,personalized,url,now))
            if cursor.rowcount:
                if expires is not None:
                    await conn.execute('INSERT INTO web_notification_expirations VALUES(?,?)', (cursor.lastrowid, expires))
                await conn.execute("INSERT OR IGNORE INTO web_push_outbox(notification_id,subscription_id,next_attempt) SELECT ?,id,? FROM web_push_subscriptions WHERE user_id=?", (cursor.lastrowid,now,uid))
        await conn.commit()



async def dispatch_push(*, not_before: float):
    """Bridge existing transactional producers into the common delivery engine."""
    from app.services.telegram_outbox import enqueue, drain
    async with connection() as conn:
        jobs = await (await conn.execute('''SELECT o.notification_id,o.subscription_id,o.attempts,n.title,n.body,n.url,n.event_key,n.created_at,e.expires
            FROM web_push_outbox o JOIN web_notifications n ON n.id=o.notification_id
            LEFT JOIN web_notification_expirations e ON e.notification_id=n.id
            WHERE o.done=0 ORDER BY n.id LIMIT 100''')).fetchall()
    for job in jobs:
        # Existing queued work survives restart, but not its original TTL.
        payload = {'event_key':job['event_key'], 'data':{'title':job['title'],'body':job['body'][:600],
                    'url':job['url'],'tag':f"notification-{job['notification_id']}"}}
        await enqueue(f"webpush:{job['notification_id']}:{job['subscription_id']}", '', None,
                      [(job['subscription_id'],'UTC')],min(job['expires'] or job['created_at']+3600,job['created_at']+3600),channel='webpush',payload=payload,
                      initial_status='unknown' if job['attempts'] else 'pending')
        async with connection() as conn:
            await conn.execute('UPDATE web_push_outbox SET done=1 WHERE notification_id=? AND subscription_id=?', (job['notification_id'],job['subscription_id']))
            await conn.commit()
    await drain(limit=30)


async def publish_safely(*args, **kwargs):
    try:
        await publish(*args, **kwargs)
    except Exception:
        logger.exception("Website notification persistence failed")

async def classification(season, round_num, title, route, rows):
    body = "\n".join(f"P{r.get('position', '—')} · {r.get('name', '')} · {r.get('team', '')} · {r.get('display', r.get('points', ''))}" for r in rows)
    await publish_safely(f"{season}:{round_num}:{route}", title, body, f"/{route}?season={season}&round={round_num}", rows=rows)

async def poll_web_notifications(*, not_before: float):
    """Web-only accounts get the same upcoming-session reminder text and preferences."""
    from datetime import datetime, timezone
    from app.f1_data import get_season_schedule_short_async
    from app.utils.notifications import get_notification_text
    if not await has_members():
        return
    # Existing deliveries must not depend on the schedule provider being online.
    await dispatch_push(not_before=not_before)
    now = time.time()
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season) or []
    async with connection() as conn:
        members = await (await conn.execute("SELECT u.id,u.timezone,u.notify_before,u.reminder_sessions,m.joined_at FROM web_notification_members m JOIN users u ON u.id=m.user_id WHERE u.archived_at IS NULL")).fetchall()
    for event in schedule:
        if event.get("is_cancelled") or not event.get("round"):
            continue
        from app.session_reminders import SESSION_BITS, session_enabled
        for kind in SESSION_BITS:
            if event.get("is_testing") and kind != "race":
                continue
            value = event.get(f"{kind}_start_utc")
            if not value:
                continue
            try:
                start = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            for user in members:
                if not session_enabled(user["reminder_sessions"], kind):
                    continue
                minutes = int(user["notify_before"] or 60)
                due = start.timestamp() - minutes * 60
                if due < max(not_before,user["joined_at"]) or not 0 <= now-due <= 90:
                    continue
                text = get_notification_text(event,user["timezone"] or "Europe/Moscow",(start.timestamp()-now)/60,event_kind=kind)
                await publish_safely(f"reminder:{season}:{event['round']}:{kind}:{minutes}", "Скоро сессия", text,
                    f"/race-details?season={season}&round={event['round']}", user_id=user["id"], expires=start.timestamp())
