"""Subscription changes, identity boundaries and incomplete upstream responses."""
import time
import hashlib
import hmac
import json
from urllib.parse import urlencode

import httpx
import pytest

from app.api import auth_api, boosty_api
from app.api.miniapp_api import web_app
from app.db import Database
from app.services.boosty_service import BoostyService, BoostyUnavailable


def subscriber(**changes):
    return {"id": 42, "email": "pilot@example.test", "subscribed": True,
            "isFeePaid": True, "isBlackListed": False, "price": 100,
            "nextPayTime": time.time() + 86400, "level": {"name": "Supporter"}, **changes}


@pytest.fixture
async def boosty(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    await database.conn.execute(
        "INSERT INTO users(email, email_verified, telegram_id, role) VALUES (?, 1, 2099386, 'superadmin')",
        ("pilot@example.test",),
    )
    await database.conn.commit()
    monkeypatch.setenv("BOOSTY_PILOT_TELEGRAM_IDS", "2099386")
    monkeypatch.setenv("BOOSTY_ACCESS_TOKEN", "test-only-token")
    monkeypatch.setenv("BOOSTY_BLOG", "turbotears")
    service = BoostyService(database)
    yield service
    await database.close()


async def pilot(service):
    async with service.database.conn.execute("SELECT * FROM users WHERE telegram_id=2099386") as cursor:
        return dict(await cursor.fetchone())


@pytest.mark.asyncio
async def test_grant_cancel_expire_without_changing_admin_role(boosty, monkeypatch):
    rows = [subscriber()]
    async def fetch():
        return rows
    monkeypatch.setattr(boosty, "fetch_subscribers", fetch)
    for rows, expected in [([subscriber()], True),
                           ([subscriber(subscribed=False)], True),
                           ([subscriber(nextPayTime=time.time()-1)], False),
                           ([subscriber(subscribed=False, nextPayTime=time.time()-1)], False),
                           ([subscriber(price=0)], False), ([], False)]:
        boosty.last_attempt = 0
        await boosty.sync()
        user = await pilot(boosty)
        assert (await boosty.status(user))["active"] is expected
        assert user["role"] == "superadmin"


@pytest.mark.asyncio
async def test_failure_retains_status_and_unknown_format_never_revokes(boosty, monkeypatch):
    async def fetch():
        return [subscriber()]
    monkeypatch.setattr(boosty, "fetch_subscribers", fetch)
    await boosty.sync()
    async def broken():
        raise httpx.ConnectError("upstream offline")
    monkeypatch.setattr(boosty, "fetch_subscribers", broken)
    boosty.last_attempt = 0
    with pytest.raises(BoostyUnavailable):
        await boosty.sync()
    status = await boosty.status(await pilot(boosty))
    assert status["active"] and status["check_failed"]
    async def malformed():
        return [subscriber(isFeePaid=None)]
    monkeypatch.setattr(boosty, "fetch_subscribers", malformed)
    boosty.last_attempt = 0
    with pytest.raises(BoostyUnavailable):
        await boosty.sync()
    assert (await boosty.status(await pilot(boosty)))["active"]


@pytest.mark.asyncio
async def test_email_identity_pilot_and_cascade(boosty, monkeypatch):
    await boosty.database.conn.execute("UPDATE users SET email_verified=0")
    await boosty.database.conn.commit()
    async def fetch():
        return [subscriber()]
    monkeypatch.setattr(boosty, "fetch_subscribers", fetch)
    await boosty.sync()
    assert not (await boosty.status(await pilot(boosty)))["active"]
    await boosty.database.conn.execute("UPDATE users SET email_verified=1")
    await boosty.database.conn.commit()
    boosty.last_attempt = 0
    await boosty.sync()
    assert (await boosty.status(await pilot(boosty)))["active"]
    other = {**await pilot(boosty), "telegram_id": 123}
    assert not (await boosty.status(other))["active"]
    await boosty.database.conn.execute("DELETE FROM users")
    await boosty.database.conn.commit()
    async with boosty.database.conn.execute("SELECT COUNT(*) FROM boosty_memberships") as cursor:
        assert (await cursor.fetchone())[0] == 0
    async with boosty.database.conn.execute("SELECT COUNT(*) FROM boosty_membership_terms") as cursor:
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_complete_pagination_required(boosty, monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json={"total": 2, "data": [subscriber(id=offset+1)]})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handle)))
    assert len(await boosty.fetch_subscribers()) == 2
    assert [r.url.params["offset"] for r in requests] == ["0", "1"]
    def incomplete(request):
        return httpx.Response(200, json={"total": 2, "data": []})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(incomplete)))
    with pytest.raises(BoostyUnavailable):
        await boosty.fetch_subscribers()


@pytest.mark.asyncio
async def test_routes_reject_guests_and_non_pilot(boosty, monkeypatch):
    monkeypatch.setattr(boosty_api, "get_boosty_service", lambda: boosty)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url="http://test") as client:
        assert (await client.get("/api/account/boosty")).status_code == 401
        assert (await client.post("/api/account/boosty/check")).status_code == 401
        await boosty.database.conn.execute("UPDATE users SET telegram_id=123")
        await boosty.database.conn.commit()
        async def user_id():
            return 1
        web_app.dependency_overrides[auth_api.require_hybrid_user_id] = user_id
        try:
            assert (await client.post("/api/account/boosty/check")).status_code == 403
        finally:
            web_app.dependency_overrides.pop(auth_api.require_hybrid_user_id, None)


@pytest.mark.asyncio
async def test_manual_check_updates_status_expiry_and_profile_rights(boosty, monkeypatch):
    from app.services import user_profiles

    expiry = time.time() + 86400 * 30
    calls = []
    async def fetch():
        calls.append(True)
        return [subscriber(level={'name': 'Полный газ'}, nextPayTime=expiry)]
    monkeypatch.setattr(boosty, 'fetch_subscribers', fetch)
    monkeypatch.setattr(boosty_api, 'get_boosty_service', lambda: boosty)
    async def user_id():
        return (await pilot(boosty))['id']
    web_app.dependency_overrides[auth_api.require_hybrid_user_id] = user_id
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
            before = (await client.get('/api/account/boosty')).json()
            assert before['can_check'] and not before['active']
            assert calls == [], 'Reading a status must not start a Boosty check'
            response = await client.post('/api/account/boosty/check')
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            status = response.json()
            assert status['active'] and status['level_name'] == 'Полный газ'
            assert status['expires_at'] == expiry and status['checked_at']
            assert len(calls) == 1
            people = await user_profiles.identities(boosty.database)
            assert people[status_user_id := await user_id()]['tier'] == 3
            # A repeat click shares the last sync; it cannot hammer the upstream API.
            assert (await client.post('/api/account/boosty/check')).json()['expires_at'] == expiry
            assert len(calls) == 1
            # Expiry survives a service restart and removes access without another sync.
            assert (await BoostyService(boosty.database).status(await pilot(boosty)))['expires_at'] == expiry
            monkeypatch.setattr(time, 'time', lambda: expiry + 1)
            expired = (await client.get('/api/account/boosty')).json()
            assert not expired['active'] and not expired['premium_active']
            assert (await user_profiles.identities(boosty.database))[status_user_id]['tier'] == 0
    finally:
        web_app.dependency_overrides.pop(auth_api.require_hybrid_user_id, None)


@pytest.mark.asyncio
async def test_manual_check_with_signed_telegram_identity(db_session, monkeypatch):
    from app.config import get_settings
    await db_session.conn.execute(
        "INSERT INTO users(email,email_verified,telegram_id) VALUES ('pilot@example.test',1,2099386)")
    await db_session.conn.commit()
    service = BoostyService(db_session)
    monkeypatch.setenv('BOOSTY_PILOT_TELEGRAM_IDS', '2099386')
    monkeypatch.setenv('BOOSTY_ACCESS_TOKEN', 'test-only-token')
    monkeypatch.setattr(boosty_api, 'get_boosty_service', lambda: service)
    async def fetch():
        return [subscriber(level={'name': 'Свой стиль'})]
    monkeypatch.setattr(service, 'fetch_subscribers', fetch)
    data = {'auth_date': str(int(time.time())), 'user': json.dumps({'id': 2099386, 'first_name': 'Pilot'})}
    secret = hmac.new(b'WebAppData', get_settings().bot.token.encode(), hashlib.sha256).digest()
    data['hash'] = hmac.new(secret, '\n'.join(f'{key}={data[key]}' for key in sorted(data)).encode(), hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
        response = await client.post('/api/account/boosty/check', headers={'X-Telegram-Init-Data': urlencode(data)})
        assert response.status_code == 200 and response.json()['level_name'] == 'Свой стиль'
        data['user'] = json.dumps({'id': 123, 'first_name': 'Forged'})
        assert (await client.post('/api/account/boosty/check', headers={'X-Telegram-Init-Data': urlencode(data)})).status_code == 401


@pytest.mark.asyncio
async def test_unknown_end_date_and_unverified_email(boosty, monkeypatch):
    async def fetch():
        return [subscriber(nextPayTime=None)]
    monkeypatch.setattr(boosty, 'fetch_subscribers', fetch)
    monkeypatch.setattr(boosty_api, 'get_boosty_service', lambda: boosty)
    await boosty.sync()
    status = await boosty.status(await pilot(boosty))
    assert status['active'] and status['expires_at'] is None
    await boosty.database.conn.execute('UPDATE users SET email_verified=0')
    await boosty.database.conn.commit()
    status = await boosty.status(await pilot(boosty))
    assert not status['active'] and not status['can_check']
    assert 'email' in status['check_unavailable_reason']
    async def user_id():
        return 1
    web_app.dependency_overrides[auth_api.require_hybrid_user_id] = user_id
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
            response = await client.post('/api/account/boosty/check')
            assert response.status_code == 403
    finally:
        web_app.dependency_overrides.pop(auth_api.require_hybrid_user_id, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_date', [float('nan'), float('inf'), -1, 'tomorrow', True])
async def test_invalid_end_date_preserves_confirmed_subscription(boosty, monkeypatch, invalid_date):
    expiry = time.time() + 86400
    rows = [subscriber(nextPayTime=expiry)]
    async def fetch():
        return rows
    monkeypatch.setattr(boosty, 'fetch_subscribers', fetch)
    await boosty.sync()
    rows = [subscriber(nextPayTime=invalid_date)]
    boosty.last_attempt = 0
    with pytest.raises(BoostyUnavailable):
        await boosty.sync()
    status = await boosty.status(await pilot(boosty))
    assert status['active'] and status['expires_at'] == expiry and status['check_failed']


def test_token_file_without_exposing_secret(tmp_path, monkeypatch):
    path = tmp_path / "boosty-token.txt"
    path.write_text("test-file-token\n", encoding="utf-8")
    monkeypatch.delenv("BOOSTY_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("BOOSTY_ACCESS_TOKEN_FILE", str(path))
    service = BoostyService(None)
    assert service.configured
    assert service.access_token() == "test-file-token"
