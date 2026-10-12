"""Security regressions exercise attack boundaries, not just happy paths."""

import asyncio
from datetime import timedelta
import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import bcrypt
import httpx
import pytest
import pytest_asyncio
from argon2 import extract_parameters
from argon2.low_level import Type

from app import passwords
from app.emailer import MockMailer
from app.emailer import EmailDeliveryError
from app.services.auth_service import (
    AuthService, EmailAlreadyRegistered, InvalidCredentials, RateLimitExceeded,
)

PASSWORD = "Unique racing phrase for the podium"


@pytest.fixture
def auth(db_session):
    return AuthService(db_session, MockMailer(), pepper="security-test-pepper")


async def test_argon2_salts_and_full_unicode_password(auth):
    password = "Секретная фраза для гонок " * 3
    first = await auth._hash_password(password)
    second = await auth._hash_password(password)
    assert first != second
    params = extract_parameters(first)
    assert (params.type, params.memory_cost, params.time_cost, params.parallelism) == (Type.ID, 65536, 3, 1)
    assert await auth._verify_password(password, first)
    assert not await auth._verify_password(password[:-1] + "!", first)
    assert not await auth._verify_password(password[:36], first)
    assert not await auth._verify_password(password, "corrupt-hash")


async def test_legacy_bcrypt_rejects_suffix_and_migrates_short_password(auth, db_session):
    legacy = "LegacyPass12"
    old_hash = bcrypt.hashpw(legacy.encode(), bcrypt.gensalt(rounds=10)).decode()
    await db_session.conn.execute(
        "INSERT INTO users(email,password_hash,email_verified) VALUES (?,?,1)",
        ("legacy@example.test", old_hash),
    )
    await db_session.conn.commit()
    session = await auth.login("legacy@example.test", legacy)
    stored = await (await db_session.conn.execute("SELECT password_hash FROM users")).fetchone()
    assert stored[0].startswith("$argon2id$")
    assert await auth._verify_password(legacy, stored[0])
    assert (await auth.authenticate_session(session.token))["email_verified"]
    edge = "a1" + "x" * 70
    edge_hash = bcrypt.hashpw(edge.encode(), bcrypt.gensalt(rounds=10)).decode()
    assert await auth._verify_password(edge, edge_hash)
    assert not await auth._verify_password(edge + "attacker-suffix", edge_hash)


async def test_unknown_email_runs_real_password_check(auth, monkeypatch):
    observed = []
    original = auth._verify_password

    async def verify(value, hashed):
        observed.append(hashed)
        return await original(value, hashed)

    monkeypatch.setattr(auth, "_verify_password", verify)
    with pytest.raises(InvalidCredentials):
        await auth.login("missing@example.test", PASSWORD)
    assert observed == [passwords.DUMMY_HASH]


async def test_limit_precedes_hash_and_survives_service_restart(auth, db_session, monkeypatch):
    for _ in range(8):
        await auth.reserve_attempt("login", "missing@example.test", 8, timedelta(minutes=15))
    restarted = AuthService(db_session, MockMailer(), pepper="security-test-pepper")

    async def should_not_run(*args):
        pytest.fail("Throttled request reached expensive password verification")

    monkeypatch.setattr(restarted, "_verify_password", should_not_run)
    with pytest.raises(RateLimitExceeded):
        await restarted.login("missing@example.test", PASSWORD)


async def test_ip_limit_blocks_password_spraying_across_emails(auth, monkeypatch):
    await auth.reserve_attempt("login-ip", "192.0.2.1", 1, timedelta(minutes=15))
    # Populate the production threshold without doing 30 expensive hashes.
    conn = await auth._conn()
    await conn.execute("UPDATE auth_rate_limits SET attempts=30 WHERE action='login-ip'")
    await conn.commit()
    with pytest.raises(RateLimitExceeded):
        await auth.login("another-account@example.test", PASSWORD, ip_address="192.0.2.1")
    with pytest.raises(InvalidCredentials):
        await auth.login("another-account@example.test", PASSWORD, ip_address="192.0.2.2")


async def test_duplicate_registration_attempts_are_persisted(auth):
    await auth.register("duplicate@example.test", PASSWORD)
    for _ in range(3):
        with pytest.raises(EmailAlreadyRegistered):
            await auth.register("duplicate@example.test", PASSWORD)
    with pytest.raises(RateLimitExceeded):
        await auth.register("duplicate@example.test", PASSWORD)


async def test_login_releases_database_lock_and_rechecks_password(auth, db_session, monkeypatch):
    await auth.register("race@example.test", PASSWORD)
    entered, release = asyncio.Event(), asyncio.Event()
    original = auth._verify_password

    async def paused_verify(value, hashed):
        assert not db_session.write_lock.locked()
        valid = await original(value, hashed)
        entered.set()
        await release.wait()
        return valid

    monkeypatch.setattr(auth, "_verify_password", paused_verify)
    task = asyncio.create_task(auth.login("race@example.test", PASSWORD))
    await asyncio.wait_for(entered.wait(), timeout=5)
    try:
        async with db_session.write_lock:
            await db_session.conn.execute("UPDATE users SET password_hash='changed-during-login'")
            await db_session.conn.commit()
    finally:
        release.set()
    with pytest.raises(InvalidCredentials):
        await task
    count = await (await db_session.conn.execute("SELECT COUNT(*) FROM auth_sessions")).fetchone()
    assert count[0] == 1  # Only the registration session, no stale-password login.


@pytest_asyncio.fixture
async def client(auth, monkeypatch):
    from app.api import auth_api
    from app.api.miniapp_api import web_app
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://racing.example.test")
    monkeypatch.setenv("WEB_ORIGINS", "https://racing.example.test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url="http://test") as value:
        yield value


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example.test"},
    {"Origin": "https://racing.example.test.evil.test"},
    {"Origin": "null"},
    {"Referer": "https://evil.example.test/form"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site"},
])
async def test_cross_site_login_rejected_before_password_work(client, auth, monkeypatch, headers):
    verify = AsyncMock()
    monkeypatch.setattr(auth, "_verify_password", verify)
    response = await client.post("/api/auth/login", json={"email": "fan@example.test", "password": PASSWORD}, headers=headers)
    assert response.status_code == 403
    verify.assert_not_called()
    assert "no-store" in response.headers["cache-control"]


async def test_allowed_origin_native_client_and_uniform_login_errors(client):
    results = []
    for headers in ({}, {"Origin": "https://racing.example.test", "Sec-Fetch-Site": "cross-site"}, {"Origin": "http://test"}):
        result = await client.post("/api/auth/login", json={"email": "absent@example.test", "password": PASSWORD}, headers=headers)
        assert result.status_code == 401
        results.append(result.json())
    assert results[0] == results[1] == results[2]


async def test_password_and_token_not_reflected_in_validation_errors(client):
    password = "SECRET-short"
    result = await client.post("/api/auth/password/reset", json={
        "token": "SECRET-token", "new_password": password, "password_confirmation": password,
    })
    assert result.status_code == 422
    assert "SECRET" not in result.text
    assert "input" not in result.text
    assert result.headers["referrer-policy"] == "no-referrer"
    assert "no-store" in result.headers["cache-control"]


async def test_recovery_does_not_expose_account_or_mail_failure(client, auth, monkeypatch, caplog):
    await auth.register("recover@example.test", PASSWORD)
    await auth.verify_email("recover@example.test", auth.mailer.messages[-1]["code"])
    monkeypatch.setattr(auth.mailer, "send_password_reset", AsyncMock(side_effect=EmailDeliveryError("SECRET-SMTP-CONFIG")))
    known = await client.post("/api/auth/password/forgot", json={"email": "recover@example.test"})
    unknown = await client.post("/api/auth/password/forgot", json={"email": "unknown@example.test"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert "SECRET" not in caplog.text
    conn = await auth._conn()
    count = await (await conn.execute("SELECT COUNT(*) FROM password_reset_tokens")).fetchone()
    assert count[0] == 0


async def test_ip_throttles_code_guessing_across_accounts(client):
    for number in range(20):
        response = await client.post("/api/auth/verify-email", json={"email": f"unknown{number}@example.test", "code": "123456"})
        assert response.status_code == 401
    response = await client.post("/api/auth/verify-email", json={"email": "new@example.test", "code": "123456"})
    assert response.status_code == 429


async def test_cookie_writes_reject_bad_origin_even_with_valid_csrf(client, auth):
    registered = await client.post("/api/auth/register", json={"email": "csrf@example.test", "password": PASSWORD, "display_name": "Pilot"})
    result = await client.post("/api/auth/logout", headers={"Origin": "https://evil.test", "X-CSRF-Token": registered.json()["csrf_token"]})
    assert result.status_code == 403
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_production_cookies_cannot_be_downgraded_and_csp_applies(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    response = await client.post("/api/auth/register", json={"email": "cookies@example.test", "password": PASSWORD, "display_name": "Pilot"})
    assert response.status_code == 202
    cookies = response.headers.get_list("set-cookie")
    assert all("Secure" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    assert "HttpOnly" in cookies[0]
    assert "HttpOnly" not in cookies[1]
    assert "script-src 'self' https://telegram.org" in response.headers["content-security-policy"]


@pytest.fixture
def production_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_PEPPER", "independent-test-secret-with-more-than-32-bytes")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://racing.example.test")
    monkeypatch.setenv("WEB_ORIGINS", "https://racing.example.test,https://www.racing.example.test")
    monkeypatch.setenv("EMAIL_DELIVERY_MODE", "smtp")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_USE_SSL", "false")


def test_safe_production_configuration(production_config):
    from app.security import validate_production_security
    validate_production_security()


@pytest.mark.parametrize("key,value", [
    ("AUTH_PEPPER", ""), ("AUTH_PEPPER", "short"),
    ("AUTH_COOKIE_SECURE", "false"), ("PUBLIC_WEB_URL", "http://racing.example.test"),
    ("PUBLIC_WEB_URL", "https://user:secret@racing.example.test"),
    ("PUBLIC_WEB_URL", "https://racing.example.test?redirect=evil"),
    ("WEB_ORIGINS", "*"), ("WEB_ORIGINS", ""), ("WEB_ORIGINS", "http://localhost:5173"),
    ("EMAIL_DELIVERY_MODE", "mock"), ("EMAIL_DELIVERY_MODE", "console"), ("SMTP_STARTTLS", "false"),
])
def test_unsafe_production_configuration_refuses_startup(production_config, monkeypatch, key, value):
    from app.security import validate_production_security
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        validate_production_security()


@pytest.mark.parametrize("admin,seconds", [(False, 7*86400), (True, 1800)])
async def test_idle_session_expires(auth, db_session, monkeypatch, admin, seconds):
    from app.services import auth_service
    from tests.support import Clock
    clock = Clock()
    monkeypatch.setattr(auth_service, "utc_now", lambda: clock.now)
    registered = await auth.register("idle@example.test", PASSWORD)
    if admin:
        await db_session.conn.execute("UPDATE users SET role='admin'")
        await db_session.conn.commit()
    clock.advance(seconds=seconds)
    with pytest.raises(InvalidCredentials):
        await auth.authenticate_session(registered["access_token"])


async def test_activity_extends_idle_time_but_not_absolute_expiry(auth, monkeypatch):
    from app.services import auth_service
    from tests.support import Clock
    clock = Clock()
    monkeypatch.setattr(auth_service, "utc_now", lambda: clock.now)
    registered = await auth.register("active@example.test", PASSWORD)
    for _ in range(5):
        clock.advance(seconds=6*86400)
        if clock.now.isoformat() < registered["expires_at"]:
            await auth.authenticate_session(registered["access_token"])
        else:
            with pytest.raises(InvalidCredentials):
                await auth.authenticate_session(registered["access_token"])


@pytest.mark.parametrize("age,accepted", [(0, True), (3599, True), (3600, False), (-30, True), (-31, False)])
async def test_telegram_auth_replay_boundaries(monkeypatch, age, accepted):
    from app import auth as telegram_auth
    from app.config import get_settings
    from fastapi import HTTPException
    now = 1_800_000_000
    monkeypatch.setattr(telegram_auth.time, "time", lambda: now)
    data = {"auth_date": str(now-age), "user": json.dumps({"id": 12345, "first_name": "Pilot"})}
    secret = hmac.new(b"WebAppData", get_settings().bot.token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, "\n".join(f"{key}={value}" for key, value in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    signed = urlencode(data)
    if accepted:
        assert await telegram_auth.get_current_user_id(signed) == 12345
    else:
        with pytest.raises(HTTPException) as error:
            await telegram_auth.get_current_user_id(signed)
        assert error.value.status_code == 401
    with pytest.raises(HTTPException):
        await telegram_auth.get_current_user_id(signed + "&auth_date=" + data["auth_date"])


@pytest.mark.parametrize("flow", ["bot", "web"])
async def test_short_link_codes_have_persistent_actor_limit(db_session, flow):
    from app.services.account_link_service import AccountLinkService, LinkError, LinkNotFound
    links = AccountLinkService(db_session, pepper="security-test-pepper")
    call = links.approve_web_short_code if flow == "bot" else links.link_with_bot_code
    for _ in range(8):
        with pytest.raises(LinkNotFound):
            if flow == "bot":
                await call("123456", 12345)
            else:
                await call(12345, "123456")
    restarted = AccountLinkService(db_session, pepper="security-test-pepper")
    with pytest.raises(LinkError, match="15 минут"):
        if flow == "bot":
            await restarted.approve_web_short_code("654321", 12345)
        else:
            await restarted.link_with_bot_code(12345, "654321")
