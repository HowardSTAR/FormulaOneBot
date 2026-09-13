import json
import httpx
import pytest
from app.db import Database
from app.services import prediction_service as service
from app.api.miniapp_api import web_app, get_prediction_user_id


def prediction():
    return {f: (0 if f == 'safety_car' else None if f.startswith('sprint_') else 'LEC') for f in service.PREDICTION_FIELDS}


def test_breakdown_uses_the_same_scoring_engine():
    p = prediction()
    answers = {**p, 'winner_driver':'VER','_race_positions':{'VER':1,'LEC':4}}
    items = service.prediction_breakdown(p,answers)
    assert sum(i['points'] for i in items) == service.calculate_prediction_points(p,answers)
    winner = next(i for i in items if i['key']=='winner_driver')
    assert winner['points'] == 1 and winner['status'] == 'partial'
    assert next(i for i in items if i['key']=='safety_car')['status'] == 'exact'


@pytest.mark.asyncio
async def test_private_review_snapshot_and_old_history(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    try:
        await database.init_tables()
        monkeypatch.setattr(service,'db',database)
        await database.conn.executemany("INSERT INTO users(id,telegram_id) VALUES(?,?)",[(1,10001),(2,10002)])
        p = prediction()
        fields = ','.join(service.PREDICTION_FIELDS)
        marks = ','.join('?' for _ in service.PREDICTION_FIELDS)
        for uid, rnd in [(1,14),(2,14),(2,15)]:
            await database.conn.execute(f"INSERT INTO race_predictions(user_id,season,round,{fields}) VALUES(?,?,?,{marks})",(uid,2026,rnd,*p.values()))
        await database.conn.commit()
        answers = {**p,'_race_positions':{'LEC':4}, '_race_facts': {'source': 'FastF1', 'safety_car': 0}}
        await service.score_prediction_round(2026,14,'Test Grand Prix',answers)
        review = await service.get_personal_prediction_review(1,2026,14)
        assert review['complete']
        assert review['race_facts'] == answers['_race_facts']
        assert sum(i['points'] for i in review['items']) == review['points']
        web_app.dependency_overrides[get_prediction_user_id] = lambda:1
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app),base_url='http://test') as client:
            response = await client.get('/api/predictions/mine/2026/14?user_id=2')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'private, no-store'
            assert (await client.get('/api/predictions/mine/2026/15?user_id=2')).status_code == 404
            assert (await client.get('/api/predictions/mine/2026/99')).status_code == 422
            web_app.dependency_overrides.pop(get_prediction_user_id)
            assert (await client.get('/api/predictions/mine/2026/14')).status_code == 401
        await database.conn.execute("UPDATE race_predictions SET breakdown_json=NULL,winner_driver='NOR' WHERE user_id=1")
        await database.conn.commit()
        legacy = await service.get_personal_prediction_review(1,2026,14)
        assert not legacy['complete']
        assert next(i for i in legacy['items'] if i['key']=='winner_driver')['points'] is None
        # Reproduce the production schema, not just a NULL in the new column.
        await database.conn.execute("ALTER TABLE race_predictions DROP COLUMN breakdown_json")
        await database.conn.commit()
        before = [dict(row) for row in await (await database.conn.execute(
            "SELECT * FROM race_predictions ORDER BY user_id,round"
        )).fetchall()]
        web_app.dependency_overrides[get_prediction_user_id] = lambda:1
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app),base_url='http://test') as client:
            response = await client.get('/api/predictions/mine/2026/14')
            assert response.status_code == 200
            assert response.json() == legacy
            assert response.headers['cache-control'] == 'private, no-store'
            assert (await client.get('/api/predictions/mine/2026/15?user_id=2')).status_code == 404
        # Startup migration must be repeatable and preserve all existing choices/scores.
        await database.init_tables()
        await database.init_tables()
        after = [dict(row) for row in await (await database.conn.execute(
            "SELECT * FROM race_predictions ORDER BY user_id,round"
        )).fetchall()]
        for row in after:
            assert row.pop('breakdown_json') is None
        assert after == before
        assert await service.get_personal_prediction_review(1,2026,14) == legacy
        await service.score_prediction_round(2026,14,'Test Grand Prix',answers)
        assert (await service.get_personal_prediction_review(1,2026,14))['complete']
    finally:
        web_app.dependency_overrides.pop(get_prediction_user_id,None)
        await database.close()
