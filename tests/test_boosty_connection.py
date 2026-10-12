"""Isolated owner login, validated installation and credential-free diagnostics."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest

from app.services.boosty_auth import BoostyAuth, BoostyUnavailable
from app.services.boosty_service import BoostyService
from scripts import connect_boosty, install_boosty_connection


def owner_session():
    return {'access_token': 'test-access', 'refresh_token': 'test-refresh', 'device_id': 'test-device'}


def cookies():
    return [
        {'domain': '.boosty.to', 'name': 'auth', 'value': quote(json.dumps(owner_session()))},
        {'domain': 'boosty.to', 'name': '_clientId', 'value': 'test-device'},
        {'domain': 'boosty.to', 'name': 'unrelated', 'value': 'never imported'},
    ]


def test_session_capture_uses_only_boosty_auth_and_device():
    assert connect_boosty.session_from_cookies(cookies()) == owner_session()
    assert connect_boosty.session_from_cookies([]) is None
    assert connect_boosty.session_from_cookies([
        {**cookie, 'domain': 'boosty.to.attacker.test'} for cookie in cookies()
    ]) is None
    assert connect_boosty.session_from_cookies([
        {**cookie, 'value': '{}'} if cookie['name'] == 'auth' else cookie for cookie in cookies()
    ]) is None


@pytest.mark.asyncio
async def test_login_uses_fresh_context_and_closes_browser_before_return():
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(new_page=AsyncMock(return_value=page),
                              cookies=AsyncMock(return_value=cookies()), pages=[page])
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context),
                              is_connected=lambda: True, close=AsyncMock())
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    assert await connect_boosty.capture_session(playwright) == owner_session()
    playwright.chromium.launch.assert_awaited_once_with(channel='msedge', headless=False)
    browser.new_context.assert_awaited_once_with(locale='ru-RU')
    context.cookies.assert_awaited_once_with('https://boosty.to/')
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_login_closes_only_the_owned_browser():
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), pages=[])
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context),
                              is_connected=lambda: False, close=AsyncMock())
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    with pytest.raises(connect_boosty.ConnectionError, match='Окно входа закрыто'):
        await connect_boosty.capture_session(playwright)
    browser.close.assert_awaited_once()


@pytest.mark.parametrize('changes', [
    {'host': 'host; run'}, {'container': 'web; run'}, {'username': 'root; run'},
    {'port': True}, {'port': 65536}, {'host': None},
])
def test_invalid_ssh_configuration_is_rejected(tmp_path, changes):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'host': 'example.test', **changes}))
    with pytest.raises(connect_boosty.ConnectionError):
        connect_boosty.read_config(config)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['auth', 'format'])
async def test_failed_validation_never_replaces_live_session(tmp_path, monkeypatch, failure):
    monkeypatch.setenv('BOOSTY_AUTH_FILE', str(tmp_path / 'live.json'))
    auth = BoostyAuth()
    auth.save({'access_token': 'existing-valid-access'})
    before = auth.path.read_bytes()
    async def fetch(service):
        if failure == 'auth':
            raise BoostyUnavailable('owner access rejected', code='auth_required')
        return [{'id': 1, 'email': 'test@example.test', 'status': None}]
    monkeypatch.setattr(BoostyService, 'fetch_subscribers', fetch)
    with pytest.raises(BoostyUnavailable):
        await install_boosty_connection.install(owner_session())
    assert auth.path.read_bytes() == before
    assert not list(tmp_path.glob('.boosty-connect-*'))


@pytest.mark.asyncio
async def test_install_preserves_rotated_candidate_and_syncs_rights(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv('BOOSTY_AUTH_FILE', str(tmp_path / 'live.json'))
    database = SimpleNamespace(connect=AsyncMock(), close=AsyncMock(),
                               conn=db_session.conn, write_lock=db_session.write_lock)
    monkeypatch.setattr('app.db.db', database)
    await db_session.conn.execute("INSERT INTO users(email,email_verified) VALUES ('owner@example.test',1)")
    await db_session.conn.commit()
    import time
    expiry = time.time() + 86400
    async def fetch(service):
        if '.boosty-connect-' in str(service.auth.path):
            service.auth.save({**owner_session(), 'access_token': 'rotated-access', 'refresh_token': 'rotated-refresh'})
        return [{'id': 1, 'email': 'owner@example.test', 'subscribed': True,
                 'status': 'active', 'isBlackListed': False, 'price': 100,
                 'nextPayTime': expiry, 'level': {'name': 'Полный газ'}}]
    monkeypatch.setattr(BoostyService, 'fetch_subscribers', fetch)
    result = await install_boosty_connection.install(owner_session())
    assert result == {'installed': True, 'synced': True, 'subscribers': 1}
    assert BoostyAuth().load()['refresh_token'] == 'rotated-refresh'
    row = await (await db_session.conn.execute('SELECT active FROM boosty_memberships')).fetchone()
    assert row['active'] == 1
    assert not list(tmp_path.glob('.boosty-connect-*'))


@pytest.mark.asyncio
async def test_sync_outage_after_install_reports_installed_session(tmp_path, monkeypatch):
    monkeypatch.setenv('BOOSTY_AUTH_FILE', str(tmp_path / 'live.json'))
    database = SimpleNamespace(connect=AsyncMock(side_effect=OSError('unavailable')), close=AsyncMock())
    monkeypatch.setattr('app.db.db', database)
    monkeypatch.setattr(BoostyService, 'fetch_subscribers', AsyncMock(return_value=[]))
    result = await install_boosty_connection.install(owner_session())
    assert result['installed'] and not result['synced'] and result['error_code'] == 'sync_pending'
    assert BoostyAuth().load() == owner_session()
