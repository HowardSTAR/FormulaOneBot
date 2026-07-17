"""Security and data-integrity tests for email auth and Telegram linking."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import aiosqlite
import pytest

from app.db import Database
from app.emailer import MockMailer, YandexPostboxAPIConfig, YandexPostboxAPIMailer
from app.services.account_link_service import AccountLinkService, LinkAlreadyUsed, LinkConflict
from app.services.auth_service import (
    AuthService,
    InvalidCredentials,
    InvalidResetToken,
    InvalidVerificationCode,
)


@pytest.fixture
def strong_password() -> str:
    return "FormulaOne-2026-Secure"


def test_yandex_postbox_api_signature_does_not_expose_secret():
    mailer = YandexPostboxAPIMailer(
        YandexPostboxAPIConfig(
            access_key_id="test-access-key",
            secret_access_key="test-secret-key",
            from_email="auth@example.com",
        )
    )
    headers = mailer._headers(b"{}", datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc))
    assert headers["X-Amz-Date"] == "20260717T120000Z"
    assert "Credential=test-access-key/20260717/ru-central1/ses/aws4_request" in headers["Authorization"]
    assert "test-secret-key" not in headers["Authorization"]


@pytest.mark.asyncio
async def test_legacy_users_schema_is_migrated_without_losing_ids(temp_db_path):
    """Legacy Telegram users and related rows survive the nullable-ID auth migration."""
    conn = await aiosqlite.connect(temp_db_path)
    await conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            timezone TEXT DEFAULT 'Europe/Moscow',
            notify_before INTEGER DEFAULT 60,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE favorite_drivers (
            user_id INTEGER NOT NULL,
            driver_code TEXT NOT NULL,
            PRIMARY KEY(user_id, driver_code),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        INSERT INTO users(id, telegram_id) VALUES (41, 900001);
        INSERT INTO favorite_drivers(user_id, driver_code) VALUES (41, 'VER');
        """
    )
    await conn.commit()
    await conn.close()

    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    async with database.conn.execute("PRAGMA table_info(users)") as cursor:
        columns = {row["name"]: row for row in await cursor.fetchall()}
    assert columns["telegram_id"]["notnull"] == 0
    assert "email" in columns and "password_hash" in columns
    async with database.conn.execute("SELECT * FROM users WHERE id = 41") as cursor:
        user = await cursor.fetchone()
    assert user["telegram_id"] == 900001
    async with database.conn.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = 41") as cursor:
        favorite = await cursor.fetchone()
    assert favorite["driver_code"] == "VER"
    await database.close()


@pytest.mark.asyncio
async def test_registration_verification_and_login(temp_db_path, strong_password):
    """A code verifies email, creates a session, and never appears in SQLite plaintext."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    service = AuthService(database, mailer, pepper="test-pepper-with-enough-entropy")

    await service.register("Fan@Example.com", strong_password)
    message = mailer.messages[-1]
    code = str(message["code"])
    async with database.conn.execute(
        "SELECT code_hash FROM verification_codes WHERE email = ?", ("fan@example.com",)
    ) as cursor:
        stored = await cursor.fetchone()
    assert code not in stored["code_hash"]

    with pytest.raises(InvalidVerificationCode):
        await service.verify_email("fan@example.com", "000000")
    session = await service.verify_email("fan@example.com", code)
    assert session.user["email_verified"] is True
    authenticated = await service.authenticate_session(session.token)
    assert authenticated["id"] == session.user["id"]
    assert service.verify_csrf(session.csrf_token, authenticated["csrf_hash"])

    login = await service.login("fan@example.com", strong_password)
    assert login.user["id"] == session.user["id"]
    await database.close()


@pytest.mark.asyncio
async def test_password_reset_is_one_time_and_revokes_sessions(temp_db_path, strong_password):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    service = AuthService(database, mailer, pepper="test-pepper-with-enough-entropy")

    await service.register("reset@example.com", strong_password)
    session = await service.verify_email("reset@example.com", str(mailer.messages[-1]["code"]))
    await service.request_password_reset("reset@example.com", "https://f1hub.example")
    reset_url = str(mailer.messages[-1]["reset_url"])
    token = parse_qs(urlparse(reset_url).query)["token"][0]

    async with database.conn.execute("SELECT token_hash FROM password_reset_tokens") as cursor:
        stored = await cursor.fetchone()
    assert token not in stored["token_hash"]

    new_password = "FormulaOne-2027-NewPassword"
    await service.reset_password(token, new_password)
    with pytest.raises(InvalidResetToken):
        await service.reset_password(token, new_password)
    with pytest.raises(InvalidCredentials):
        await service.authenticate_session(session.token)
    with pytest.raises(InvalidCredentials):
        await service.login("reset@example.com", strong_password)
    assert (await service.login("reset@example.com", new_password)).user["email"] == "reset@example.com"
    await database.close()


@pytest.mark.asyncio
async def test_change_password_keeps_current_session_and_revokes_others(temp_db_path, strong_password):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    service = AuthService(database, mailer, pepper="test-pepper-with-enough-entropy")

    await service.register("change@example.com", strong_password)
    first = await service.verify_email("change@example.com", str(mailer.messages[-1]["code"]))
    second = await service.login("change@example.com", strong_password)
    current = await service.authenticate_session(first.token)
    new_password = "FormulaOne-2028-Changed"
    await service.change_password(
        int(current["id"]), strong_password, new_password, current["session_token_hash"]
    )

    assert (await service.authenticate_session(first.token))["email"] == "change@example.com"
    with pytest.raises(InvalidCredentials):
        await service.authenticate_session(second.token)
    assert (await service.login("change@example.com", new_password)).user["id"] == current["id"]
    await database.close()


async def _verified_web_user(database: Database, email: str = "web@example.com") -> int:
    cursor = await database.conn.execute(
        """
        INSERT INTO users(email, password_hash, email_verified)
        VALUES (?, 'bcrypt-placeholder', 1)
        """,
        (email,),
    )
    await database.conn.commit()
    return int(cursor.lastrowid)


@pytest.mark.asyncio
async def test_link_without_duplicate_attaches_telegram_id(temp_db_path):
    """A fresh Telegram identity is attached to the existing web user record."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    web_id = await _verified_web_user(database)
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")

    created = await links.create_web_link_session(web_id)
    result = await links.approve_web_link(created["token"], 777001)
    assert result["user"]["id"] == web_id
    assert result["user"]["telegram_id"] == 777001
    assert result["merged"] is False
    await database.close()


@pytest.mark.asyncio
async def test_deep_link_is_bound_to_first_telegram_account(temp_db_path):
    """A forwarded link cannot be approved by a Telegram account that did not open it first."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    web_id = await _verified_web_user(database)
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")

    created = await links.create_web_link_session(web_id)
    await links.inspect_web_link(created["token"], 700001)
    with pytest.raises(LinkAlreadyUsed):
        await links.approve_web_link(created["token"], 700002)
    result = await links.approve_web_link(created["token"], 700001)
    assert result["user"]["telegram_id"] == 700001
    await database.close()


@pytest.mark.asyncio
async def test_keep_web_merge_moves_telegram_data(temp_db_path):
    """keep_web preserves web ID and moves Telegram favorites before deleting the duplicate."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    web_id = await _verified_web_user(database)
    cursor = await database.conn.execute("INSERT INTO users(telegram_id) VALUES (880001)")
    telegram_user_id = int(cursor.lastrowid)
    await database.conn.execute(
        "INSERT INTO favorite_drivers(user_id, driver_code) VALUES (?, 'NOR')", (telegram_user_id,)
    )
    await database.conn.commit()
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")

    with pytest.raises(LinkConflict):
        await links.merge_accounts(web_id, 880001)
    result = await links.merge_accounts(web_id, 880001, "keep_web")
    assert result["user"]["id"] == web_id
    async with database.conn.execute("SELECT 1 FROM users WHERE id = ?", (telegram_user_id,)) as cursor:
        assert await cursor.fetchone() is None
    async with database.conn.execute(
        "SELECT driver_code FROM favorite_drivers WHERE user_id = ?", (web_id,)
    ) as cursor:
        assert (await cursor.fetchone())["driver_code"] == "NOR"
    await database.close()


@pytest.mark.asyncio
async def test_keep_telegram_merge_moves_web_session_and_credentials(temp_db_path):
    """keep_telegram preserves Telegram ID while web sessions and credentials follow it."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    web_id = await _verified_web_user(database, "merge@example.com")
    cursor = await database.conn.execute("INSERT INTO users(telegram_id) VALUES (990001)")
    telegram_user_id = int(cursor.lastrowid)
    await database.conn.execute(
        """
        INSERT INTO auth_sessions(token_hash, csrf_hash, user_id, expires_at)
        VALUES ('token-hash', 'csrf-hash', ?, '2999-01-01T00:00:00+00:00')
        """,
        (web_id,),
    )
    await database.conn.commit()
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")

    result = await links.merge_accounts(web_id, 990001, "keep_telegram")
    assert result["user"]["id"] == telegram_user_id
    assert result["user"]["email"] == "merge@example.com"
    async with database.conn.execute("SELECT user_id FROM auth_sessions WHERE token_hash = 'token-hash'") as cursor:
        assert (await cursor.fetchone())["user_id"] == telegram_user_id
    async with database.conn.execute("SELECT 1 FROM users WHERE id = ?", (web_id,)) as cursor:
        assert await cursor.fetchone() is None
    await database.close()


@pytest.mark.asyncio
async def test_bot_generated_code_links_on_website(temp_db_path):
    """The reverse manual flow stores bot code in SQLite and consumes it once on the website."""
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    web_id = await _verified_web_user(database)
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")

    generated = await links.create_bot_code(551122)
    result = await links.link_with_bot_code(web_id, generated["code"], "keep_web")
    assert result["user"]["telegram_id"] == 551122
    async with database.conn.execute("SELECT status FROM telegram_login_codes") as cursor:
        assert (await cursor.fetchone())["status"] == "approved"
    await database.close()
