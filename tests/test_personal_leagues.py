"""Bot league previews share membership, scoring and subscription rules with the web."""
import json
import time

import httpx
import pytest
import pytest_asyncio

from app.services import prediction_social as social
from app.utils.telegram_presentation import leagues_card


@pytest_asyncio.fixture
async def league_members(db_session):
    for uid, name in [(1, 'Me <pilot>'), (2, 'Leader'), (3, 'Second'), (4, 'Third'), (5, 'Outsider')]:
        await db_session.conn.execute(
            'INSERT INTO users(id,telegram_id,email,email_verified) VALUES(?,?,?,1)',
            (uid, 1000 + uid, f'{uid}@example.test'))
        await db_session.conn.execute('INSERT INTO prediction_profiles(user_id,display_name) VALUES(?,?)', (uid, name))
        for season, points in [(2025, uid * 10), (2026, 60 - uid * 10)]:
            await db_session.conn.execute(
                '''INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,
                   second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
                   first_retirement_driver,safety_car,points,max_points)
                   VALUES(?,?,1,'VER','SECRET','NOR','PIA','LEC','HAM','VER','STR',0,?,37)''',
                (uid, season, points))
    await db_session.conn.commit()
    league = await social.create_league(1, 'Friends <league>')
    await db_session.conn.executemany('INSERT INTO prediction_league_members(league_id,user_id) VALUES(?,?)',
                                    [(league['id'], uid) for uid in (2, 3, 4)])
    await db_session.conn.commit()
    return db_session, league['id']


@pytest.mark.asyncio
async def test_preview_ranks_only_members_and_preserves_requested_season(league_members):
    _, league_id = league_members
    view = await social.personal_league_summaries(1, 2025)
    assert view['total'] == 1
    league = view['leagues'][0]
    assert league['id'] == league_id and league['season'] == 2025
    assert [e['user_id'] for e in league['top']] == [4, 3, 2]
    assert league['own']['place'] == 4 and league['own']['total_points'] == 10
    assert league['participants'] == 4
    assert not any(value in json.dumps(view) for value in ('SECRET', 'invite_token', '@example', 'history'))
    card, fallback = leagues_card(view, 1)
    assert 'Me &lt;pilot&gt; (вы)' in fallback
    assert 'Friends &lt;league&gt;' in fallback
    assert 'Ваше место: #4 · 10 баллов' in fallback
    table = next(block for block in card.blocks if block.type == 'table')
    assert len(table.cells) == 5  # Header, top three and the clicker's separate row.
    with pytest.raises(PermissionError):
        await social.league_scores(5, league_id, 2025)


@pytest.mark.asyncio
@pytest.mark.parametrize('tier', ['На старт', 'Свой стиль', 'Полный газ'])
async def test_all_paid_tiers_get_supporter_league_without_joining(league_members, tier):
    database, _ = league_members
    await database.conn.execute("INSERT INTO boosty_memberships VALUES(1,'turbotears',1,1,?,1)", (tier,))
    await database.conn.execute('INSERT INTO premium_overrides VALUES(2,1,CURRENT_TIMESTAMP)')
    await database.conn.commit()
    view = await social.personal_league_summaries(1, 2025)
    assert view['total'] == 2
    club = view['leagues'][0]
    assert club['id'] == 'supporters'
    assert [e['user_id'] for e in club['top']] == [2, 1]
    assert club['own']['place'] == 2
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM prediction_league_members WHERE user_id=1')).fetchone())[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['expired', 'disabled', 'unverified', 'inactive'])
async def test_inactive_subscription_cannot_appear_as_club_membership(league_members, state):
    database, _ = league_members
    await database.conn.execute("INSERT INTO boosty_memberships VALUES(1,'turbotears',1,1,'На старт',1)")
    if state == 'expired':
        await database.conn.execute("INSERT INTO boosty_membership_terms VALUES(1,'turbotears',?)", (time.time() - 1,))
    elif state == 'disabled':
        await database.conn.execute('INSERT INTO premium_overrides VALUES(1,0,CURRENT_TIMESTAMP)')
    elif state == 'inactive':
        await database.conn.execute('UPDATE boosty_memberships SET active=0 WHERE user_id=1')
    else:
        await database.conn.execute('UPDATE users SET email_verified=0 WHERE id=1')
    await database.conn.commit()
    view = await social.personal_league_summaries(1, 2025)
    assert all(league['id'] != 'supporters' for league in view['leagues'])


@pytest.mark.asyncio
async def test_manual_premium_and_every_private_league_are_accessible_by_pagination(league_members):
    database, _ = league_members
    await database.conn.execute('INSERT INTO premium_overrides VALUES(1,1,CURRENT_TIMESTAMP)')
    await database.conn.commit()
    for index in range(6):
        await social.create_league(1, f'Friends {index}')
    first = await social.personal_league_summaries(1, 2025)
    assert first['total'] == 8 and first['pages'] == 3
    views = [await social.personal_league_summaries(1, 2025, page) for page in range(3)]
    ids = [league['id'] for view in views for league in view['leagues']]
    assert len(ids) == len(set(ids)) == 8 and 'supporters' in ids
    assert (await social.personal_league_summaries(1, 2025, 999))['page'] == 2


@pytest.mark.asyncio
async def test_cup_stays_in_its_own_season_and_excludes_other_rounds(league_members):
    database, league_id = league_members
    await database.conn.execute(
        "UPDATE prediction_leagues SET mode='cup',season=2026,rounds_json=? WHERE id=?",
        (json.dumps([{'round': 1, 'event_name': 'Test GP'}]), league_id))
    await database.conn.commit()
    league = (await social.personal_league_summaries(1, 2025))['leagues'][0]
    assert league['mode'] == 'cup' and league['season'] == 2026
    assert league['own']['total_points'] == 50


@pytest.mark.asyncio
async def test_no_memberships_are_handled_without_a_fake_ranking(db_session):
    await db_session.conn.execute('INSERT INTO users(id,telegram_id) VALUES(1,1001)')
    await db_session.conn.commit()
    view = await social.personal_league_summaries(1, 2025)
    card, text = leagues_card(view, 1)
    assert view['total'] == 0 and view['pages'] == 1
    assert 'Вы пока не состоите в лигах' in text
    assert all(block.type != 'table' for block in card.blocks)


@pytest.mark.asyncio
async def test_full_league_api_keeps_season_and_membership_checks(league_members):
    from app.api.miniapp_api import get_prediction_user_id, web_app
    _, league_id = league_members
    original = web_app.dependency_overrides.copy()
    web_app.dependency_overrides[get_prediction_user_id] = lambda: 1
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app), base_url='http://test') as client:
            response = await client.get(f'/api/predictions/leagues/{league_id}?season=2025')
            assert response.status_code == 200
            assert response.json()['season'] == 2025
            assert response.json()['entries'][0]['user_id'] == 4
            assert response.headers['cache-control'] == 'private, no-store'
            assert (await client.get(f'/api/predictions/leagues/{league_id}?season=0')).status_code == 422
            web_app.dependency_overrides[get_prediction_user_id] = lambda: 5
            assert (await client.get(f'/api/predictions/leagues/{league_id}?season=2025')).status_code == 403
    finally:
        web_app.dependency_overrides.clear()
        web_app.dependency_overrides.update(original)


def test_own_top_three_position_is_not_duplicated_and_zero_is_a_score():
    own = {'user_id': 1, 'display_name': 'Me', 'place': 1, 'total_points': 0}
    view = {'page': 0, 'pages': 1, 'total': 1, 'leagues': [{
        'id': 7, 'name': 'Friends', 'mode': 'season', 'season': 2026,
        'participants': 1, 'top': [own], 'own': own}]}
    card, text = leagues_card(view, 1)
    assert len(next(block for block in card.blocks if block.type == 'table').cells) == 2
    assert 'Ваше место: #1 · 0 баллов' in text
