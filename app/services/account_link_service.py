"""SQLite-backed Telegram linking and deterministic account consolidation."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import timedelta
from typing import Any, Literal

from app.db import Database
from app.services.auth_service import iso, utc_now

MergeStrategy = Literal["keep_web", "keep_telegram"]


class LinkError(RuntimeError):
    code = "link_error"


class LinkNotFound(LinkError):
    code = "link_not_found"


class LinkExpired(LinkError):
    code = "link_expired"


class LinkConflict(LinkError):
    code = "merge_strategy_required"


class LinkAlreadyUsed(LinkError):
    code = "link_already_used"


class AccountLinkService:
    link_ttl = timedelta(minutes=5)

    def __init__(self, database: Database, pepper: str | None = None):
        self.database = database
        secret = pepper or os.getenv("AUTH_PEPPER") or os.getenv("BOT_TOKEN")
        if not secret:
            raise RuntimeError("AUTH_PEPPER (or BOT_TOKEN fallback) must be configured")
        self._pepper = secret.encode("utf-8")

    async def _conn(self):
        if not self.database.conn:
            await self.database.connect()
        return self.database.conn

    def _hash(self, namespace: str, value: str) -> str:
        return hmac.new(self._pepper, f"{namespace}:{value}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _new_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _user(row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "email": row["email"],
            "telegram_id": row["telegram_id"],
            "email_verified": bool(row["email_verified"]),
        }

    async def create_web_link_session(self, web_user_id: int) -> dict[str, Any]:
        conn = await self._conn()
        # Telegram /start payload is limited to 64 characters, including "link_".
        raw_token = f"{uuid.uuid4().hex}{secrets.token_urlsafe(16)}"
        short_code = self._new_code()
        expires_at = utc_now() + self.link_ttl
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                async with conn.execute(
                    "SELECT * FROM users WHERE id = ? AND email_verified = 1 AND archived_at IS NULL",
                    (web_user_id,),
                ) as cursor:
                    user = await cursor.fetchone()
                if not user:
                    raise LinkError("A verified web account is required")
                await conn.execute(
                    """
                    UPDATE telegram_link_sessions SET status = 'cancelled', updated_at = ?
                    WHERE web_user_id = ? AND status = 'pending'
                    """,
                    (iso(utc_now()), web_user_id),
                )
                await conn.execute(
                    """
                    INSERT INTO telegram_link_sessions(
                        token_hash, token_hint, short_code_hash, web_user_id, expires_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self._hash("link-token", raw_token),
                        raw_token[-16:],
                        self._hash("web-short-code", short_code),
                        web_user_id,
                        iso(expires_at),
                    ),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return {"token": raw_token, "short_code": short_code, "expires_at": iso(expires_at)}

    async def inspect_web_link(self, token: str, telegram_id: int) -> dict[str, Any]:
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                session = await self._get_pending_link(conn, token)
                claimed_by = session["telegram_id"]
                if claimed_by is not None and int(claimed_by) != int(telegram_id):
                    raise LinkAlreadyUsed("Link session was opened by another Telegram account")
                await conn.execute(
                    "UPDATE telegram_link_sessions SET telegram_id = ?, updated_at = ? WHERE token_hash = ?",
                    (int(telegram_id), iso(utc_now()), session["token_hash"]),
                )
                async with conn.execute(
                    "SELECT * FROM users WHERE id = ?", (session["web_user_id"],)
                ) as cursor:
                    web_user = await cursor.fetchone()
                async with conn.execute(
                    "SELECT * FROM users WHERE telegram_id = ? AND archived_at IS NULL",
                    (int(telegram_id),),
                ) as cursor:
                    telegram_user = await cursor.fetchone()
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        conflict = bool(telegram_user and int(telegram_user["id"]) != int(web_user["id"]))
        return {
            "status": session["status"],
            "expires_at": session["expires_at"],
            "conflict": conflict,
            "web_user": self._user(web_user),
            "telegram_user": self._user(telegram_user) if telegram_user else None,
        }

    async def approve_web_link(
        self, token: str, telegram_id: int, strategy: MergeStrategy | None = None
    ) -> dict[str, Any]:
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                session = await self._get_pending_link(conn, token)
                if session["telegram_id"] is not None and int(session["telegram_id"]) != int(telegram_id):
                    raise LinkAlreadyUsed("Link session belongs to another Telegram account")
                result = await self._merge_accounts_locked(
                    conn, int(session["web_user_id"]), int(telegram_id), strategy
                )
                await conn.execute(
                    """
                    UPDATE telegram_link_sessions SET
                        telegram_id = ?, status = 'approved', merge_policy = ?,
                        approved_at = ?, updated_at = ?
                    WHERE token_hash = ?
                    """,
                    (
                        int(telegram_id), result["strategy"], iso(utc_now()), iso(utc_now()),
                        self._hash("link-token", token),
                    ),
                )
                await conn.commit()
                return result
            except Exception:
                await conn.rollback()
                raise

    async def approve_web_short_code(
        self, short_code: str, telegram_id: int, strategy: MergeStrategy | None = None
    ) -> dict[str, Any]:
        if not re.fullmatch(r"\d{6}", short_code):
            raise LinkNotFound("Invalid code")
        conn = await self._conn()
        async with conn.execute(
            "SELECT * FROM telegram_link_sessions WHERE short_code_hash = ?",
            (self._hash("web-short-code", short_code),),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise LinkNotFound("Invalid code")
        return await self._approve_link_row(row, telegram_id, strategy)

    async def approve_by_hint(
        self, token_hint: str, telegram_id: int, strategy: MergeStrategy | None = None
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{16}", token_hint):
            raise LinkNotFound("Link session not found")
        conn = await self._conn()
        async with conn.execute(
            "SELECT * FROM telegram_link_sessions WHERE token_hint = ?", (token_hint,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise LinkNotFound("Link session not found")
        return await self._approve_link_row(row, telegram_id, strategy)

    async def cancel_by_hint(self, token_hint: str, telegram_id: int) -> None:
        conn = await self._conn()
        async with self.database.write_lock:
            cursor = await conn.execute(
                """
                UPDATE telegram_link_sessions SET status = 'cancelled', telegram_id = ?, updated_at = ?
                WHERE token_hint = ? AND status = 'pending' AND telegram_id = ?
                """,
                (int(telegram_id), iso(utc_now()), token_hint, int(telegram_id)),
            )
            await conn.commit()
        if cursor.rowcount != 1:
            raise LinkNotFound("Link session not found")

    async def _approve_link_row(
        self, row: Any, telegram_id: int, strategy: MergeStrategy | None
    ) -> dict[str, Any]:
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                async with conn.execute(
                    "SELECT * FROM telegram_link_sessions WHERE token_hash = ?", (row["token_hash"],)
                ) as cursor:
                    current_row = await cursor.fetchone()
                if not current_row:
                    raise LinkNotFound("Link session not found")
                self._validate_pending_row(current_row)
                if current_row["telegram_id"] is not None and int(current_row["telegram_id"]) != int(telegram_id):
                    raise LinkAlreadyUsed("Link session belongs to another Telegram account")
                result = await self._merge_accounts_locked(
                    conn, int(current_row["web_user_id"]), int(telegram_id), strategy
                )
                await conn.execute(
                    """
                    UPDATE telegram_link_sessions SET telegram_id = ?, status = 'approved',
                        merge_policy = ?, approved_at = ?, updated_at = ?
                    WHERE token_hash = ?
                    """,
                    (
                        int(telegram_id), result["strategy"], iso(utc_now()), iso(utc_now()),
                        current_row["token_hash"],
                    ),
                )
                await conn.commit()
                return result
            except Exception:
                await conn.rollback()
                raise

    async def create_bot_code(self, telegram_id: int) -> dict[str, Any]:
        conn = await self._conn()
        code = self._new_code()
        expires_at = utc_now() + self.link_ttl
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                await conn.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (int(telegram_id),))
                await conn.execute(
                    "UPDATE telegram_login_codes SET status = 'cancelled' WHERE telegram_id = ? AND status = 'pending'",
                    (int(telegram_id),),
                )
                await conn.execute(
                    "INSERT INTO telegram_login_codes(code_hash, telegram_id, expires_at) VALUES (?, ?, ?)",
                    (self._hash("bot-code", code), int(telegram_id), iso(expires_at)),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return {"code": code, "expires_at": iso(expires_at)}

    async def link_with_bot_code(
        self, web_user_id: int, code: str, strategy: MergeStrategy | None = None
    ) -> dict[str, Any]:
        if not re.fullmatch(r"\d{6}", code):
            raise LinkNotFound("Invalid code")
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                async with conn.execute(
                    "SELECT * FROM telegram_login_codes WHERE code_hash = ?",
                    (self._hash("bot-code", code),),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    raise LinkNotFound("Invalid code")
                self._validate_pending_row(row)
                result = await self._merge_accounts_locked(
                    conn, int(web_user_id), int(row["telegram_id"]), strategy
                )
                await conn.execute(
                    "UPDATE telegram_login_codes SET status = 'approved', consumed_at = ? WHERE code_hash = ?",
                    (iso(utc_now()), row["code_hash"]),
                )
                await conn.commit()
                return result
            except Exception:
                await conn.rollback()
                raise

    async def get_link_status(self, token: str, web_user_id: int) -> dict[str, Any]:
        conn = await self._conn()
        async with conn.execute(
            "SELECT status, telegram_id, expires_at, approved_at FROM telegram_link_sessions "
            "WHERE token_hash = ? AND web_user_id = ?",
            (self._hash("link-token", token), int(web_user_id)),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise LinkNotFound("Link session not found")
        status = row["status"]
        if status == "pending" and self._is_expired(row["expires_at"]):
            status = "expired"
        return {
            "status": status,
            "telegram_id": row["telegram_id"],
            "expires_at": row["expires_at"],
            "approved_at": row["approved_at"],
        }

    async def validate_public_token(self, token: str) -> None:
        conn = await self._conn()
        async with conn.execute(
            "SELECT status, expires_at FROM telegram_link_sessions WHERE token_hash = ?",
            (self._hash("link-token", token),),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise LinkNotFound("Link session not found")
        self._validate_pending_row(row)

    async def merge_accounts(
        self, web_user_id: int, telegram_id: int, strategy: MergeStrategy | None = None
    ) -> dict[str, Any]:
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                result = await self._merge_accounts_locked(conn, web_user_id, telegram_id, strategy)
                await conn.commit()
                return result
            except Exception:
                await conn.rollback()
                raise

    async def _merge_accounts_locked(
        self, conn, web_user_id: int, telegram_id: int, strategy: MergeStrategy | None
    ) -> dict[str, Any]:
        async with conn.execute(
            "SELECT * FROM users WHERE id = ? AND archived_at IS NULL", (int(web_user_id),)
        ) as cursor:
            web_user = await cursor.fetchone()
        if not web_user or not web_user["email"] or not web_user["email_verified"]:
            raise LinkError("A verified web account is required")
        if web_user["telegram_id"] is not None:
            if int(web_user["telegram_id"]) != int(telegram_id):
                raise LinkConflict("Web account is already linked to another Telegram account")
            return {"user": self._user(web_user), "strategy": strategy or "keep_web", "merged": False}

        async with conn.execute(
            "SELECT * FROM users WHERE telegram_id = ? AND archived_at IS NULL", (int(telegram_id),)
        ) as cursor:
            telegram_user = await cursor.fetchone()
        if not telegram_user:
            await conn.execute(
                "UPDATE users SET telegram_id = ?, updated_at = ? WHERE id = ?",
                (int(telegram_id), iso(utc_now()), int(web_user_id)),
            )
            async with conn.execute("SELECT * FROM users WHERE id = ?", (int(web_user_id),)) as cursor:
                result_user = await cursor.fetchone()
            return {"user": self._user(result_user), "strategy": "keep_web", "merged": False}

        if int(telegram_user["id"]) == int(web_user_id):
            return {"user": self._user(web_user), "strategy": strategy or "keep_web", "merged": False}
        if strategy not in ("keep_web", "keep_telegram"):
            raise LinkConflict("Both accounts contain data; choose keep_web or keep_telegram")

        target_id = int(web_user_id if strategy == "keep_web" else telegram_user["id"])
        source_id = int(telegram_user["id"] if strategy == "keep_web" else web_user_id)
        await self._transfer_related_data(conn, source_id, target_id)

        if strategy == "keep_telegram":
            await conn.execute("UPDATE auth_sessions SET user_id = ? WHERE user_id = ?", (target_id, source_id))
            await conn.execute("UPDATE verification_codes SET user_id = ? WHERE user_id = ?", (target_id, source_id))
            await conn.execute(
                "UPDATE telegram_link_sessions SET web_user_id = ? WHERE web_user_id = ?",
                (target_id, source_id),
            )

        await conn.execute("DELETE FROM users WHERE id = ?", (source_id,))
        if strategy == "keep_web":
            await conn.execute(
                "UPDATE users SET telegram_id = ?, updated_at = ? WHERE id = ?",
                (int(telegram_id), iso(utc_now()), target_id),
            )
        else:
            await conn.execute(
                """
                UPDATE users SET email = ?, password_hash = ?, email_verified = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    web_user["email"], web_user["password_hash"], web_user["email_verified"],
                    iso(utc_now()), target_id,
                ),
            )
        await conn.execute(
            """
            INSERT INTO account_merge_log(source_user_id, target_user_id, telegram_id, strategy)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, target_id, int(telegram_id), strategy),
        )
        async with conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)) as cursor:
            result_user = await cursor.fetchone()
        return {"user": self._user(result_user), "strategy": strategy, "merged": True}

    @staticmethod
    async def _transfer_related_data(conn, source_id: int, target_id: int) -> None:
        await conn.execute(
            "INSERT OR IGNORE INTO favorite_drivers(user_id, driver_code) "
            "SELECT ?, driver_code FROM favorite_drivers WHERE user_id = ?",
            (target_id, source_id),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO favorite_teams(user_id, constructor_name) "
            "SELECT ?, constructor_name FROM favorite_teams WHERE user_id = ?",
            (target_id, source_id),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO race_votes(user_id, season, round, rating, created_at) "
            "SELECT ?, season, round, rating, created_at FROM race_votes WHERE user_id = ?",
            (target_id, source_id),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO driver_votes(user_id, season, round, driver_code, created_at) "
            "SELECT ?, season, round, driver_code, created_at FROM driver_votes WHERE user_id = ?",
            (target_id, source_id),
        )

    async def _get_pending_link(self, conn, token: str):
        if not token or len(token) > 256:
            raise LinkNotFound("Link session not found")
        async with conn.execute(
            "SELECT * FROM telegram_link_sessions WHERE token_hash = ?",
            (self._hash("link-token", token),),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise LinkNotFound("Link session not found")
        self._validate_pending_row(row)
        return row

    def _validate_pending_row(self, row: Any) -> None:
        if row["status"] != "pending":
            raise LinkAlreadyUsed("Link session is no longer pending")
        if self._is_expired(row["expires_at"]):
            raise LinkExpired("Link session has expired")

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        from datetime import datetime
        return datetime.fromisoformat(expires_at) <= utc_now()

    async def cleanup_expired(self) -> None:
        conn = await self._conn()
        now = iso(utc_now())
        async with self.database.write_lock:
            await conn.execute(
                "UPDATE telegram_link_sessions SET status = 'expired', updated_at = ? "
                "WHERE status = 'pending' AND expires_at <= ?",
                (now, now),
            )
            await conn.execute(
                "UPDATE telegram_login_codes SET status = 'expired' "
                "WHERE status = 'pending' AND expires_at <= ?",
                (now,),
            )
            await conn.commit()
