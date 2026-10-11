"""Boosty subscriptions for verified website accounts; validated snapshots only."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time

import httpx
from app.services.boosty_auth import BoostyAuth, BoostyUnavailable

SCHEMA = """
CREATE TABLE IF NOT EXISTS boosty_memberships (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blog TEXT NOT NULL,
    boosty_id INTEGER,
    active INTEGER NOT NULL DEFAULT 0,
    level_name TEXT,
    checked_at REAL NOT NULL,
    PRIMARY KEY(user_id, blog)
);
CREATE TABLE IF NOT EXISTS premium_overrides (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS boosty_membership_terms (
    user_id INTEGER NOT NULL,
    blog TEXT NOT NULL,
    expires_at REAL,
    PRIMARY KEY(user_id, blog),
    FOREIGN KEY(user_id, blog) REFERENCES boosty_memberships(user_id, blog) ON DELETE CASCADE
);
"""
logger = logging.getLogger(__name__)


class BoostyService:
    def __init__(self, database):
        self.database = database
        self.lock = asyncio.Lock()
        self.last_attempt = 0.0
        self.last_failed = False
        self.auth = BoostyAuth()

    @property
    def blog(self):
        blog = os.getenv("BOOSTY_BLOG", "turbotears")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", blog):
            raise BoostyUnavailable("Некорректная настройка блога Boosty")
        return blog

    @property
    def configured(self):
        try:
            return bool(self.access_token())
        except BoostyUnavailable:
            return False

    def access_token(self):
        return self.auth.load()['access_token']

    async def fetch_subscribers(self):
        subscribers = []
        seen = set()
        expected_total = None
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            for _ in range(1000):
                response = await self.auth.get(client,
                    f"https://api.boosty.to/v1/blog/{self.blog}/subscribers",
                    params={"offset": len(subscribers), "limit": 100},
                )
                if response.status_code in (401, 403):
                    raise BoostyUnavailable('Подключение Boosty требует обновления владельцем проекта')
                response.raise_for_status()
                payload = response.json()
                rows, total = payload.get("data"), payload.get("total")
                if not isinstance(rows, list) or type(total) is not int or total < 0:
                    raise BoostyUnavailable("Неизвестный формат ответа Boosty")
                if expected_total is not None and total != expected_total:
                    raise BoostyUnavailable("Список подписчиков изменился во время проверки")
                expected_total = total
                for row in rows:
                    if (not isinstance(row, dict) or type(row.get("id")) is not int
                            or row["id"] in seen or not isinstance(row.get("email"), str)):
                        raise BoostyUnavailable("Неполный список подписчиков Boosty")
                    seen.add(row["id"])
                subscribers.extend(rows)
                if len(subscribers) == total:
                    return subscribers
                if not rows or len(subscribers) > total:
                    raise BoostyUnavailable("Неполный список подписчиков Boosty")
        raise BoostyUnavailable("Превышен лимит страниц Boosty")

    @staticmethod
    def membership(row, now):
        if row is None:
            return None, False, None
        if (type(row.get("subscribed")) is not bool
                or type(row.get("isFeePaid")) is not bool
                or type(row.get("isBlackListed")) is not bool
                or not isinstance(row.get("level"), dict)):
            raise BoostyUnavailable("Статус подписки требует проверки формата Boosty")
        price = row.get("price")
        if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
            raise BoostyUnavailable("Неизвестная стоимость подписки Boosty")
        next_pay = row.get("nextPayTime")
        # Keep paid access after cancellation until the paid period finishes.
        if next_pay is not None and (type(next_pay) not in (int, float)
                                    or not math.isfinite(next_pay)
                                    or not 0 <= next_pay <= 100_000_000_000):
            raise BoostyUnavailable("Неизвестный формат срока подписки Boosty")
        paid_period = next_pay > now if next_pay else row["subscribed"]
        active = (not row["isBlackListed"] and price > 0 and row["isFeePaid"]
                  and paid_period)
        name = row["level"].get("name")
        if name is not None and not isinstance(name, str):
            raise BoostyUnavailable("Неизвестный уровень подписки Boosty")
        return row["id"], active, name if active else None

    async def sync(self):
        async with self.lock:
            if time.monotonic() - self.last_attempt < 60:
                if self.last_failed:
                    raise BoostyUnavailable("Boosty временно недоступен. Повторите позже")
                return
            self.last_attempt = time.monotonic()
            self.last_failed = True
            try:
                rows = await self.fetch_subscribers()
                by_email = {}
                for row in rows:
                    email = row["email"].strip().casefold()
                    if email in by_email:
                        raise BoostyUnavailable("Неоднозначное сопоставление аккаунтов Boosty")
                    by_email[email] = row
                conn = self.database.conn
                now = time.time()
                async with self.database.write_lock:
                    async with conn.execute(
                        "SELECT * FROM users WHERE email_verified = 1 AND archived_at IS NULL"
                    ) as cursor:
                        users = [dict(row) for row in await cursor.fetchall()]
                    # Validate the whole update before writing anything.
                    updates = []
                    terms = []
                    paid_periods = []
                    for user in users:
                        if user.get("email"):
                            identity, active, level = self.membership(
                                by_email.get(user["email"].strip().casefold()), now)
                            updates.append((user["id"], self.blog, identity, int(active), level, now))
                            subscriber = by_email.get(user['email'].strip().casefold())
                            paid_until = subscriber.get('nextPayTime') if subscriber else None
                            terms.append((user['id'], self.blog, paid_until or None))
                            if active and paid_until and paid_until > now:
                                paid_periods.append((user['id'], now, paid_until))
                    try:
                        await conn.executemany(
                            "INSERT INTO boosty_memberships(user_id, blog, boosty_id, active, level_name, checked_at) "
                            "VALUES (?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(user_id, blog) DO UPDATE SET boosty_id=excluded.boosty_id, "
                            "active=excluded.active, level_name=excluded.level_name, checked_at=excluded.checked_at",
                            updates,
                        )
                        await conn.executemany(
                            "INSERT INTO boosty_membership_terms(user_id, blog, expires_at) VALUES (?, ?, ?) "
                            "ON CONFLICT(user_id, blog) DO UPDATE SET expires_at=excluded.expires_at",
                            terms,
                        )
                        for user_id, start, end in paid_periods:
                            overlaps = await (await conn.execute('''SELECT MIN(start),MAX(end)
                                FROM trophy_support_periods WHERE user_id=? AND start<=? AND end>=?''',
                                (user_id, end, start))).fetchone()
                            if overlaps[0] is not None:
                                await conn.execute('DELETE FROM trophy_support_periods WHERE user_id=? AND start<=? AND end>=?', (user_id,end,start))
                                start, end = min(start,overlaps[0]), max(end,overlaps[1])
                            await conn.execute('INSERT INTO trophy_support_periods VALUES (?,?,?)', (user_id,start,end))
                        await conn.commit()
                    except BaseException:
                        await conn.rollback()
                        raise
                self.last_failed = False
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                # Never expose upstream bodies, tokens or subscriber emails in errors/logs.
                raise BoostyUnavailable("Boosty временно недоступен. Статус сохранён") from exc

    async def status(self, user):
        async with self.database.conn.execute(
            "SELECT bm.*, bt.expires_at FROM boosty_memberships bm "
            "LEFT JOIN boosty_membership_terms bt ON bt.user_id=bm.user_id AND bt.blog=bm.blog "
            "WHERE bm.user_id = ? AND bm.blog = ?",
            (user["id"], self.blog),
        ) as cursor:
            row = await cursor.fetchone()
        async with self.database.conn.execute(
            "SELECT active FROM premium_overrides WHERE user_id = ?", (user["id"],)
        ) as cursor:
            override = await cursor.fetchone()
        verified = bool(user.get("email_verified") and user.get("email"))
        expires_at = row['expires_at'] if row and verified else None
        active = bool(row and row["active"] and verified
                      and (expires_at is None or expires_at > time.time()))
        manual = bool(override["active"]) if override is not None else None
        configured = self.configured
        check_unavailable_reason = (
            "Подтвердите в аккаунте тот же email, который используете на Boosty." if not verified else
            "Подключение проверки Boosty готовится." if not configured else None
        )
        return {
            "eligible": True, "configured": configured,
            "blog_url": f"https://boosty.to/{self.blog}",
            "active": active,
            "premium_active": active if manual is None else manual,
            "premium_override": manual,
            "level_name": row["level_name"] if row and verified else None,
            "checked_at": row["checked_at"] if row and verified else None,
            "check_failed": self.last_failed and configured and verified,
            "expires_at": expires_at,
            "can_check": check_unavailable_reason is None,
            "check_unavailable_reason": check_unavailable_reason,
        }

    async def worker(self):
        while True:
            if self.configured:
                try:
                    await self.sync()
                except BoostyUnavailable as exc:
                    logger.warning("Boosty sync failed: %s; last confirmed membership retained", str(exc))
                except Exception:
                    logger.warning("Boosty sync failed; last confirmed membership retained")
            await asyncio.sleep(900)
