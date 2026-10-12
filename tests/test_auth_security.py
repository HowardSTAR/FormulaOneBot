"""Security regressions exercise attack boundaries, not just happy paths."""

import asyncio
from datetime import timedelta

import bcrypt
import pytest
from argon2 import extract_parameters
from argon2.low_level import Type

from app import passwords
from app.emailer import MockMailer
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
