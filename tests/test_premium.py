"""Owner-only premium controls, CSRF, persistence and Boosty precedence."""
import time

import httpx
import pytest

from app.api import admin_api, auth_api, boosty_api
from app.api.miniapp_api import web_app
from app.db import Database
from app.emailer import MockMailer
from app.services.auth_service import AuthService
from app.services.boosty_service import BoostyService


@pytest.fixture
async def premium(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    monkeypatch.setenv('ADMIN_EMAIL', 'owner@example.test')
    monkeypatch.setenv('ADMIN_TELEGRAM_ID', '2099386')
    monkeypatch.setenv('BOOSTY_PILOT_TELEGRAM_IDS', '2099386')
    monkeypatch.delenv('BOOSTY_ACCESS_TOKEN', raising=False)
    monkeypatch.setenv('BOOSTY_ACCESS_TOKEN_FILE', str(temp_db_path.parent / 'missing-token'))
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper='premium-test-only')
    service = BoostyService(database)
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    monkeypatch.setattr(admin_api, 'get_auth_service', lambda: auth)
    monkeypatch.setattr(admin_api, 'db', database)
    monkeypatch.setattr(boosty_api, 'get_boosty_service', lambda: service)

    async def account(email):
        await auth.register(email, 'FormulaOne-2026-Secure')
        return await auth.verify_email(email, str(mailer.messages[-1]['code']))

    owner = await account('owner@example.test')
    other = await account('other@example.test')
    await database.conn.execute('UPDATE users SET telegram_id=2099386 WHERE id=?', (owner.user['id'],))
    await database.conn.commit()
    try:
        yield database, service, owner, other
    finally:
        await database.close()


def client_for(session=None, **kwargs):
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app, **kwargs), base_url='http://test')
    if session:
        client.cookies.set('turbotears_session', session.token)
        client.cookies.set('turbotears_csrf', session.csrf_token)
        client.headers['X-CSRF-Token'] = session.csrf_token
    return client


@pytest.mark.asyncio
async def test_manual_modes_survive_sync_and_auto_restores_subscription(premium, monkeypatch):
    database, service, owner, _ = premium
    rows = []
    async def subscribers():
        return rows
    monkeypatch.setattr(service, 'fetch_subscribers', subscribers)
    async with client_for(owner) as client:
        assert (await client.get('/api/admin/me')).json()['can_manage_own_premium']
        initial = await client.get('/api/admin/me/premium')
        assert initial.headers['cache-control'] == 'no-store'
        assert initial.json()['premium_override'] is None
        enabled = await client.patch('/api/admin/me/premium', json={'mode': 'enabled'})
        assert enabled.status_code == 200
        assert enabled.json()['premium_active'] and not enabled.json()['active']
        assert not enabled.json()['configured']  # No Boosty token is necessary.
        await service.sync()
        assert (await client.get('/api/account/boosty')).json()['premium_active']

        rows.append({'id': 42, 'email': 'owner@example.test', 'subscribed': True,
                     'isFeePaid': True, 'isBlackListed': False, 'price': 100,
                     'nextPayTime': time.time() + 86400, 'level': {'name': 'Supporter'}})
        service.last_attempt = 0
        await service.sync()
        disabled = await client.patch('/api/admin/me/premium', json={'mode': 'disabled'})
        assert disabled.status_code == 200
        assert disabled.json()['active'] and not disabled.json()['premium_active']
        service.last_attempt = 0
        await service.sync()
        assert not (await client.get('/api/account/boosty')).json()['premium_active']

        # A fresh connection/service sees the stored override, as after restart.
        await database.close()
        await database.connect()
        async with database.conn.execute('SELECT * FROM users WHERE id=?', (owner.user['id'],)) as cursor:
            user = dict(await cursor.fetchone())
        assert not (await BoostyService(database).status(user))['premium_active']
        assert user['role'] == 'superadmin'
        automatic = await client.patch('/api/admin/me/premium', json={'mode': 'boosty'})
        assert automatic.status_code == 200
        assert automatic.json()['premium_override'] is None
        assert automatic.json()['premium_active']
        audit = (await client.get('/api/admin/audit-log')).json()['items']
        changes = [item for item in audit if item['action'] == 'user.premium_changed']
        assert [item['details']['to'] for item in changes] == ['boosty', 'disabled', 'enabled']
        assert all(item['target_user_id'] == owner.user['id'] for item in changes)


@pytest.mark.asyncio
async def test_premium_rejects_guests_other_users_and_other_admins(premium):
    database, _, owner, other = premium
    async with client_for() as guest:
        assert (await guest.get('/api/admin/me/premium')).status_code == 401
        assert (await guest.patch('/api/admin/me/premium', json={'mode': 'enabled'})).status_code == 401
    async with client_for(other) as client:
        for role in ['user', 'admin', 'superadmin']:
            await database.conn.execute('UPDATE users SET role=? WHERE id=?', (role, other.user['id']))
            await database.conn.commit()
            assert (await client.get('/api/admin/me/premium')).status_code == 403
            assert (await client.patch('/api/admin/me/premium', json={'mode': 'enabled'})).status_code == 403
        assert not (await client.get('/api/admin/me')).json()['can_manage_own_premium']
    async with database.conn.execute('SELECT COUNT(*) FROM premium_overrides') as cursor:
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_premium_requires_csrf_and_rejects_invalid_modes(premium):
    database, _, owner, _ = premium
    async with client_for(owner) as client:
        del client.headers['X-CSRF-Token']
        assert (await client.patch('/api/admin/me/premium', json={'mode': 'enabled'})).status_code == 403
        client.headers['X-CSRF-Token'] = owner.csrf_token
        assert (await client.patch('/api/admin/me/premium', json={'mode': 'invalid'})).status_code == 422
    async with database.conn.execute('SELECT COUNT(*) FROM premium_overrides') as cursor:
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_failed_audit_rolls_back_premium_change(premium, monkeypatch):
    database, _, owner, _ = premium
    async def fail_audit(*args, **kwargs):
        raise RuntimeError('test-only audit failure')
    monkeypatch.setattr(admin_api, '_audit', fail_audit)
    async with client_for(owner, raise_app_exceptions=False) as client:
        result = await client.patch('/api/admin/me/premium', json={'mode': 'enabled'})
        assert result.status_code == 500
    async with database.conn.execute('SELECT COUNT(*) FROM premium_overrides') as cursor:
        assert (await cursor.fetchone())[0] == 0
