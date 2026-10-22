"""Deterministic title-clinching conditions, never probability estimates.

Normal, full-distance scoring from 2025 onwards. All rivals are checked;
Sprint points do not enter the race-finish countback. A future points tie
requires the rival to take every remaining maximum, fixing its countback.
"""
import asyncio
import html
import logging
import math
from datetime import datetime, timezone
from functools import lru_cache
from itertools import combinations

import httpx
import pandas as pd

from app.f1_data import (cache_result, get_driver_standings_async,
                         get_constructor_standings_async, get_season_schedule_short_async,
                         get_sprint_results_async)
from app.services.prediction_history import archive

log = logging.getLogger(__name__)
RACE = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
SPRINT = (8, 7, 6, 5, 4, 3, 2, 1)
COMPETITIONS = (('drivers', 1), ('constructors', 2))
NOTE = ('Расчёт для полного начисления очков по действующему календарю. '
        'Учитываются все соперники и спринты. Равенство очков решается по победам, '
        'затем вторым, третьим и следующим местам в гонках; в сезоне 2026 — далее по квалификациям. '
        'При сокращении дистанции, отмене сессии или штрафах условия пересчитываются.')


def utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def points(positions, scale):
    return sum(scale[p - 1] for p in positions if 0 < p <= len(scale))


def maximum_points(cars, races=1, sprints=0):
    return sum(RACE[:cars]) * races + sum(SPRINT[:cars]) * sprints


def sprint_event(event):
    return bool(event.get('sprint_start_utc') or event.get('sprint_quali_start_utc'))


def active_events(schedule):
    return [e for e in schedule if not e.get('is_testing') and not e.get('is_cancelled')]


def secured(candidate, rivals, races, sprints, cars):
    remaining = maximum_points(cars, races, sprints)
    return all(candidate['points'] > rival['points'] + remaining or
               (candidate['points'] == rival['points'] + remaining and
                wins_tie(candidate, rival, (), (), races, cars)) for rival in rivals)


def can_clinch(candidate, rivals, available, remaining):
    return all(candidate['points'] + available >= rival['points'] + remaining for rival in rivals)


def compatible(first, second):
    return not (set(first) - {0}) & (set(second) - {0})


@lru_cache(maxsize=16)
def outcomes(cars, size, sprint=False):
    # 0 denotes an unclassified car; duplicate nonzero places are impossible.
    places = list(range(1, (min(size, 8) if sprint else size) + 1))
    if cars == 1:
        return [(p,) for p in places] + [(0,)]
    return list(combinations(places, 2)) + [(p, 0) for p in places] + [(0, 0)]


@lru_cache(maxsize=16)
def attainable_scores(cars, size, has_sprint):
    race_scores = {points(p, RACE) for p in outcomes(cars, size)}
    sprint_scores = {points(p, SPRINT) for p in outcomes(cars, size, True)} if has_sprint else {0}
    return sorted({r + s for r in race_scores for s in sprint_scores})


def vector(entry, positions=(), future_races=0, cars=1):
    counts = list(entry.get('finishes') or [entry.get('wins', 0)])
    counts += [0] * (32 - len(counts))
    for p in positions:
        if p:
            counts[p - 1] += 1
    counts[0] += future_races
    if cars == 2:
        counts[1] += future_races
    return tuple(counts)


def wins_tie(candidate, rival, own_places, rival_places, future_races, cars, *, possible=False):
    own, other = vector(candidate, own_places), vector(rival, rival_places, future_races, cars)
    # Without the complete archive only a strict difference in wins is proof.
    if candidate.get('finishes') is None or rival.get('finishes') is None:
        return own[0] > other[0]
    if own != other:
        return own > other
    if candidate.get('qualifying') is None or rival.get('qualifying') is None:
        return False
    pending = possible and candidate.get('qualifying_pending', False)
    return vector({'finishes': candidate['qualifying']}, (1, 2) if pending and cars == 2 else (1,) if pending else ()) > vector({'finishes': rival['qualifying']}, future_races=future_races, cars=cars)


def _possible(candidate, rivals, own_race, own_sprint, limits, future_races, cars):
    """Find a jointly possible classification, rather than testing rivals in isolation.

    Only positions before the candidate (and at least a winner) need filling:
    every other car may retire. A slot belongs to at most one driver, or to
    at most two cars of each constructor, independently in each session.
    """
    own_points = points(own_race, RACE) + points(own_sprint, SPRINT)
    maximum = maximum_points(cars, sprints=int(bool(own_sprint)))
    constrained = [r for r in rivals if candidate['points'] + own_points - r['points'] - limits <= maximum]
    free_cars = (len(rivals) - len(constrained)) * cars
    rivals = constrained
    slots = []
    for is_sprint, own in [(False, own_race), (True, own_sprint)]:
        if is_sprint and not own:
            continue
        required = [p for p in range(1, max(max(own), 1) + 1) if p not in own]
        # Unrestricted rivals can fill the highest places. Giving contenders
        # the remaining lowest places is always their most favourable outcome.
        needed = max(0, len(required) - free_cars)
        slots.extend((is_sprint, p) for p in required[-needed:] if needed)
    scores = [0] * len(rivals)
    race_places, sprint_places = [[] for _ in rivals], [[] for _ in rivals]
    def valid(index):
        boundary = candidate['points'] + own_points - rivals[index]['points'] - limits
        if scores[index] < boundary:
            return True
        return scores[index] == boundary and wins_tie(candidate, rivals[index], own_race,
                                                       race_places[index], future_races, cars, possible=True)
    if not all(valid(i) for i in range(len(rivals))):
        return False
    # Upper bounds only: granting a rival more points/finishes cannot help.
    def fill(index):
        if index == len(slots):
            return all(valid(i) for i in range(len(rivals)))
        is_sprint, place = slots[index]
        collection = sprint_places if is_sprint else race_places
        gain = points((place,), SPRINT if is_sprint else RACE)
        order = sorted(range(len(rivals)), key=lambda i: rivals[i]['points'] + scores[i])
        seen = set()
        for i in order:
            signature = (rivals[i]['points'], tuple(rivals[i].get('finishes') or [rivals[i]['wins']]),
                         tuple(rivals[i].get('qualifying') or []),
                         scores[i], tuple(race_places[i]), tuple(sprint_places[i]))
            if signature in seen or len(collection[i]) >= cars:
                continue
            seen.add(signature)
            boundary = candidate['points'] + own_points - rivals[i]['points'] - limits
            if scores[i] + gain > boundary:
                continue
            scores[i] += gain
            collection[i].append(place)
            if valid(i) and fill(index + 1):
                return True
            collection[i].pop()
            scores[i] -= gain
        return False
    return fill(0)


def calculate_candidates(entries, future_races, future_sprints, *, has_sprint=False, cars=1, grid_size=22):
    """Return every attainable candidate score and the corresponding rival caps.

    Each scenario includes its exact race/Sprint places and point caps; at
    equality its countback must beat the rival's maximum future results.
    """
    if len(entries) < 2:
        return []
    later = maximum_points(cars, future_races, future_sprints)
    current_max = maximum_points(cars, sprints=int(has_sprint))
    score_options = attainable_scores(cars, grid_size, has_sprint)
    race_options = outcomes(cars, grid_size)
    sprint_options = outcomes(cars, grid_size, True) if has_sprint else [()]
    race_by_score = {}
    for places in race_options:
        race_by_score.setdefault(points(places, RACE), []).append(places)
    rival_sprint_scores = {own: {points(other, SPRINT) for other in sprint_options if compatible(own, other)}
                           for own in sprint_options}
    rival_vectors = {r['id']: {places: vector(r, places, future_races, cars) for places in race_options}
                     for r in entries}

    def tie_available(candidate, rival, own_race, own_sprint, boundary):
        own_vector = vector(candidate, own_race)
        if own_vector[0] < rival['wins'] + future_races:
            return False
        for sprint_score in rival_sprint_scores[own_sprint]:
            for rival_race in race_by_score.get(boundary - sprint_score, []):
                if not compatible(own_race, rival_race):
                    continue
                other_vector = rival_vectors[rival['id']][rival_race]
                if candidate.get('finishes') is not None and rival.get('finishes') is not None and own_vector != other_vector:
                    if own_vector > other_vector:
                        return True
                elif wins_tie(candidate, rival, own_race, rival_race, future_races, cars, possible=True):
                    return True
        return False

    result = []
    for candidate in entries:
        rivals = [r for r in entries if r['id'] != candidate['id']]
        if not can_clinch(candidate, rivals, current_max, later):
            continue
        # A title secured before this prediction window is never a question.
        if secured(candidate, rivals, future_races + 1, future_sprints + int(has_sprint), cars):
            continue
        groups = {}
        for race_places in race_options:
            race_points = points(race_places, RACE)
            for sprint_places in sprint_options:
                earned = race_points + points(sprint_places, SPRINT)
                if not can_clinch(candidate, rivals, earned, later) or not _possible(candidate, rivals, race_places, sprint_places, later, future_races, cars):
                    continue
                caps = []
                for rival in rivals:
                    boundary = float(candidate['points'] + earned - later - rival['points'])
                    # All equal-point classifications are explicitly described
                    # by the countback condition, not treated as automatic wins.
                    strict = max((p for p in score_options if p < boundary), default=-1)
                    if strict < current_max:
                        caps.append({'id': rival['id'], 'name': rival['name'], 'points': rival['points'],
                                     'max_points': min(strict, current_max),
                                     'tie_points': boundary if boundary in score_options and
                                     tie_available(candidate, rival, race_places, sprint_places, boundary) else None})
                group = groups.setdefault(earned, {'points': earned, 'rivals': caps, 'finishes': []})
                for saved_cap, current_cap in zip(group['rivals'], caps):
                    if current_cap['tie_points'] is not None:
                        saved_cap['tie_points'] = current_cap['tie_points']
                group['finishes'].append({'race': list(race_places), 'sprint': list(sprint_places)})
        if groups:
            result.append({**candidate, 'scenarios': [groups[k] for k in sorted(groups, reverse=True)],
                           'remaining_points': later, 'future_races': future_races,
                           'future_sprints': future_sprints, 'has_sprint': has_sprint})
    return result


def _entries(frame, kind):
    rows = []
    for row in frame.to_dict('records'):
        identifier = str(row.get('driverCode') if kind == 'drivers' else row.get('constructorId') or '')
        name = ' '.join(str(row.get(k) or '') for k in ('givenName', 'familyName')).strip() if kind == 'drivers' else str(row.get('constructorName') or '')
        value = float(row['points'])
        if not identifier or identifier == 'None' or not math.isfinite(value) or value < 0:
            raise ValueError('Incomplete championship standings')
        rows.append({'id': identifier, 'name': name or identifier, 'points': value,
                     'wins': int(row.get('wins') or 0), 'finishes': None})
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate championship entrants')
    return rows


async def _finish_counts(client, season, session, expected):
    archive_rows = await archive(client, season, session, datetime.now(timezone.utc).timestamp())
    races = [r for r in archive_rows if int(r['round']) in expected]
    if len(races) != len(expected) or {int(r['round']) for r in races} != expected:
        raise ValueError(f'Incomplete {session} countback archive')
    counts = {'drivers': {}, 'constructors': {}}
    field = 'Results' if session == 'race' else 'QualifyingResults'
    for race in races:
        rows = race.get(field) or []
        if not rows:
            raise ValueError(f'Empty {session} classification')
        for row in rows:
            position = int(row['position'])
            if not 1 <= position <= 32:
                raise ValueError('Invalid countback position')
            for kind, identifier in [('drivers', row['Driver'].get('code')),
                                     ('constructors', row['Constructor']['constructorId'])]:
                counts[kind].setdefault(identifier, [0] * 32)[position - 1] += 1
    return counts


async def _load_finishes(season, before_round, schedule, drivers, teams, *, qualifying_pending=False, qualifying_round=None):
    events = active_events(schedule)
    expected = {int(e['round']) for e in events if 0 < int(e.get('round') or 0) < before_round}
    groups = [('drivers', drivers), ('constructors', teams)]
    async with httpx.AsyncClient(timeout=12) as client:
        counts = await _finish_counts(client, season, 'race', expected)
        q_counts = None
        if season >= 2026:
            through = qualifying_round if qualifying_round is not None else before_round - 1
            q_expected = {int(e['round']) for e in events if 0 < int(e.get('round') or 0) <= through}
            q_counts = await _finish_counts(client, season, 'qualifying', q_expected)
    for kind, entries in groups:
        for entry in entries:
            tally = counts[kind].get(entry['id'], [0] * 32)
            if tally[0] != entry['wins']:
                raise ValueError('Countback and standings disagree')
            entry['finishes'] = tally
            if q_counts is not None:
                entry['qualifying'] = q_counts[kind].get(entry['id'], [0] * 32)
                entry['qualifying_pending'] = qualifying_pending


@cache_result(ttl=60, key_prefix='championship_v1')
async def _get_context(season, round_num, phase, schedule_override=None):
    empty = {'status': 'unavailable', 'drivers': [], 'constructors': [], 'note': NOTE}
    if season < 2025 or round_num <= 1:
        return {**empty, 'status': 'not_applicable'}
    try:
        schedule = schedule_override if schedule_override is not None else await get_season_schedule_short_async(season) or []
        schedule = active_events(schedule)
        event = next(e for e in schedule if int(e['round']) == round_num)
        if phase == 'auto':
            sprint_at = utc(event.get('sprint_start_utc'))
            quali_at = utc(event.get('quali_start_utc'))
            boundary = sprint_at or quali_at
            phase = 'race' if boundary and datetime.now(timezone.utc) >= boundary else 'weekend'
        previous = max((int(e['round']) for e in schedule if int(e['round']) < round_num), default=0)
        if not previous:
            return {**empty, 'status': 'not_applicable'}
        driver_frame, team_frame = await asyncio.gather(get_driver_standings_async(season, previous),
                                                       get_constructor_standings_async(season, previous))
        # Never substitute a stale/latest table for the requested pre-event round.
        if any(f is None or f.empty or f.attrs.get('round') != previous for f in (driver_frame, team_frame)):
            return empty
        drivers, teams = _entries(driver_frame, 'drivers'), _entries(team_frame, 'constructors')
        sprint_pending = sprint_event(event)
        if sprint_pending and phase == 'race':
            sprint = await get_sprint_results_async(season, round_num)
            if sprint is None or sprint.empty or 'Points' not in sprint:
                return empty
            scores = pd.to_numeric(sprint['Points'], errors='coerce')
            if scores.isna().any() or not scores.gt(0).any() or 'DataComplete' in sprint and not sprint['DataComplete'].all():
                return empty
            code_key = next(k for k in ('Abbreviation', 'driverCode', 'DriverCode') if k in sprint)
            driver_map = {e['id']: e for e in drivers}
            team_map = {str(r['driverCode']): str(r['constructorId']) for r in driver_frame.to_dict('records')}
            by_team = {e['id']: e for e in teams}
            for (_, row), gain in zip(sprint.iterrows(), scores):
                if row[code_key] not in driver_map or team_map.get(row[code_key]) not in by_team:
                    return empty
                driver_map[row[code_key]]['points'] += float(gain)
                by_team[team_map[row[code_key]]]['points'] += float(gain)
            sprint_pending = False
        future = [e for e in schedule if int(e['round']) > round_num]
        future_sprints = sum(sprint_event(e) for e in future)
        # Cheap upper-bound test avoids fetching the archive during most of a season.
        possible = any(can_clinch(c, [r for r in entries if r != c],
                                  maximum_points(cars, sprints=int(sprint_pending)),
                                  maximum_points(cars, len(future), future_sprints))
                       for entries, cars in [(drivers, 1), (teams, 2)] for c in entries)
        if not possible:
            return {**empty, 'status': 'ok'}
        # Missing tie-break evidence must not manufacture a mathematical chance.
        await _load_finishes(season, round_num, schedule, drivers, teams,
                             qualifying_pending=phase != 'race', qualifying_round=round_num if phase == 'race' else round_num - 1)
        driver_candidates, team_candidates = await asyncio.gather(
            asyncio.to_thread(calculate_candidates, drivers, len(future), future_sprints,
                              has_sprint=sprint_pending, grid_size=2 * len(teams)),
            asyncio.to_thread(calculate_candidates, teams, len(future), future_sprints,
                              has_sprint=sprint_pending, cars=2, grid_size=2 * len(teams)))
        return {'status': 'ok', 'drivers': driver_candidates, 'constructors': team_candidates,
                'note': NOTE, 'season': season, 'round': round_num, 'phase': phase,
                'scope': 'Уикенд, включая спринт' if sprint_pending else 'Основная гонка',
                'future_races': len(future), 'future_sprints': future_sprints}
    except Exception as exc:
        log.warning('Championship context %s/%s unavailable: %s', season, round_num, type(exc).__name__)
        return empty


async def get_championship_context(season, round_num, *, phase='weekend', schedule=None):
    return await _get_context(int(season), int(round_num), phase, schedule)


def normalize_answers(payload, context):
    answers = {}
    for kind, _ in COMPETITIONS:
        candidates = context.get(kind) or []
        answer = (payload or {}).get(kind)
        if not candidates:
            if answer is not None:
                raise ValueError('Прогноз на титул недоступен: обновите условия этапа')
            continue
        if not isinstance(answer, dict) or type(answer.get('yes')) is not bool:
            raise ValueError('Для прогноза на титул выберите Да или Нет')
        identifier = candidates[0]['id'] if len(candidates) == 1 else answer.get('id')
        candidate = next((c for c in candidates if c['id'] == identifier), None)
        if not candidate or answer.get('id') not in (None, identifier):
            raise ValueError('Выберите участника с математическим шансом на титул')
        answers[kind] = {'id': identifier, 'name': candidate['name'], 'yes': answer['yes']}
    return answers


def scenario_text(candidate, scenario):
    own = f"{candidate['name']}: набрать {scenario['points']:g} очк."
    limits = []
    for rival in scenario['rivals']:
        cap = rival['max_points']
        text = f"{rival['name']} — не более {cap:g} очк." if cap >= 0 else f"{rival['name']} — только равенство очков с преимуществом по местам"
        if rival['tie_points'] is not None and cap >= 0:
            text += f"; {rival['tie_points']:g} допустимо при преимуществе по местам"
        limits.append(text)
    return own + ('; ' + '; '.join(limits) if limits else ' — независимо от очков соперников')


def notification_text(context):
    if context.get('status') != 'ok':
        return ''
    lines = []
    for kind, label in [('drivers', 'Чемпион мира'), ('constructors', 'Кубок конструкторов')]:
        for candidate in context.get(kind) or []:
            lines.append(f"{label}: {candidate['name']} ({candidate['points']:g} очк.).")
            # One concrete scenario; complete point/finish variants stay in the app.
            scenario = scenario_text(candidate, candidate['scenarios'][0])
            if len(html.escape('\n'.join(lines + [scenario]))) <= 2500:
                lines.append(scenario)
    if not lines:
        return ''
    return ('\n🏆 Титул может решиться на этом этапе\n'
            '<tg-spoiler>' + html.escape('\n'.join(lines)) + '</tg-spoiler>\n'
            'Все варианты — в прогнозе, раздел «Условия титула».\n')


async def enrich_event(event, season, *, phase='race', schedule=None):
    if event.get('is_testing') or not event.get('round'):
        return event
    sprint_at = utc(event.get('sprint_start_utc'))
    if phase == 'race' and sprint_at and datetime.now(timezone.utc) < sprint_at:
        phase = 'weekend'
    return {**event, 'championship': await get_championship_context(season, event['round'], phase=phase, schedule=schedule)}


@cache_result(ttl=300, key_prefix='confirmed_titles_v1')
async def confirmed_titles(season, round_num):
    """Post-event facts. Missing/older standings mean pending, never a 'No'."""
    try:
        schedule = active_events(await get_season_schedule_short_async(season) or [])
        frames = await asyncio.gather(get_driver_standings_async(season, round_num),
                                      get_constructor_standings_async(season, round_num))
        if any(f is None or f.empty or f.attrs.get('round') != round_num for f in frames):
            return None
        drivers, teams = _entries(frames[0], 'drivers'), _entries(frames[1], 'constructors')
        await _load_finishes(season, round_num + 1, schedule, drivers, teams)
        future = [e for e in schedule if int(e['round']) > round_num]
        sprints = sum(sprint_event(e) for e in future)
        result = {'confirmed': True}
        for kind, entries, cars in [('drivers', drivers, 1), ('constructors', teams, 2)]:
            result[kind] = next((c['id'] for c in entries if secured(c, [r for r in entries if r != c], len(future), sprints, cars)), None)
        return result
    except Exception as exc:
        log.warning('Title result %s/%s pending: %s', season, round_num, type(exc).__name__)
        return None
