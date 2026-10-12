"""Registration opens a saved profile before email verification without trusting the address."""
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import auth_api
from app.api.miniapp_api import web_app
from app.db import ensure_race_game_profile, get_reaction_profile
from app.emailer import EmailDeliveryError, MockMailer
from app.services.auth_service import AuthService, EmailAlreadyRegistered, InvalidCredentials, RateLimitExceeded

PASSWORD = 'FormulaOne-2026-Secure'
PROFILE = {'display_name': 'Турбо Пилот',
           'avatar': {'helmet': 'cobalt', 'suit': 'mint', 'background': 'gold'},
           'favorite_drivers': ['NOR', 'LEC'], 'favorite_teams': ['McLaren', 'Ferrari']}


@pytest.fixture
def registration_auth(db_session, monkeypatch):
    mailer = MockMailer()
    auth = AuthService(db_session, mailer, pepper='registration-profile-tests')
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')
    return auth, mailer


async def test_registration_opens_profile_and_saves_preferences(registration_auth, db_session):
    auth, mailer = registration_auth
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
        result = await client.post('/api/auth/register', json={'email': 'New@Example.test', 'password': PASSWORD, **PROFILE})
        assert result.status_code == 202
        data = result.json()
        assert data['email_sent'] is True
        assert data['user']['email_verified'] is False
        assert data['user']['display_name'] == PROFILE['display_name']
        assert client.cookies.get('turbotears_session')
        assert (await client.get('/api/auth/me')).json()['id'] == data['user']['id']
        own = (await client.get('/api/profiles/me')).json()
        assert own['display_name'] == PROFILE['display_name']
        assert own['avatar'] == PROFILE['avatar']
        assert own['favorites'] == {'drivers': ['LEC', 'NOR'], 'teams': ['Ferrari', 'McLaren']}
        assert own['email'] == 'new@example.test' and own['email_verified'] is False
        assert own['profile_guide_seen'] is False
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as visitor:
            public = (await visitor.get(f"/api/profiles/{data['user']['id']}")).json()
        assert 'email' not in public and 'email_verified' not in public
        assert (await client.post('/api/auth/resend-verification')).status_code == 403
        csrf = {'X-CSRF-Token': data['csrf_token']}
        assert (await client.get('/api/favorites')).json() == own['favorites']
        assert (await client.post('/api/favorites/driver', json={'id': 'NOR'}, headers=csrf)).json()['status'] == 'removed'
        assert (await client.post('/api/favorites/team', json={'id': 'Ferrari'}, headers=csrf)).json()['status'] == 'removed'
        assert (await client.get('/api/favorites')).json() == {'drivers': ['LEC'], 'teams': ['McLaren']}
        old_code = mailer.messages[-1]['code']
        assert (await client.post('/api/auth/resend-verification', headers=csrf)).status_code == 202
        new_code = mailer.messages[-1]['code']
        if old_code != new_code:
            assert (await client.post('/api/auth/verify-email', json={'email': own['email'], 'code': old_code})).status_code == 401
        verified = await client.post('/api/auth/verify-email', json={'email': own['email'], 'code': new_code})
        assert verified.status_code == 200
        assert verified.json()['user']['id'] == data['user']['id']
        assert (await client.get('/api/profiles/me')).json()['email_verified'] is True
        assert (await auth.authenticate_session(data['access_token']))['email_verified'] is True


async def test_unverified_account_can_return_but_cannot_be_overwritten(registration_auth):
    auth, _ = registration_auth
    created = await auth.register('later@example.test', PASSWORD, **PROFILE)
    with pytest.raises(EmailAlreadyRegistered):
        await auth.register('LATER@example.test', 'Attacker-Password-2026', display_name='Другой ник')
    with pytest.raises(InvalidCredentials):
        await auth.login('later@example.test', 'Attacker-Password-2026')
    session = await auth.login('later@example.test', PASSWORD)
    assert session.user['id'] == created['user']['id']
    assert session.user['display_name'] == PROFILE['display_name']
    assert session.user['email_verified'] is False


async def test_unverified_primary_email_gets_no_admin_role(registration_auth, monkeypatch):
    auth, mailer = registration_auth
    monkeypatch.setenv('ADMIN_EMAIL', 'admin-new@example.test')
    created = await auth.register('admin-new@example.test', PASSWORD, **PROFILE)
    assert created['user']['role'] == 'user'
    assert (await auth.authenticate_session(created['access_token']))['role'] == 'user'
    assert (await auth.login('admin-new@example.test', PASSWORD)).user['role'] == 'user'
    await auth.database.init_tables()
    assert (await auth.authenticate_session(created['access_token']))['role'] == 'user'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test',
                                headers={'Authorization': f"Bearer {created['access_token']}"}) as client:
        assert (await client.get('/api/admin/me')).status_code == 403
    verified = await auth.verify_email('admin-new@example.test', mailer.messages[-1]['code'])
    assert verified.user['role'] == 'superadmin'


async def test_mail_failure_keeps_profile_and_resend_can_recover(registration_auth, monkeypatch):
    auth, mailer = registration_auth
    original = mailer.send_verification_code
    monkeypatch.setattr(mailer, 'send_verification_code', AsyncMock(side_effect=EmailDeliveryError('offline')))
    created = await auth.register('offline@example.test', PASSWORD, **PROFILE)
    assert created['email_sent'] is False
    assert (await auth.authenticate_session(created['access_token']))['id'] == created['user']['id']
    monkeypatch.setattr(mailer, 'send_verification_code', original)
    await auth.resend_verification(created['user']['id'])
    assert (await auth.verify_email('offline@example.test', mailer.messages[-1]['code'])).user['email_verified']


async def test_failed_resend_preserves_previous_code(registration_auth, monkeypatch):
    auth, mailer = registration_auth
    created = await auth.register('resend@example.test', PASSWORD, **PROFILE)
    code = mailer.messages[-1]['code']
    monkeypatch.setattr(mailer, 'send_verification_code', AsyncMock(side_effect=EmailDeliveryError('offline')))
    with pytest.raises(EmailDeliveryError):
        await auth.resend_verification(created['user']['id'])
    assert (await auth.verify_email('resend@example.test', code)).user['email_verified']


async def test_resend_limit_counts_failed_deliveries(registration_auth, monkeypatch):
    auth, mailer = registration_auth
    created = await auth.register('limit@example.test', PASSWORD, **PROFILE)
    failing_send = AsyncMock(side_effect=EmailDeliveryError('offline'))
    monkeypatch.setattr(mailer, 'send_verification_code', failing_send)
    for _ in range(4):
        with pytest.raises(EmailDeliveryError):
            await auth.resend_verification(created['user']['id'])
    with pytest.raises(RateLimitExceeded):
        await auth.resend_verification(created['user']['id'])
    assert failing_send.await_count == 4


@pytest.mark.parametrize('values', [
    {'display_name': ''}, {'display_name': ' '}, {'display_name': 'A' * 33},
    {'display_name': '  '}, {'avatar': {'helmet': 'unknown', 'suit': 'mint', 'background': 'gold'}},
    {'favorite_drivers': ['bad code']}, {'favorite_teams': [' ']},
])
async def test_invalid_registration_profile_is_rejected(registration_auth, db_session, values):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
        result = await client.post('/api/auth/register', json={'email': 'invalid@example.test', 'password': PASSWORD, **PROFILE, **values})
        assert result.status_code == 422
        row = await (await db_session.conn.execute('SELECT COUNT(*) FROM users')).fetchone()
        assert row[0] == 0


async def test_registration_nickname_used_for_games_after_linking(registration_auth, db_session):
    auth, _ = registration_auth
    created = await auth.register('games@example.test', PASSWORD, **PROFILE)
    # Telegram activity can update users.display_name; the website nick remains in prediction_profiles.
    await db_session.conn.execute('UPDATE users SET telegram_id=7654321, display_name=? WHERE id=?',
                                  ('Telegram Name', created['user']['id']))
    await db_session.conn.commit()
    assert (await get_reaction_profile(7654321))['display_name'] == PROFILE['display_name']
    game, enrolled = await ensure_race_game_profile(7654321)
    assert enrolled and game['display_name'] == PROFILE['display_name']
