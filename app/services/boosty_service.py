"""Pilot subscription badge. Only complete, validated snapshots may remove it."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path

import httpx

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
"""
logger = logging.getLogger(__name__)


class BoostyUnavailable(Exception):
    pass


class BoostyService:
    def __init__(self, database):
        self.database = database
        self.lock = asyncio.Lock()
        self.last_attempt = 0.0
        self.last_failed = False

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
        token = os.getenv("BOOSTY_ACCESS_TOKEN", "").strip()
        if token:
            return token
        default = Path(__file__).resolve().parents[2] / "secrets" / "boosty-access-token.txt"
        path = Path(os.getenv("BOOSTY_ACCESS_TOKEN_FILE", str(default)))
        try:
            return path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""
        except OSError as exc:
            raise BoostyUnavailable("Не удалось прочитать файл авторизации Boosty") from exc

    def eligible(self, user):
        # Deliberately opt-in: expanding the pilot requires server configuration.
        allowed = os.getenv("BOOSTY_PILOT_TELEGRAM_IDS", "2099386").split(",")
        return str(user.get("telegram_id")) in {value.strip() for value in allowed}

    async def fetch_subscribers(self):
        token = self.access_token()
        if not token:
            raise BoostyUnavailable("Проверка Boosty ещё не настроена")
        subscribers = []
        seen = set()
        expected_total = None
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            for _ in range(1000):
                response = await client.get(
                    f"https://api.boosty.to/v1/blog/{self.blog}/subscribers",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"offset": len(subscribers), "limit": 100},
                )
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
        if type(price) not in (int, float) or price < 0:
            raise BoostyUnavailable("Неизвестная стоимость подписки Boosty")
        next_pay = row.get("nextPayTime")
        # Keep paid access after cancellation until the paid period finishes.
        if next_pay is not None and (type(next_pay) not in (int, float) or next_pay > 100_000_000_000):
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
                    for user in users:
                        if self.eligible(user) and user.get("email"):
                            identity, active, level = self.membership(
                                by_email.get(user["email"].strip().casefold()), now)
                            updates.append((user["id"], self.blog, identity, int(active), level, now))
                    try:
                        await conn.executemany(
                            "INSERT INTO boosty_memberships VALUES (?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(user_id, blog) DO UPDATE SET boosty_id=excluded.boosty_id, "
                            "active=excluded.active, level_name=excluded.level_name, checked_at=excluded.checked_at",
                            updates,
                        )
                        await conn.commit()
                    except BaseException:
                        await conn.rollback()
                        raise
                self.last_failed = False
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                # Never expose upstream bodies, tokens or subscriber emails in errors/logs.
                raise BoostyUnavailable("Boosty временно недоступен. Статус сохранён") from exc

    async def status(self, user):
        eligible = self.eligible(user)
        async with self.database.conn.execute(
            "SELECT * FROM boosty_memberships WHERE user_id = ? AND blog = ?",
            (user["id"], self.blog),
        ) as cursor:
            row = await cursor.fetchone()
        async with self.database.conn.execute(
            "SELECT active FROM premium_overrides WHERE user_id = ?", (user["id"],)
        ) as cursor:
            override = await cursor.fetchone()
        active = bool(row and row["active"] and eligible and user.get("email_verified"))
        manual = bool(override["active"]) if override is not None else None
        return {
            "eligible": eligible, "configured": self.configured,
            "blog_url": f"https://boosty.to/{self.blog}",
            "active": active,
            "premium_active": active if manual is None else manual,
            "premium_override": manual,
            "level_name": row["level_name"] if row and eligible else None,
            "checked_at": row["checked_at"] if row and eligible else None,
            "check_failed": self.last_failed,
        }

    async def worker(self):
        while True:
            if self.configured:
                try:
                    await self.sync()
                except Exception:
                    logger.warning("Boosty sync failed; last confirmed membership retained")
            await asyncio.sleep(900)
