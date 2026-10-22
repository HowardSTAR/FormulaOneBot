"""Title opportunities, joint finish feasibility, countback and durable answers."""
from itertools import permutations, product
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services import championship as title


def entrant(identifier, score, wins=0, seconds=0):
    return {'id': identifier, 'name': identifier, 'points': float(score), 'wins': wins,
            'finishes': [wins, seconds] + [0] * 30}


def scenarios(entries, races=1, sprints=0, **kwargs):
    return title.calculate_candidates(entries, races, sprints, grid_size=kwargs.pop('grid_size', 6), **kwargs)


def test_no_title_question_without_a_mathematical_opportunity():
    assert scenarios([entrant('ANT', 300, 7), entrant('RUS', 290, 5)], races=5) == []


def test_single_candidate_and_exact_points_limits_check_all_rivals():
    candidates = scenarios([entrant('ANT', 350, 10), entrant('RUS', 300, 2), entrant('NOR', 299, 4)], races=2)
    assert [c['id'] for c in candidates] == ['ANT']
    win = next(s for s in candidates[0]['scenarios'] if s['points'] == 25)
    assert {r['id']: (r['max_points'], r['tie_points']) for r in win['rivals']} == {'RUS': (18, None)}
    assert candidates[0]['remaining_points'] == 50


@pytest.mark.parametrize('cars,scores', [(1, [350, 310, 309, 200]), (2, [665, 610, 609, 400])],
                         ids=['drivers', 'constructors'])
def test_conditions_include_all_relevant_rivals_not_only_the_runner_up(cars, scores):
    entries = [entrant(code, score, wins) for code, score, wins in zip('ABCD', scores, [10, 2, 4, 0])]
    candidates = scenarios(entries, races=2, cars=cars, grid_size=8)
    assert [c['id'] for c in candidates] == ['A']
    best = candidates[0]['scenarios'][0]
    assert {r['id'] for r in best['rivals']} == {'B', 'C'}


def test_future_sprint_can_prevent_clinching():
    entries = [entrant('ANT', 350, 10), entrant('RUS', 300, 2)]
    assert scenarios(entries, races=3)
    assert scenarios(entries, races=3, sprints=1) == []


def test_current_sprint_creates_an_opportunity_and_is_included_in_variants():
    entries = [entrant('ANT', 350, 10), entrant('RUS', 300, 2)]
    assert scenarios(entries, races=3, sprints=1) == []
    candidates = scenarios(entries, races=3, sprints=1, has_sprint=True)
    assert [c['id'] for c in candidates] == ['ANT']
    assert candidates[0]['scenarios'][0]['points'] == 33
    assert {'race': [1], 'sprint': [1]} in candidates[0]['scenarios'][0]['finishes']


def test_already_secured_title_has_no_question():
    assert scenarios([entrant('ANT', 400, 10), entrant('RUS', 300, 2)], races=2) == []


def test_finale_can_offer_two_or_more_candidates():
    candidates = scenarios([entrant('ANT', 350, 7), entrant('RUS', 349, 6), entrant('NOR', 345, 5)], races=0)
    assert {c['id'] for c in candidates} == {'ANT', 'RUS', 'NOR'}


def test_team_maximum_is_two_cars_not_twice_the_winners_points():
    entries = [entrant('Mercedes', 600, 9), entrant('McLaren', 530, 4), entrant('Ferrari', 450, 2)]
    candidates = scenarios(entries, races=2, cars=2)
    assert [c['id'] for c in candidates] == ['Mercedes']
    assert candidates[0]['scenarios'][0]['points'] == 43
    assert candidates[0]['remaining_points'] == 86
    assert {'race': [1, 2], 'sprint': []} in candidates[0]['scenarios'][0]['finishes']


def test_team_sprint_has_two_car_maximum_and_all_equal_score_variants():
    candidates = scenarios([entrant('A', 600, 9), entrant('B', 550, 2), entrant('C', 450)],
                           races=1, cars=2, has_sprint=True)
    assert candidates[0]['scenarios'][0]['points'] == 58
    variants = [f['sprint'] for s in candidates[0]['scenarios'] for f in s['finishes'] if title.points(f['sprint'], title.SPRINT) == 13]
    assert [1, 4] in variants and [2, 3] in variants


def test_countback_considers_future_wins_then_seconds():
    a, b = entrant('A', 100, 4, 8), entrant('B', 100, 3, 7)
    assert title.wins_tie(a, b, (), (), 1, 1)
    assert not title.wins_tie(a, b, (), (), 2, 1)
    assert title.wins_tie(a, b, (1,), (), 1, 1)


def test_impossible_equal_points_are_not_advertised_as_a_title_scenario():
    candidates = scenarios([entrant('ANT', 350, 7), entrant('RUS', 315, 7), entrant('NOR', 200)], races=2)
    win = next(s for s in candidates[0]['scenarios'] if s['points'] == 25)
    assert win['rivals'][0]['max_points'] == 8
    assert win['rivals'][0]['tie_points'] is None  # 8 wins versus the rival's potential 9.


def test_full_grid_with_three_finalists_does_not_search_impossible_ties():
    from time import perf_counter
    entries = [entrant(str(i), 350-i if i < 3 else 200, 7-i if i < 3 else 0) for i in range(22)]
    start = perf_counter()
    candidates = scenarios(entries, races=0, has_sprint=True, grid_size=22)
    assert {c['id'] for c in candidates} == {'0', '1', '2'}
    assert perf_counter() - start < 3


def test_constructor_future_one_two_counts_both_places():
    a, b = entrant('A', 100, 4, 7), entrant('B', 100, 3, 7)
    assert not title.wins_tie(a, b, (), (), 1, 2)


def test_2026_equal_race_countback_uses_qualifying():
    a, b = entrant('A', 100, 4), entrant('B', 100, 4)
    a['qualifying'], b['qualifying'] = [5] + [0]*31, [4] + [0]*31
    assert title.wins_tie(a, b, (), (), 0, 1)
    a['qualifying_pending'] = True
    a['qualifying'] = [4] + [0]*31
    assert not title.wins_tie(a, b, (), (), 0, 1)
    assert title.wins_tie(a, b, (), (), 0, 1, possible=True)


def test_single_candidate_is_automatic_but_yes_no_is_explicit():
    context = {'drivers': [entrant('ANT', 350)], 'constructors': []}
    assert title.normalize_answers({'drivers': {'yes': False}}, context)['drivers']['id'] == 'ANT'
    for bad in [None, {}, {'drivers': {'yes': 'false'}}, {'drivers': {'id': 'VER', 'yes': True}}]:
        with pytest.raises(ValueError):
            title.normalize_answers(bad, context)


def test_multiple_candidates_require_selection_and_reject_impossible_team():
    context = {'drivers': [entrant('ANT', 350), entrant('RUS', 349)], 'constructors': []}
    with pytest.raises(ValueError):
        title.normalize_answers({'drivers': {'yes': True}}, context)
    with pytest.raises(ValueError):
        title.normalize_answers({'drivers': {'id': 'RUS', 'yes': False}, 'constructors': {'id': 'X', 'yes': True}}, context)
    assert title.normalize_answers({'drivers': {'id': 'RUS', 'yes': False}}, context)['drivers']['yes'] is False


def test_every_exposed_driver_finish_is_jointly_feasible_against_exhaustive_reference():
    entries = [entrant('A', 90, 3), entrant('B', 95, 2), entrant('C', 94, 1)]
    # Independent enumeration: every subset of finishers in every finishing order.
    sessions = []
    for count in range(1, len(entries) + 1):
        for order in permutations(range(len(entries)), count):
            places = [0] * len(entries)
            for p, i in enumerate(order, 1):
                places[i] = p
            sessions.append(places)
    expected = set()
    for race, sprint in product(sessions, repeat=2):
        scores = [e['points'] + title.points((race[i],), title.RACE) + title.points((sprint[i],), title.SPRINT) for i,e in enumerate(entries)]
        vectors = [title.vector(e, (race[i],)) for i,e in enumerate(entries)]
        best = max(zip(scores, vectors))
        for i, e in enumerate(entries):
            if (scores[i], vectors[i]) == best and sum((scores[j], vectors[j]) == best for j in range(len(entries))) == 1:
                expected.add((e['id'], race[i], sprint[i]))
    actual = {(c['id'], f['race'][0], f['sprint'][0]) for c in scenarios(entries, races=0, has_sprint=True, grid_size=3)
              for s in c['scenarios'] for f in s['finishes']}
    assert actual == expected


def test_team_finish_variants_match_full_six_car_classifications():
    entries = [entrant('A', 100, 3), entrant('B', 95, 2), entrant('C', 0)]
    expected = set()
    for count in range(1, 7):
        for order in permutations(range(6), count):
            finishes = [[0, 0] for _ in entries]
            for place, car in enumerate(order, 1):
                finishes[car // 2][car % 2] = place
            ranks = [(e['points'] + title.points(finishes[i], title.RACE), title.vector(e, finishes[i])) for i, e in enumerate(entries)]
            best = max(ranks)
            if ranks.count(best) != 1:
                continue
            winner = ranks.index(best)
            normal = tuple(sorted(p for p in finishes[winner] if p)) + (0,) * finishes[winner].count(0)
            expected.add((entries[winner]['id'], normal))
    actual = {(c['id'], tuple(f['race'])) for c in scenarios(entries, races=0, cars=2, grid_size=6)
              for s in c['scenarios'] for f in s['finishes']}
    assert actual == expected


def test_notification_is_compact_escaped_and_contains_conditions():
    candidates = scenarios([entrant('<ANT>', 350, 10), entrant('RUS', 300)], races=2)
    text = title.notification_text({'status': 'ok', 'drivers': candidates, 'constructors': []})
    assert '<tg-spoiler>' in text and '&lt;ANT&gt;' in text
    assert 'не более 18' in text and len(text) < 1000
    assert title.notification_text({'status': 'unavailable'}) == ''


@pytest.mark.asyncio
async def test_missing_or_wrong_round_standings_never_offer_title(monkeypatch):
    event = {'round': 22, 'race_start_utc': '2026-11-01T12:00:00Z'}
    monkeypatch.setattr(title, 'get_season_schedule_short_async', AsyncMock(return_value=[{'round': 21}, event]))
    stale = pd.DataFrame([{'driverCode': 'ANT', 'points': 300}])
    stale.attrs['round'] = 20
    monkeypatch.setattr(title, 'get_driver_standings_async', AsyncMock(return_value=stale))
    monkeypatch.setattr(title, 'get_constructor_standings_async', AsyncMock(return_value=stale))
    result = await title._get_context.__wrapped__(2026, 22, 'weekend')
    assert result['status'] == 'unavailable' and not result['drivers']


@pytest.mark.asyncio
async def test_pre_race_conditions_add_confirmed_sprint_once(monkeypatch):
    drivers = pd.DataFrame([
        {'driverCode': code, 'points': score, 'wins': wins, 'constructorId': team}
        for code, score, wins, team in [('ANT',350,10,'mercedes'), ('RUS',300,2,'mercedes'),
                                      ('NOR',299,3,'mclaren'), ('PIA',280,2,'mclaren'),
                                      ('LEC',200,1,'ferrari'), ('HAM',190,1,'ferrari')]])
    teams = pd.DataFrame([{'constructorId': key, 'constructorName': key, 'points': score, 'wins': wins}
                          for key, score, wins in [('mercedes',650,12), ('mclaren',579,5), ('ferrari',390,2)]])
    drivers.attrs['round'] = teams.attrs['round'] = 21
    schedule = [{'round':21}, {'round':22, 'sprint_start_utc':'2026-10-31T12:00:00Z'}, {'round':23}, {'round':24}]
    monkeypatch.setattr(title, 'get_driver_standings_async', AsyncMock(return_value=drivers))
    monkeypatch.setattr(title, 'get_constructor_standings_async', AsyncMock(return_value=teams))
    monkeypatch.setattr(title, '_load_finishes', AsyncMock())
    monkeypatch.setattr(title, 'get_sprint_results_async', AsyncMock(return_value=pd.DataFrame(
        [{'Abbreviation': code, 'Points': 8-i} for i, code in enumerate(drivers['driverCode'])])))
    result = await title._get_context.__wrapped__(2026, 22, 'race', schedule)
    assert result['status'] == 'ok'
    assert result['drivers'][0]['points'] == 358
    assert result['constructors'][0]['points'] == 665
    assert result['drivers'][0]['scenarios'][0]['points'] == 25
    assert result['drivers'][0]['has_sprint'] is False
    assert result['drivers'][0]['remaining_points'] == 50
    assert drivers.iloc[0]['points'] == 350  # Provider snapshots were not mutated.


@pytest.mark.asyncio
async def test_server_saves_false_and_preserves_snapshot_on_reload(api_client):
    from app.db import db
    from app.services.prediction_service import save_prediction_profile, save_user_prediction, get_user_prediction
    from tests.test_predictions import prediction_payload, DRIVERS
    await db.conn.execute('INSERT INTO users(telegram_id) VALUES(234567)')
    user = (await (await db.conn.execute('SELECT id FROM users WHERE telegram_id=234567')).fetchone())[0]
    await db.conn.commit()
    await save_prediction_profile(user, 'Title Tester')
    context = {'status': 'ok', 'drivers': [entrant('ANT', 350)], 'constructors': []}
    await save_user_prediction(user, 2026, 22, {**prediction_payload(), 'championship': {'drivers': {'yes': False}}},
                               allowed_driver_codes=set(DRIVERS), championship_context=context)
    saved = await get_user_prediction(user, 2026, 22)
    import json
    assert json.loads(saved['championship_json'])['drivers'] == {'id': 'ANT', 'name': 'ANT', 'yes': False}
    assert json.loads(saved['championship_context_json'])['drivers'][0]['points'] == 350


@pytest.mark.asyncio
async def test_public_endpoint_exposes_no_saved_choices(api_client, monkeypatch):
    from app.api import miniapp_api
    monkeypatch.setattr(miniapp_api, 'get_prediction_context', AsyncMock(return_value={'status': 'ok', 'season': 2026, 'round': 22}))
    monkeypatch.setattr(title, 'get_championship_context', AsyncMock(return_value={'status': 'ok', 'drivers': [], 'constructors': []}))
    response = await api_client.get('/api/predictions/championship')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'drivers': [], 'constructors': []}
