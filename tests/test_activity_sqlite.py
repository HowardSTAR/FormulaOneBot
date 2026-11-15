"""Authenticated requests survive stale WAL snapshots and optional metrics contention."""
import sqlite3
from datetime import timedelta

import aiosqlite
import httpx
import pytest

from app.api import auth_api
from app.api.miniapp_api import web_app
from app.emailer import MockMailer
from app.services.activity_service import record_user_activity, record_telegram_activity
from app.services.auth_service import AuthService, InvalidCredentials, iso, utc_now


async def pin_snapshot(database):
    await database.conn.execute('BEGIN')
    await (await database.conn.execute('SELECT COUNT(*) FROM user_activity_events')).fetchone()
    async with aiosqlite.connect(database.db_path) as other:
        await other.execute("UPDATE users SET updated_at=CURRENT_TIMESTAMP")
        await other.commit()


@pytest.mark.asyncio
async def test_activity_writes_survive_shared_stale_snapshot(db_session):
    async with db_session.transaction() as conn:
        await conn.execute('INSERT INTO users(telegram_id) VALUES (7654321)')
        user_id = (await (await conn.execute('SELECT id FROM users WHERE telegram_id=7654321')).fetchone())[0]
    await pin_snapshot(db_session)
    try:
        await record_user_activity(db_session, user_id, 'site')
        await record_user_activity(db_session, user_id, 'site')
        await record_telegram_activity(db_session, 7654321, display_name='Updated driver')
        # The caller's read transaction was neither committed nor rolled back.
        assert db_session.conn.in_transaction
    finally:
        await db_session.conn.rollback()
    rows = await (await db_session.conn.execute('SELECT source,COUNT(*) FROM user_activity_events GROUP BY source')).fetchall()
    assert dict(rows) == {'site': 1, 'bot': 1}
    assert (await (await db_session.conn.execute('SELECT display_name FROM users WHERE id=?', (user_id,))).fetchone())[0] == 'Updated driver'


@pytest.mark.asyncio
async def test_session_refresh_and_private_routes_survive_snapshot(db_session, monkeypatch):
    auth = AuthService(db_session, MockMailer(), pepper='sqlite-activity-regression')
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    created = await auth.register('snapshot@example.test', 'FormulaOne-2026-Secure')
    token = created['access_token']
    async with db_session.transaction() as conn:
        await conn.execute('UPDATE auth_sessions SET last_seen_at=?', (iso(utc_now() - timedelta(minutes=10)),))
    await pin_snapshot(db_session)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test', headers={'Authorization': f'Bearer {token}'}) as client:
            for path in ['/api/auth/me', '/api/account/settings', '/api/favorites']:
                response = await client.get(path)
                assert response.status_code == 200, response.text
        assert db_session.conn.in_transaction
    finally:
        await db_session.conn.rollback()
    last_seen = (await (await db_session.conn.execute('SELECT last_seen_at FROM auth_sessions')).fetchone())[0]
    assert last_seen > iso(utc_now() - timedelta(minutes=1))
    # An externally revoked session must not remain visible in a shared snapshot.
    await pin_snapshot(db_session)
    try:
        async with aiosqlite.connect(db_session.db_path) as other:
            await other.execute('UPDATE auth_sessions SET revoked_at=?', (iso(utc_now()),))
            await other.commit()
        with pytest.raises(InvalidCredentials):
            await auth.authenticate_session(token)
    finally:
        await db_session.conn.rollback()


@pytest.mark.asyncio
async def test_busy_metrics_do_not_bypass_auth_or_csrf(db_session, monkeypatch):
    auth = AuthService(db_session, MockMailer(), pepper='busy-metrics-regression')
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')
    created = await auth.register('busy@example.test', 'FormulaOne-2026-Secure')
    async with aiosqlite.connect(db_session.db_path) as writer:
        await writer.execute('BEGIN IMMEDIATE')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
            client.cookies.set('turbotears_session', created['access_token'])
            assert (await client.get('/api/auth/me')).status_code == 200
            assert (await client.get('/api/account/settings')).status_code == 200
            assert (await client.post('/api/favorites/driver', json={'id': 'NOR'})).status_code == 403
            client.cookies.clear()
            assert (await client.get('/api/auth/me')).status_code == 401
        await writer.rollback()
    # Failed optional writes left no pending transaction; the next sample works.
    await record_user_activity(db_session, created['user']['id'], 'site')
    assert (await (await db_session.conn.execute('SELECT COUNT(*) FROM user_activity_events')).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_activity_schema_errors_are_not_silenced(db_session, monkeypatch):
    auth = AuthService(db_session, MockMailer(), pepper='schema-error-regression')
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    created = await auth.register('schema@example.test', 'FormulaOne-2026-Secure')
    async def broken(*args, **kwargs):
        raise sqlite3.OperationalError('no such table: user_activity_events')
    monkeypatch.setattr(auth_api, 'record_user_activity', broken)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test', headers={'Authorization': f"Bearer {created['access_token']}"}) as client:
        with pytest.raises(sqlite3.OperationalError, match='no such table'):
            await client.get('/api/auth/me')
