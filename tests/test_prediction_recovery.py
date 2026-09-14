import asyncio
import json
from unittest.mock import AsyncMock

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
