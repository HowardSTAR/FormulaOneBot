import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.db import Database
from app.services import prediction_recovery as service
from app.api import admin_tools_api as api


@pytest_asyncio.fixture
async def recovery(temp_db_path,monkeypatch):
    database=Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    monkeypatch.setattr(service,'db',database)
    await database.conn.executemany('INSERT INTO users(id,telegram_id) VALUES(?,?)',[(1,101),(2,102)])
    await database.conn.execute("INSERT INTO prediction_round_results(season,round,event_name,winner_driver,max_points) VALUES(2026,14,'Test GP','VER',28)")
    for uid in (1,2):
        await database.conn.execute("INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,first_retirement_driver,safety_car,points,max_points) VALUES(?,2026,14,'VER','VER','NOR','HAM','LEC','PIA',?,?,?,13,28)",
                                   (uid,'HAM' if uid==1 else 'NOR','STR',uid-1))
    await database.conn.execute('INSERT INTO prediction_notification_state(season,round,results_sent) VALUES(2026,14,1)')
    await database.conn.commit()
    fetch=AsyncMock(return_value={'fastest_lap_driver':'HAM','first_retirement_driver':None,'safety_car':0,'source':'FastF1'})
    monkeypatch.setattr(service,'get_prediction_race_facts',fetch)
    yield database,fetch
    await database.close()


@pytest.mark.asyncio
async def test_preview_inert_apply_atomic_idempotent_and_no_broadcast(recovery):
    database,_=recovery
    preview=await service.prepare(2026,14)
    assert [r['delta'] for r in preview['changes']]==[4,0]
    async with service.connection() as conn:
        assert (await service.snapshot(conn,2026,14))['predictions'][0]['points']==13
    first,second=await asyncio.gather(service.apply(preview['id'],99),service.apply(preview['id'],99))
    assert {first['already_applied'],second['already_applied']}=={False,True}
    async with service.connection() as conn:
        state=await service.snapshot(conn,2026,14)
        assert [r['points'] for r in state['predictions']]==[17,13]
        assert all(r['max_points']==32 for r in state['predictions'])
        assert state['actual']['winner_driver']=='VER'
        assert (await (await conn.execute('SELECT results_sent FROM prediction_notification_state')).fetchone())[0]==1
        assert (await (await conn.execute('SELECT COUNT(*) FROM telegram_delivery_batches')).fetchone())[0]==0
        assert (await (await conn.execute('SELECT COUNT(*) FROM web_notifications')).fetchone())[0]==0
        record=await (await conn.execute('SELECT * FROM prediction_recovery')).fetchone()
        assert record['applied_by']==99 and json.loads(record['before_json'])['predictions'][0]['points']==13
    assert (await service.prepare(2026,14))['state']=='waiting'


@pytest.mark.asyncio
async def test_recovery_credits_each_driver_in_first_retirement_group(recovery):
    database, fetch = recovery
    await database.conn.execute("UPDATE race_predictions SET first_retirement_driver='HAM' WHERE user_id=2")
    await database.conn.commit()
    fetch.return_value = {'fastest_lap_driver': None, 'first_retirement_driver': 'HAM',
                          'first_retirement_drivers': ['HAM', 'STR'], 'safety_car': None,
                          'source': 'OpenF1'}
    preview = await service.prepare(2026, 14)
    assert preview['state'] == 'ready'
    assert [row['delta'] for row in preview['changes']] == [2, 2]
    assert all(row['new_max'] == 30 for row in preview['changes'])
    await service.apply(preview['id'], 99)
    async with service.connection() as conn:
        saved = await service.snapshot(conn, 2026, 14)
    assert json.loads(saved['actual']['race_facts_json'])['first_retirement_drivers'] == ['HAM', 'STR']
    assert (await service.prepare(2026, 14))['state'] == 'waiting'


@pytest.mark.asyncio
async def test_recovery_can_extend_existing_first_retirement_to_tie(recovery):
    database, fetch = recovery
    await database.conn.execute("UPDATE prediction_round_results SET first_retirement_driver='STR',max_points=30 WHERE season=2026 AND round=14")
    await database.conn.execute("UPDATE race_predictions SET max_points=30,points=15 WHERE user_id=1")
    await database.conn.execute("UPDATE race_predictions SET max_points=30,first_retirement_driver='HAM' WHERE user_id=2")
    await database.conn.commit()
    fetch.return_value = {'first_retirement_driver': 'HAM', 'first_retirement_drivers': ['HAM', 'STR'],
                          'source': 'OpenF1'}
    preview = await service.prepare(2026, 14)
    assert preview['state'] == 'ready'
    assert preview['tie_expansion'] == ['HAM', 'STR']
    assert [row['delta'] for row in preview['changes']] == [0, 2]
    await service.apply(preview['id'], 99)
    assert (await service.prepare(2026, 14))['state'] == 'waiting'


@pytest.mark.asyncio
async def test_stale_preview_rejected(recovery):
    database,_=recovery
    preview=await service.prepare(2026,14)
    await database.conn.execute('UPDATE race_predictions SET points=14 WHERE user_id=1')
    await database.conn.commit()
    with pytest.raises(ValueError,match='изменились'):
        await service.apply(preview['id'],99)
    assert (await service.history())[0]['state']=='stale'


@pytest.mark.asyncio
async def test_unavailable_data_never_zeros_results_and_background_does_not_apply(recovery):
    _,fetch=recovery
    fetch.return_value={'note':'offline'}
    await service.refresh_missing()
    await service.refresh_missing()
    fetch.assert_awaited_once()
    history=await service.history()
    assert history[0]['state']=='waiting'
    assert history[0]['changes'][0]['new_points']==13
    with pytest.raises(ValueError,match='Нет новых'):
        await service.apply(history[0]['id'],99)


@pytest.mark.asyncio
async def test_conflicting_sources_cannot_be_applied(recovery):
    _, fetch = recovery
    fetch.return_value = {
        'fastest_lap_driver': None, 'first_retirement_driver': 'STR',
        'safety_car': 0, 'source': 'FastF1 + OpenF1',
        'conflicts': ['fastest_lap_driver'],
    }
    preview = await service.prepare(2026, 14)
    assert preview['state'] == 'conflict'
    assert preview['conflict'] is True
    with pytest.raises(ValueError, match='Нет новых'):
        await service.apply(preview['id'], 99)


@pytest.mark.asyncio
async def test_admin_confirmation_and_auth(recovery):
    app=FastAPI();app.include_router(api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.get('/api/admin/tools/prediction-recovery')).status_code in {401,403}
        app.dependency_overrides[api.require_admin_session]=lambda:api.AdminContext(id=99,role='admin')
        response=await client.post('/api/admin/tools/prediction-recovery/preview',json={'season':2026,'round':14})
        assert response.status_code==200
        url=f"/api/admin/tools/prediction-recovery/{response.json()['id']}/apply"
        assert (await client.post(url,json={'confirmation':''})).status_code==422
        assert (await client.post(url,json={'confirmation':'ПЕРЕСЧИТАТЬ'})).status_code==200
        assert (await client.post('/api/admin/tools/prediction-recovery/preview',json={'season':2026,'round':99})).status_code==422


@pytest.mark.asyncio
async def test_batch_scope_contains_only_calculated_rounds(recovery):
    app = FastAPI(); app.include_router(api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/admin/tools/prediction-recovery/rounds?season=2026')).status_code in {401, 403}
        app.dependency_overrides[api.require_admin_session] = lambda: api.AdminContext(id=99, role='admin')
        response = await client.get('/api/admin/tools/prediction-recovery/rounds?season=2026')
        assert response.status_code == 200
        assert [(row['season'], row['round']) for row in response.json()['rounds']] == [(2026, 14)]


@pytest.mark.asyncio
async def test_complete_round_without_new_facts_is_not_waiting(recovery):
    database, fetch = recovery
    await database.conn.execute("UPDATE prediction_round_results SET fastest_lap_driver='HAM',first_retirement_driver='STR',safety_car=0,max_points=34 WHERE season=2026 AND round=14")
    await database.conn.commit()
    fetch.return_value = {'fastest_lap_driver': 'HAM', 'first_retirement_driver': 'STR',
                          'first_retirement_drivers': ['STR'], 'safety_car': 0, 'source': 'OpenF1'}
    assert (await service.prepare(2026, 14))['state'] == 'unchanged'


@pytest.mark.asyncio
async def test_updated_results_require_separate_admin_confirmation(recovery):
    _, fetch = recovery
    fetch.return_value = {
        'fastest_lap_driver': 'HAM', 'first_retirement_driver': 'STR',
        'safety_car': 0, 'source': 'FastF1',
    }
    preview = await service.prepare(2026, 14)
    app = FastAPI(); app.include_router(api.router)
    url = f"/api/admin/tools/prediction-recovery/{preview['id']}/notify"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post(url, json={'confirmation': 'ОТПРАВИТЬ'})).status_code in {401, 403}
        app.dependency_overrides[api.require_admin_session] = lambda: api.AdminContext(id=99, role='admin')
        assert (await client.post(url, json={'confirmation': 'ОТПРАВИТЬ'})).status_code == 409
        await service.apply(preview['id'], 99)
        assert (await client.post(url, json={'confirmation': ''})).status_code == 422
        with patch('app.services.prediction_notifications.queue_verified_result_update', new_callable=AsyncMock, return_value=2) as queue:
            response = await client.post(url, json={'confirmation': 'ОТПРАВИТЬ'})
        assert response.status_code == 200
        assert response.json()['queued'] == 2
        queue.assert_awaited_once_with(2026, 14, 'Test GP')


@pytest.mark.asyncio
async def test_manual_preview_requires_explicit_apply_and_preserves_evidence(recovery):
    database, fetch = recovery
    values = {'fastest_lap_driver':'HAM', 'first_retirement_drivers':['STR'], 'safety_car':0}
    urls = {key:f'https://www.formula1.com/{key}' for key in service.FIELDS}
    preview = await service.prepare_manual(2026, 14, values, urls,
                                           'Официальный протокол и отчёт гонки.', 99)
    fetch.assert_not_awaited()
    assert preview['state'] == 'ready'
    assert [row['delta'] for row in preview['changes']] == [6, 2]
    assert all(row['new_max'] == 34 for row in preview['changes'])
    async with service.connection() as conn:
        saved = await service.snapshot(conn, 2026, 14)
        assert saved['actual']['fastest_lap_driver'] is None
        assert saved['predictions'][0]['points'] == 13
    with pytest.raises(ValueError, match='только администратор'):
        await service.apply(preview['id'], 100)
    assert (await service.apply(preview['id'], 99))['already_applied'] is False
    assert (await service.apply(preview['id'], 99))['already_applied'] is True
    async with service.connection() as conn:
        saved = await service.snapshot(conn, 2026, 14)
        assert [row['points'] for row in saved['predictions']] == [19, 15]
        assert saved['actual']['safety_car'] == 0
        facts = json.loads(saved['actual']['race_facts_json'])
        assert facts['source_urls'] == urls
        assert set(facts['field_sources'].values()) == {'Ручное подтверждение'}
        assert 'manual_evidence' not in facts and 'prepared_by' not in facts
        actions = await (await conn.execute("SELECT action FROM admin_audit_log WHERE action LIKE 'prediction_recovery.manual_%' ORDER BY id")).fetchall()
        assert [row['action'] for row in actions] == ['prediction_recovery.manual_preview', 'prediction_recovery.manual_apply']
        assert (await (await conn.execute('SELECT results_sent FROM prediction_notification_state')).fetchone())[0] == 1
        assert (await (await conn.execute('SELECT COUNT(*) FROM telegram_delivery_batches')).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_manual_conflict_does_not_replace_confirmed_fact(recovery):
    database, _ = recovery
    await database.conn.execute("UPDATE prediction_round_results SET fastest_lap_driver='HAM',max_points=30 WHERE season=2026 AND round=14")
    await database.conn.commit()
    preview = await service.prepare_manual(2026, 14, {'fastest_lap_driver':'NOR'},
                                           {'fastest_lap_driver':'https://www.formula1.com/results'},
                                           'Исправление по официальной таблице.', 99)
    assert preview['state'] == 'conflict'
    with pytest.raises(ValueError, match='Нет новых'):
        await service.apply(preview['id'], 99)
    async with service.connection() as conn:
        assert (await service.snapshot(conn, 2026, 14))['actual']['fastest_lap_driver'] == 'HAM'


@pytest.mark.asyncio
async def test_manual_confirmation_can_extend_first_retirement_tie(recovery):
    database, _ = recovery
    await database.conn.execute("UPDATE prediction_round_results SET first_retirement_driver='STR',max_points=30 WHERE season=2026 AND round=14")
    await database.conn.execute("UPDATE race_predictions SET first_retirement_driver='HAM',max_points=30 WHERE user_id=2")
    await database.conn.commit()
    preview = await service.prepare_manual(2026, 14,
                                           {'first_retirement_drivers':['HAM','STR']},
                                           {'first_retirement_driver':'https://www.formula1.com/report'},
                                           'Оба пилота сошли одновременно после контакта.', 99)
    assert preview['state'] == 'ready'
    assert preview['tie_expansion'] == ['HAM', 'STR']
    assert [row['delta'] for row in preview['changes']] == [0, 2]
    await service.apply(preview['id'], 99)
    async with service.connection() as conn:
        saved = await service.snapshot(conn, 2026, 14)
    assert sorted(json.loads(saved['actual']['race_facts_json'])['first_retirement_drivers']) == ['HAM', 'STR']


@pytest.mark.asyncio
async def test_manual_preview_api_validates_sources_and_auth(recovery):
    app = FastAPI(); app.include_router(api.router)
    url = '/api/admin/tools/prediction-recovery/manual-preview'
    payload = {'season':2026,'round':14,'fastest_lap_driver':'ham',
               'fastest_lap_url':'https://www.formula1.com/results','reason':'Официальная таблица быстрейших кругов.'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.post(url,json=payload)).status_code in {401,403}
        app.dependency_overrides[api.require_admin_session] = lambda: api.AdminContext(id=99,role='admin')
        for invalid in (
            {**payload,'fastest_lap_url':None},
            {**payload,'fastest_lap_url':'http://example.com/results'},
            {**payload,'first_retirement_drivers':['STR','STR'],'first_retirement_url':'https://www.formula1.com/report'},
            {**payload,'fastest_lap_driver':'???'},
            {**payload,'reason':'          '},
            {**payload,'season':2026,'round':40},
        ):
            expected = 409 if invalid['round'] == 40 else 422
            assert (await client.post(url,json=invalid)).status_code == expected
        response = await client.post(url,json=payload)
        assert response.status_code == 200
        assert response.json()['additions']['fastest_lap_driver'] == 'HAM'
        assert response.json()['manual_evidence']['urls']['fastest_lap_driver'] == payload['fastest_lap_url']
