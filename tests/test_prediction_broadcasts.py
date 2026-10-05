"""Manual prediction broadcasts use isolated queues; no external sends or race API calls."""
import asyncio
import json
import time

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api import admin_tools_api as api
from app.db import Database
from app.services import prediction_broadcasts as service


@pytest_asyncio.fixture
async def broadcasts(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    monkeypatch.setattr(service, 'db', database)
    monkeypatch.setenv('MINI_APP_URL', 'https://example.test')
    await database.conn.executemany(
        'INSERT INTO users(id,telegram_id,role,archived_at,email) VALUES(?,?,?,?,?)',
        [(1, 101, 'admin', None, None), (2, 102, 'user', None, None),
         (3, None, 'user', None, 'web@example.test'),
         (4, 104, 'user', '2026-01-01', None), (5, 105, 'user', None, None)],
    )
    await database.conn.executemany('INSERT INTO web_notification_members VALUES(?,?)',
                                    [(uid, time.time()-60) for uid in (1, 3, 4)])
    await database.conn.execute("UPDATE users SET notifications_enabled=0 WHERE id=2")
    await database.conn.execute(
        "INSERT INTO web_push_subscriptions(user_id,endpoint,subscription,created_at) VALUES(3,'https://example.test/push','{}',?)",
        (time.time(),),
    )
    await database.conn.execute(
        '''INSERT INTO prediction_round_results(season,round,event_name,pole_driver,winner_driver,
           second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
           first_retirement_driver,safety_car,max_points)
           VALUES(2026,16,'Test <GP>','VER','VER','NOR','HAM','LEC','PIA','HAM','STR',0,34)''',
    )
    await database.conn.execute("INSERT INTO prediction_profiles(user_id,display_name) VALUES(1,'Fan <one>')")
    await database.conn.execute(
        '''INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,
           second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
           first_retirement_driver,safety_car,points,max_points)
           VALUES(1,2026,16,'VER','VER','NOR','HAM','LEC','PIA','HAM','STR',0,20,34)''',
    )
    await database.conn.commit()
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[api.require_admin_session] = lambda: api.AdminContext(id=1, role='admin')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield database, app, client
    await database.close()


async def total(database, table):
    return (await (await database.conn.execute(f'SELECT COUNT(*) FROM {table}')).fetchone())[0]


@pytest.mark.asyncio
async def test_calculated_unchanged_results_broadcast_both_channels_atomically(broadcasts):
    database, _, client = broadcasts
    preview = await client.get('/api/admin/tools/prediction-results/preview?season=2026&round=16')
    assert preview.status_code == 200
    assert preview.headers['cache-control'] == 'no-store'
    data = preview.json()
    assert data['recipients'] == {'telegram': 3, 'web': 2}
    assert data['provisional'] is False
    assert 'Fan <one>' in data['body'] and 'Test <GP>' in data['body']
    assert await total(database, 'web_notifications') == 0
    assert await total(database, 'telegram_delivery_batches') == 0
    # No recovery or applied state is required; normal broadcasts may already be sent.
    await database.conn.execute('INSERT INTO prediction_notification_state(season,round,results_sent) VALUES(2026,16,1)')
    await database.conn.commit()
    body = {'season': 2026, 'round': 16, 'fingerprint': data['fingerprint'], 'confirmation': 'ОТПРАВИТЬ'}
    first, second = await asyncio.gather(*[client.post('/api/admin/tools/prediction-results/send', json=body) for _ in range(2)])
    assert first.status_code == second.status_code == 200
    assert {first.json()['already_sent'], second.json()['already_sent']} == {False, True}
    assert first.json()['recipients'] == {'telegram': 3, 'web': 2}
    assert await total(database, 'telegram_delivery_batches') == 1
    assert await total(database, 'telegram_deliveries') == 3
    assert await total(database, 'web_notifications') == 2
    assert await total(database, 'web_push_outbox') == 1
    assert await total(database, 'admin_audit_log') == 1
    batch = await (await database.conn.execute('SELECT text,keyboard FROM telegram_delivery_batches')).fetchone()
    assert 'Fan &lt;one&gt;' in batch['text']
    keyboard = json.loads(batch['keyboard'])['inline_keyboard']
    assert 'season=2026' in keyboard[0][0]['web_app']['url']
    assert keyboard[1][0]['callback_data'] == 'personal:review:2026:16'
    results = await (await database.conn.execute('SELECT points,max_points FROM race_predictions')).fetchone()
    assert tuple(results) == (20, 34)
    assert await total(database, 'prediction_recovery') == 0
    assert (await client.get('/api/admin/tools/prediction-results/preview?season=2026&round=16')).json()['already_sent']


@pytest.mark.asyncio
async def test_stale_preview_rejected_and_changed_results_can_be_sent(broadcasts):
    database, _, _ = broadcasts
    preview = await service.preview(2026, 16)
    await service.send(2026, 16, preview['fingerprint'], 1)
    await database.conn.execute('UPDATE race_predictions SET points=21 WHERE user_id=1')
    await database.conn.commit()
    with pytest.raises(ValueError, match='изменились'):
        await service.send(2026, 16, preview['fingerprint'], 1)
    updated = await service.preview(2026, 16)
    assert not updated['already_sent']
    assert updated['fingerprint'] != preview['fingerprint']
    assert not (await service.send(2026, 16, updated['fingerprint'], 1))['already_sent']
    assert await total(database, 'web_notifications') == 4
    assert await total(database, 'telegram_delivery_batches') == 2


@pytest.mark.asyncio
async def test_preliminary_results_and_zero_participants_are_labelled(broadcasts):
    database, _, _ = broadcasts
    await database.conn.execute('UPDATE prediction_round_results SET fastest_lap_driver=NULL')
    await database.conn.commit()
    preview = await service.preview(2026, 16)
    assert preview['provisional'] and 'Предварительные итоги' in preview['body']
    await database.conn.execute('DELETE FROM race_predictions')
    await database.conn.commit()
    preview = await service.preview(2026, 16)
    assert preview['participants'] == 0
    assert 'не было отправленных прогнозов' in preview['body']
    await service.send(2026, 16, preview['fingerprint'], 1)


@pytest.mark.asyncio
async def test_validation_auth_and_unscored_rounds(broadcasts):
    database, app, client = broadcasts
    preview_url = '/api/admin/tools/prediction-results/preview?season=2026&round=16'
    body = {'season': 2026, 'round': 16, 'fingerprint': (await service.preview(2026, 16))['fingerprint'], 'confirmation': 'ОТПРАВИТЬ'}
    url = '/api/admin/tools/prediction-results/send'
    app.dependency_overrides.clear()
    assert (await client.get(preview_url)).status_code in {401, 403}
    assert (await client.post(url, json=body)).status_code in {401, 403}
    app.dependency_overrides[api.require_admin_session] = lambda: api.AdminContext(id=1, role='admin')
    for bad in ({'confirmation': ''}, {'fingerprint': 'bad'}, {'round': 99}, {'season': 0}):
        assert (await client.post(url, json={**body, **bad})).status_code == 422
    assert (await client.get('/api/admin/tools/prediction-results/preview?season=2026&round=15')).status_code == 409
    await database.conn.execute('UPDATE race_predictions SET points=NULL')
    await database.conn.commit()
    assert (await client.get(preview_url)).status_code == 409
    assert (await client.post(url, json=body)).status_code == 409
    assert await total(database, 'web_notifications') == 0


@pytest.mark.asyncio
async def test_channels_rollback_together_on_persistence_failure(broadcasts):
    database, _, _ = broadcasts
    preview = await service.preview(2026, 16)
    await database.conn.execute("CREATE TRIGGER reject_web BEFORE INSERT ON web_notifications BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    await database.conn.commit()
    with pytest.raises(aiosqlite.IntegrityError, match='test failure'):
        await service.send(2026, 16, preview['fingerprint'], 1)
    assert await total(database, 'telegram_delivery_batches') == 0
    assert await total(database, 'telegram_deliveries') == 0
    assert await total(database, 'web_notification_events') == 0
    await database.conn.execute('DROP TRIGGER reject_web')
    await database.conn.commit()
    assert not (await service.send(2026, 16, preview['fingerprint'], 1))['already_sent']


@pytest.mark.asyncio
async def test_repeat_keeps_frozen_audience_and_empty_audience_rejected(broadcasts):
    database, _, _ = broadcasts
    preview = await service.preview(2026, 16)
    await service.send(2026, 16, preview['fingerprint'], 1)
    await database.conn.execute("INSERT INTO users(id,telegram_id) VALUES(6,106)")
    await database.conn.execute('INSERT INTO web_notification_members VALUES(6,?)', (time.time(),))
    await database.conn.commit()
    repeat = await service.send(2026, 16, preview['fingerprint'], 1)
    assert repeat == {'recipients': {'telegram': 3, 'web': 2}, 'already_sent': True}
    await database.conn.execute('UPDATE race_predictions SET points=21')
    await database.conn.execute("UPDATE users SET archived_at='2026-01-01'")
    await database.conn.commit()
    preview = await service.preview(2026, 16)
    assert preview['recipients'] == {'telegram': 0, 'web': 0}
    with pytest.raises(ValueError, match='Нет доступных'):
        await service.send(2026, 16, preview['fingerprint'], 1)


@pytest.mark.asyncio
async def test_cookie_auth_requires_admin_role_and_csrf(broadcasts, monkeypatch):
    from app.api import admin_api, auth_api
    from app.emailer import MockMailer
    from app.services.auth_service import AuthService

    database, app, client = broadcasts
    monkeypatch.setattr(admin_api, 'db', database)
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper='test-only')
    monkeypatch.setattr(auth_api, 'get_auth_service', lambda: auth)
    await auth.register('broadcast-admin@example.test', 'FormulaOne-2026-Secure')
    session = await auth.verify_email('broadcast-admin@example.test', str(mailer.messages[-1]['code']))
    app.dependency_overrides.clear()
    client.cookies.set('turbotears_session', session.token)
    client.cookies.set('turbotears_csrf', session.csrf_token)
    preview_url = '/api/admin/tools/prediction-results/preview?season=2026&round=16'
    assert (await client.get(preview_url)).status_code == 403
    await database.conn.execute("UPDATE users SET role='admin' WHERE id=?", (session.user['id'],))
    await database.conn.commit()
    preview = (await client.get(preview_url)).json()
    body = {'season': 2026, 'round': 16, 'fingerprint': preview['fingerprint'], 'confirmation': 'ОТПРАВИТЬ'}
    url = '/api/admin/tools/prediction-results/send'
    assert (await client.post(url, json=body)).status_code == 403
    assert await total(database, 'web_notifications') == 0
    assert (await client.post(url, json=body, headers={'X-CSRF-Token': session.csrf_token})).status_code == 200
