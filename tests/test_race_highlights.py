"""Invented timing records; no network or Telegram sends."""
from copy import deepcopy

import pytest

from app.services import recap_chronicle as chronicle
from app.services.race_highlights import personalize_recap, select_highlights
from test_recap_chronicle import SESSION, BOUNDARIES, NOW, mock_background, database


def evidence():
    key = SESSION['session_key']
    def position(number, minute, value):
        return dict(session_key=key, driver_number=number, date=f'2026-09-26T11:{minute:02}:00Z', position=value)
    return dict(
        drivers=[dict(session_key=key, driver_number=43, full_name='Favorite Driver', name_acronym='FAV'),
                 dict(session_key=key, driver_number=1, full_name='Other Driver', name_acronym='OTH')],
        overtakes=[dict(session_key=key, date='2026-09-26T11:30:00Z', overtaking_driver_number=43, overtaken_driver_number=1, position=3)],
        positions=[position(43, 20, 4), position(43, 30, 3), position(43, 59, 3),
                   position(1, 20, 3), position(1, 30, 4)],
        laps=[dict(session_key=key, driver_number=n, date_start='2026-09-26T11:29:00Z',
                   lap_duration=100, lap_number=15, is_pit_out_lap=False) for n in (43, 1)],
        results=[dict(session_key=key, driver_number=n, position=p, dnf=False, dns=False, dsq=False) for n, p in ((43, 3), (1, 4))],
        pits=[],
    )


def build(data=None, messages=None):
    data = data or evidence()
    return chronicle.build_chronicle(SESSION, messages or BOUNDARIES, data['drivers'], NOW,
        data['overtakes'], data['pits'], positions=data['positions'], laps=data['laps'], results=data['results'])


def test_pass_is_personal_and_preserved_to_finish():
    rows = build()
    assert len(rows) == 1 and rows[0]['category'] == 'retained_overtake'
    assert rows[0]['driver_code'] == 'FAV'
    assert 'Круг 15:' in rows[0]['title'] and 'обогнал Other Driver' in rows[0]['title']
    assert 'сохранил эту позицию до финиша' in rows[0]['title']
    assert select_highlights(rows, ['fav']) == rows
    assert not select_highlights(rows, ['OTH']) and not select_highlights(rows)
    recap = {'highlight_candidates': rows, 'chronicle': [], 'items': []}
    assert personalize_recap(recap, ['FAV'])['chronicle'] == rows
    assert recap['chronicle'] == []  # Never mutate the shared object.


@pytest.mark.parametrize('case', ['lost', 'improved', 'lost_then_recovered', 'wrong_finish', 'dnf', 'dns', 'dsq',
                                  'other_retired', 'pit_in', 'other_pit_in', 'pit_out', 'other_pit_out',
                                  'near_pit', 'missing_positions', 'missing_laps', 'missing_results',
                                  'wrong_session', 'nonadjacent', 'no_exchange', 'late_exchange', 'missing_flags'])
def test_uncertain_or_unretained_swap_is_never_an_overtake_highlight(case):
    data = evidence()
    if case in {'lost', 'improved', 'lost_then_recovered'}:
        data['positions'].append(dict(data['positions'][1], date='2026-09-26T11:40:00Z', position=2 if case == 'improved' else 4))
    elif case == 'wrong_finish':
        data['results'][0]['position'] = 4
    elif case in {'dnf', 'dns', 'dsq'}:
        data['results'][0][case] = True
    elif case == 'other_retired':
        data['results'][1]['dnf'] = True
    elif case in {'pit_in', 'other_pit_in', 'near_pit'}:
        data['pits'] = [dict(session_key=SESSION['session_key'], driver_number=1 if case == 'other_pit_in' else 43,
                            date='2026-09-26T11:29:30Z' if case == 'near_pit' else '2026-09-26T11:31:00Z',
                            lap_number=14 if case == 'near_pit' else 15)]
    elif case in {'pit_out', 'other_pit_out'}:
        data['laps'][1 if case == 'other_pit_out' else 0]['is_pit_out_lap'] = True
    elif case.startswith('missing_') and case != 'missing_flags':
        data[case.removeprefix('missing_')] = []
    elif case == 'missing_flags':
        del data['results'][0]['dnf']
    elif case == 'wrong_session':
        data['positions'] = [dict(row, session_key=999) for row in data['positions']]
    elif case == 'nonadjacent':
        data['positions'][0]['position'] = 6
    elif case == 'no_exchange':
        data['positions'][4]['position'] = 3
    elif case == 'late_exchange':
        data['positions'][1]['date'] = '2026-09-26T11:31:00Z'
    rows = build(data)
    assert rows and not select_highlights(rows, ['FAV'])
    assert all('обогнал' not in row['title'] for row in rows)


@pytest.mark.parametrize('control', [
    dict(category='SafetyCar', message='SAFETY CAR DEPLOYED'),
    dict(category='Flag', message='RED FLAG', flag='RED', scope='Track'),
    dict(category='Other', message='10 SECOND TIME PENALTY FOR CAR 1'),
])
def test_neutralisation_and_penalty_changes_are_excluded(control):
    row = dict(session_key=SESSION['session_key'], date='2026-09-26T11:29:00Z', **control)
    assert not any(item['category'] == 'retained_overtake' for item in build(messages=[*BOUNDARIES, row]))


@pytest.mark.parametrize('message,expected', [
    ('CAR 43 (FAV) CRASHED AT TURN 6', 'Favorite Driver попал в аварию в повороте 6'),
    ('CAR 43 HIT THE BARRIER', 'Favorite Driver попал в аварию'),
    ('CAR 43 COLLIDED WITH CAR 1 AT TURN 3', 'Favorite Driver столкнулся с Other Driver в повороте 3'),
    ('INCIDENT INVOLVING CARS 43 (FAV) AND 1 (OTH) NOTED - CAUSING A COLLISION', 'столкновении: Favorite Driver, Other Driver'),
    ('CAR 43 RETIRED', None), ('YELLOW FLAG', None),
    ('POSSIBLE COLLISION INVOLVING CAR 43', None),
    ('INCIDENT INVOLVING CAR 43 NOTED - TRACK LIMITS', None),
])
def test_accidents_need_an_explicit_source_statement(message, expected):
    data = evidence()
    data['overtakes'] = []
    row = dict(session_key=SESSION['session_key'], date='2026-09-26T11:30:00Z', category='Other', message=message, lap_number=15)
    rows = build(data, [*BOUNDARIES, row])
    selected = select_highlights(rows)
    if expected:
        assert len(selected) == 1 and expected in selected[0]['title']
        assert selected == select_highlights(rows, ['UNRELATED'])
    else:
        assert not selected


@pytest.mark.parametrize('sanction', ['10 SECOND TIME PENALTY', 'DRIVE THROUGH PENALTY', 'STOP/GO 10 SECONDS PENALTY', 'DISQUALIFICATION'])
def test_penalties_are_general_but_rescinded_penalties_are_removed(sanction):
    data = evidence()
    data['overtakes'] = []
    row = dict(session_key=SESSION['session_key'], date='2026-09-26T11:30:00Z', category='Other', message=f'{sanction} FOR CAR 43')
    rows = build(data, [*BOUNDARIES, row])
    assert len(select_highlights(rows)) == 1 and rows[0]['category'] == 'penalty'
    cancelled = dict(row, date='2026-09-26T11:40:00Z', message=row['message'] + ' RESCINDED')
    assert not select_highlights(build(data, [*BOUNDARIES, row, cancelled]))


async def test_verified_pass_persists_and_readers_do_not_fetch(database, monkeypatch):
    data = evidence()
    fetch = mock_background(monkeypatch)
    async def payload(path, **kwargs):
        mapping = {'drivers':'drivers', 'overtakes':'overtakes', 'pit':'pits', 'position':'positions', 'laps':'laps', 'session_result':'results'}
        return deepcopy(data[mapping[path]]) if path in mapping else BOUNDARIES
    fetch.side_effect = payload
    await chronicle._refresh_recent_race_control()
    fetch.side_effect = AssertionError('Public readers only use SQLite')
    candidates = await chronicle.public_highlight_candidates(2026, 15)
    assert any(row['category'] == 'retained_overtake' and row['driver_code'] == 'FAV' for row in candidates)
    assert not any(row['category'] == 'retained_overtake' for row in select_highlights(candidates))
    assert any(row['category'] == 'retained_overtake' for row in select_highlights(candidates, ['FAV']))
    await database.conn.execute("UPDATE recap_news_articles SET hidden=1 WHERE category='retained_overtake'")
    await database.conn.commit()
    assert not any(row['category'] == 'retained_overtake' for row in await chronicle.public_highlight_candidates(2026, 15))
