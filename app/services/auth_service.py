"""Email/password authentication backed by SQLite opaque sessions."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt

from app.db import Database
from app.emailer import VerificationMailer

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthError(RuntimeError):
    code = "auth_error"


class InvalidCredentials(AuthError):
    code = "invalid_credentials"


class EmailAlreadyRegistered(AuthError):
    code = "email_already_registered"


class EmailNotVerified(AuthError):
    code = "email_not_verified"


class InvalidVerificationCode(AuthError):
    code = "invalid_verification_code"


class VerificationCodeExpired(AuthError):
    code = "verification_code_expired"


class RateLimitExceeded(AuthError):
    code = "rate_limit_exceeded"


class InvalidInput(AuthError):
    code = "invalid_input"


@dataclass(frozen=True)
class AuthenticatedSession:
    token: str
    csrf_token: str
    expires_at: str
    user: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 254 or not EMAIL_RE.fullmatch(value):
        raise InvalidInput("Invalid email address")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or not local or not domain:
        raise InvalidInput("Invalid email address")
    return value


def validate_password(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(password) < 12:
        raise InvalidInput("Password must contain at least 12 characters")
    if len(encoded) > 72:
        raise InvalidInput("Password must not exceed 72 UTF-8 bytes")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise InvalidInput("Password must contain letters and numbers")


class AuthService:
    verification_ttl = timedelta(minutes=10)
    session_ttl = timedelta(days=30)

    def __init__(self, database: Database, mailer: VerificationMailer, pepper: str | None = None):
        self.database = database
        self.mailer = mailer
        secret = pepper or os.getenv("AUTH_PEPPER") or os.getenv("BOT_TOKEN")
        if not secret:
            raise RuntimeError("AUTH_PEPPER (or BOT_TOKEN fallback) must be configured")
        self._pepper = secret.encode("utf-8")

    async def _conn(self):
        if not self.database.conn:
            await self.database.connect()
        return self.database.conn

    def _hmac(self, namespace: str, value: str) -> str:
        return hmac.new(self._pepper, f"{namespace}:{value}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_user(row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "email": row["email"],
            "telegram_id": row["telegram_id"],
            "email_verified": bool(row["email_verified"]),
            "created_at": row["created_at"],
        }

    async def _hash_password(self, password: str) -> str:
        validate_password(password)
        hashed = await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt(rounds=12))
        return hashed.decode("ascii")

    async def _verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return await asyncio.to_thread(bcrypt.checkpw, password.encode(), password_hash.encode())
        except (ValueError, TypeError):
            return False

    async def _consume_rate_limit(
        self, conn, action: str, identifier: str, max_attempts: int, window: timedelta
    ) -> None:
        key = self._hmac("rate-limit", identifier)
        now = utc_now()
        async with conn.execute(
            "SELECT attempts, window_expires_at FROM auth_rate_limits WHERE action = ? AND identifier_hash = ?",
            (action, key),
        ) as cursor:
            row = await cursor.fetchone()
        if row and datetime.fromisoformat(row["window_expires_at"]) > now:
            if int(row["attempts"]) >= max_attempts:
                raise RateLimitExceeded("Too many attempts; try again later")
            await conn.execute(
                "UPDATE auth_rate_limits SET attempts = attempts + 1 WHERE action = ? AND identifier_hash = ?",
                (action, key),
            )
        else:
            await conn.execute(
                """
                INSERT INTO auth_rate_limits(action, identifier_hash, attempts, window_expires_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(action, identifier_hash) DO UPDATE SET
                    attempts = 1, window_expires_at = excluded.window_expires_at
                """,
                (action, key, iso(now + window)),
            )

    async def _clear_rate_limit(self, conn, action: str, identifier: str) -> None:
        await conn.execute(
            "DELETE FROM auth_rate_limits WHERE action = ? AND identifier_hash = ?",
            (action, self._hmac("rate-limit", identifier)),
        )

    async def register(self, email: str, password: str) -> dict[str, Any]:
        normalized = normalize_email(email)
        password_hash = await self._hash_password(password)
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = self._hmac("email-code", f"{normalized}:{code}")
        expires_at = utc_now() + self.verification_ttl
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                await self._consume_rate_limit(conn, "register", normalized, 4, timedelta(hours=1))
                async with conn.execute("SELECT * FROM users WHERE email = ?", (normalized,)) as cursor:
                    existing = await cursor.fetchone()
                if existing and existing["email_verified"]:
                    raise EmailAlreadyRegistered("Email is already registered")
                if existing:
                    user_id = int(existing["id"])
                    await conn.execute(
                        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                        (password_hash, iso(utc_now()), user_id),
                    )
                else:
                    cursor = await conn.execute(
                        "INSERT INTO users(email, password_hash, email_verified) VALUES (?, ?, 0)",
                        (normalized, password_hash),
                    )
                    user_id = int(cursor.lastrowid)
                await conn.execute(
                    "UPDATE verification_codes SET consumed_at = ? WHERE email = ? AND consumed_at IS NULL",
                    (iso(utc_now()), normalized),
                )
                await conn.execute(
                    "INSERT INTO verification_codes(user_id, email, code_hash, expires_at) VALUES (?, ?, ?, ?)",
                    (user_id, normalized, code_hash, iso(expires_at)),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        try:
            await self.mailer.send_verification_code(
                normalized, code, int(self.verification_ttl.total_seconds() // 60)
            )
        except Exception:
            async with self.database.write_lock:
                await conn.execute(
                    "DELETE FROM verification_codes WHERE email = ? AND code_hash = ?",
                    (normalized, code_hash),
                )
                await conn.commit()
            raise
        return {"email": normalized, "expires_at": iso(expires_at)}

    async def verify_email(
        self, email: str, code: str, user_agent: str | None = None, ip_address: str | None = None
    ) -> AuthenticatedSession:
        normalized = normalize_email(email)
        if not re.fullmatch(r"\d{6}", code):
            raise InvalidVerificationCode("Invalid verification code")
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                async with conn.execute(
                    """
                    SELECT vc.*, u.id AS account_id FROM verification_codes vc
                    JOIN users u ON u.id = vc.user_id
                    WHERE vc.email = ? AND vc.consumed_at IS NULL
                    ORDER BY vc.id DESC LIMIT 1
                    """,
                    (normalized,),
                ) as cursor:
                    verification = await cursor.fetchone()
                if not verification:
                    raise InvalidVerificationCode("Invalid verification code")
                if datetime.fromisoformat(verification["expires_at"]) <= utc_now():
                    await conn.execute(
                        "UPDATE verification_codes SET consumed_at = ? WHERE id = ?",
                        (iso(utc_now()), verification["id"]),
                    )
                    raise VerificationCodeExpired("Verification code has expired")
                if int(verification["attempts"]) >= int(verification["max_attempts"]):
                    raise RateLimitExceeded("Verification code attempt limit reached")
                expected = self._hmac("email-code", f"{normalized}:{code}")
                if not hmac.compare_digest(expected, verification["code_hash"]):
                    await conn.execute(
                        "UPDATE verification_codes SET attempts = attempts + 1 WHERE id = ?",
                        (verification["id"],),
                    )
                    await conn.commit()
                    raise InvalidVerificationCode("Invalid verification code")
                now = iso(utc_now())
                await conn.execute(
                    "UPDATE verification_codes SET consumed_at = ? WHERE id = ?",
                    (now, verification["id"]),
                )
                await conn.execute(
                    "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
                    (now, verification["account_id"]),
                )
                session = await self._create_session_locked(
                    conn, int(verification["account_id"]), user_agent, ip_address
                )
                await self._clear_rate_limit(conn, "register", normalized)
                await conn.commit()
                return session
            except (InvalidVerificationCode, VerificationCodeExpired, RateLimitExceeded):
                if conn.in_transaction:
                    await conn.commit()
                raise
            except Exception:
                await conn.rollback()
                raise

    async def login(
        self, email: str, password: str, user_agent: str | None = None, ip_address: str | None = None
    ) -> AuthenticatedSession:
        normalized = normalize_email(email)
        conn = await self._conn()
        async with self.database.write_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                await self._consume_rate_limit(conn, "login", normalized, 8, timedelta(minutes=15))
                async with conn.execute(
                    "SELECT * FROM users WHERE email = ? AND archived_at IS NULL", (normalized,)
                ) as cursor:
                    user = await cursor.fetchone()
                valid = bool(
                    user and user["password_hash"]
                    and await self._verify_password(password, user["password_hash"])
                )
                if not valid:
                    await conn.commit()
                    raise InvalidCredentials("Invalid email or password")
                if not user["email_verified"]:
                    await conn.commit()
                    raise EmailNotVerified("Email address is not verified")
                await self._clear_rate_limit(conn, "login", normalized)
                session = await self._create_session_locked(conn, int(user["id"]), user_agent, ip_address)
                await conn.commit()
                return session
            except (InvalidCredentials, EmailNotVerified, RateLimitExceeded):
                if conn.in_transaction:
                    await conn.commit()
                raise
            except Exception:
                await conn.rollback()
                raise

    async def _create_session_locked(
        self, conn, user_id: int, user_agent: str | None, ip_address: str | None
    ) -> AuthenticatedSession:
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = utc_now() + self.session_ttl
        await conn.execute(
            """
            INSERT INTO auth_sessions(token_hash, csrf_hash, user_id, expires_at, user_agent, ip_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self._token_hash(token), self._token_hash(csrf_token), user_id, iso(expires_at),
                (user_agent or "")[:300] or None,
                self._hmac("ip", ip_address) if ip_address else None,
            ),
        )
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        return AuthenticatedSession(token, csrf_token, iso(expires_at), self._public_user(user))

    async def authenticate_session(self, token: str) -> dict[str, Any]:
        if not token or len(token) > 512:
            raise InvalidCredentials("Invalid session")
        conn = await self._conn()
        async with conn.execute(
            """
            SELECT s.token_hash, s.csrf_hash, s.expires_at, u.* FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.revoked_at IS NULL AND u.archived_at IS NULL
            """,
            (self._token_hash(token),),
        ) as cursor:
            row = await cursor.fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= utc_now():
            raise InvalidCredentials("Invalid or expired session")
        result = self._public_user(row)
        result["csrf_hash"] = row["csrf_hash"]
        result["session_token_hash"] = row["token_hash"]
        return result

    def verify_csrf(self, csrf_token: str | None, expected_hash: str) -> bool:
        return bool(csrf_token) and hmac.compare_digest(self._token_hash(csrf_token or ""), expected_hash)

    async def logout(self, token: str) -> None:
        conn = await self._conn()
        async with self.database.write_lock:
            await conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?",
                (iso(utc_now()), self._token_hash(token)),
            )
            await conn.commit()

    async def cleanup_expired(self) -> None:
        now = iso(utc_now())
        conn = await self._conn()
        async with self.database.write_lock:
            await conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL", (now,))
            await conn.execute("DELETE FROM verification_codes WHERE expires_at <= ?", (now,))
            await conn.execute("DELETE FROM auth_rate_limits WHERE window_expires_at <= ?", (now,))
            await conn.commit()

