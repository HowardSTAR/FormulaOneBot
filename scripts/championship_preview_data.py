"""Synthetic standings shared by poster previews and offline tests."""
from pathlib import Path

from app.services.championship import calculate_candidates
from app.utils.default import DRIVER_CODE_TO_FILE

DRIVERS = ('ANT', 'RUS', 'NOR', 'VER', 'PIA', 'LEC', 'HAM', 'ALO')
TEAMS = (
    ('mercedes', 'Mercedes'), ('mclaren', 'McLaren'), ('ferrari', 'Ferrari'),
    ('red_bull', 'Red Bull'), ('williams', 'Williams'), ('aston_martin', 'Aston Martin'),
    ('alpine', 'Alpine'), ('haas', 'Haas'), ('rb', 'Racing Bulls'),
    ('audi', 'Audi'), ('cadillac', 'Cadillac'),
)


def _entrant(code, name, points, wins=0):
    return {'id': code, 'name': name, 'points': float(points), 'wins': wins,
            'finishes': [wins] + [0]*31}


def preview_context(*, next_round=False, participants=3):
    if participants not in {3, 4, 5, 8}:
        raise ValueError('Preview supports 3, 4, 5 or 8 total participants')
    codes = DRIVERS[:participants]
    drivers = [_entrant(code, 'Kimi Antonelli' if code == 'ANT' else Path(DRIVER_CODE_TO_FILE[code]).stem,
                        350 if index == 0 else 316-index, 7)
               for index, code in enumerate(codes)]
    for code, filename in DRIVER_CODE_TO_FILE.items():
        if code not in {*codes, 'DOO', 'TSU'}:
            drivers.append(_entrant(code, Path(filename).stem, 180-len(drivers)))
    teams = []
    for index, (code, name) in enumerate(TEAMS):
        points = 665 if index == 0 else 611-index
        teams.append(_entrant(code, name, points if index < participants else 400-index,
                              7 if index < participants else 0))
    if next_round:
        for entries, scores in [(drivers, (375, 330, 332)), (teams, (708, 628, 636))]:
            for entry, points in zip(entries, scores):
                entry['points'] = float(points)
            entries[0]['wins'] = entries[0]['finishes'][0] = 8
    remaining_races = 1 if next_round else 2
    # Full grids and the production solver; no hand-written point caps.
    return {'status': 'ok', 'season': 2026, 'round': 23 if next_round else 22,
            'drivers': calculate_candidates(drivers, remaining_races, 0, grid_size=22),
            'constructors': calculate_candidates(teams, remaining_races, 0, cars=2, grid_size=22)}
