import json
from unittest.mock import AsyncMock
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


@pytest.fixture
def historical_review():
    answers = dict.fromkeys(service.PREDICTION_FIELDS)
    answers.update(pole_driver='ANT', winner_driver='ANT', second_driver='RUS',
                   third_driver='HAM', fourth_driver='LEC', fifth_driver='NOR',
                   fastest_lap_driver='HAM', first_retirement_driver='STR', safety_car=0)
    saved = {**answers, 'second_driver': 'HAM', 'third_driver': 'RUS',
             'points': 33, 'max_points': 37, 'breakdown_json': None}
    return saved, answers


@pytest.mark.parametrize('legacy_snapshot', [False, True], ids=['missing-detail', 'recovery-blanked-detail'])
def test_historical_detail_restores_exact_and_near_matches(historical_review, legacy_snapshot):
    saved, answers = historical_review
    if legacy_snapshot:
        items = service.prediction_breakdown(saved, answers, historical=True)
        for item in items:
            item.update(points=None, status='unknown',
                        reason='Историческая разбивка не сохранена; прежний итог не изменён.')
        saved['breakdown_json'] = json.dumps(items)
    before = dict(saved)
    items = {item['key']: item for item in service.historical_prediction_breakdown(saved, answers)}
    assert (items['winner_driver']['status'], items['winner_driver']['points']) == ('exact', 8)
    assert (items['second_driver']['status'], items['second_driver']['points']) == ('partial', 3)
    assert sum(item['points'] for item in items.values()) == 33
    assert saved == before


def test_historical_detail_does_not_guess_missing_position(historical_review):
    saved, answers = historical_review
    saved.update(fifth_driver='ALO', points=30)
    items = {item['key']: item for item in service.historical_prediction_breakdown(saved, answers)}
    assert items['winner_driver']['points'] == 8
    assert items['fifth_driver']['points'] is None
    assert items['fifth_driver']['status'] == 'unknown'
    assert saved['points'] == 30


def test_saved_full_classification_restores_points_outside_top_five(historical_review):
    saved, answers = historical_review
    saved.update(fifth_driver='ALO', points=30)
    answers['race_facts_json'] = json.dumps({'race_positions': {
        'ANT': 1, 'RUS': 2, 'HAM': 3, 'LEC': 4, 'NOR': 5, 'ALO': 7,
    }})
    items = {item['key']: item for item in service.historical_prediction_breakdown(saved, answers)}
    assert (items['fifth_driver']['status'], items['fifth_driver']['points']) == ('partial', 2)
    assert sum(item['points'] for item in items.values()) == 30


def test_reconstructed_detail_never_overrides_different_historical_total(historical_review):
    saved, answers = historical_review
    saved['points'] = 12
    items = service.historical_prediction_breakdown(saved, answers)
    assert all(item['points'] is None and item['status'] == 'unknown' for item in items)
    assert saved['points'] == 12


def test_repair_preserves_individual_saved_awards(historical_review):
    saved, answers = historical_review
    items = service.prediction_breakdown(saved, answers, historical=True)
    original = dict(next(item for item in items if item['key'] == 'fastest_lap_driver'))
    for item in items:
        if item['key'] != 'fastest_lap_driver':
            item.update(points=None, status='unknown',
                        reason='Историческая разбивка не сохранена; прежний итог не изменён.')
    saved['breakdown_json'] = json.dumps(items)
    answers['fastest_lap_driver'] = 'NOR'
    repaired = {item['key']: item for item in service.historical_prediction_breakdown(saved, answers)}
    assert repaired['fastest_lap_driver'] == original
    assert repaired['winner_driver']['points'] == 8


@pytest.mark.asyncio
async def test_unchanged_round_repairs_legacy_review_without_database_writes(db_session, monkeypatch, historical_review):
    from app.services import prediction_recovery as recovery_service
    saved, answers = historical_review
    database = db_session
    monkeypatch.setattr(service, 'db', database)
    monkeypatch.setattr(recovery_service, 'db', database)
    await database.conn.execute('INSERT INTO users(id,telegram_id) VALUES(1,10001)')
    fields = ','.join(service.PREDICTION_FIELDS)
    marks = ','.join('?' for _ in service.PREDICTION_FIELDS)
    legacy = service.prediction_breakdown(saved, answers, historical=True)
    for item in legacy:
        item.update(points=None, status='unknown',
                    reason='Историческая разбивка не сохранена; прежний итог не изменён.')
    snapshot = json.dumps(legacy)
    await database.conn.execute(
        f'INSERT INTO race_predictions(user_id,season,round,{fields},points,max_points,breakdown_json) '
        f'VALUES(1,2026,13,{marks},33,37,?)',
        (*[saved[field] for field in service.PREDICTION_FIELDS], snapshot),
    )
    await database.conn.execute(
        f'INSERT INTO prediction_round_results(season,round,event_name,{fields},max_points) '
        f"VALUES(2026,13,'Test GP',{marks},37)",
        [answers[field] for field in service.PREDICTION_FIELDS],
    )
    await database.conn.commit()
    monkeypatch.setattr(recovery_service, 'get_prediction_race_facts', AsyncMock(return_value={
        key: answers[key] for key in recovery_service.FIELDS
    }))
    assert (await recovery_service.prepare(2026, 13))['state'] == 'unchanged'
    review = await service.get_personal_prediction_review(1, 2026, 13)
    assert review['complete'] and review['points'] == 33
    assert next(item for item in review['items'] if item['key'] == 'winner_driver')['points'] == 8
    persisted = await (await database.conn.execute('SELECT points,max_points,breakdown_json FROM race_predictions')).fetchone()
    assert tuple(persisted) == (33, 37, snapshot)


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
        assert review['race_facts'] == {**answers['_race_facts'], 'race_positions': {'LEC': 4}}
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
