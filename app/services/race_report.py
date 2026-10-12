"""Shared classification and private favorites for race messages."""
import math

import pandas as pd

from app.services.race_recap import classified_rows


def image_rows(frame):
    verified = classified_rows(frame)
    by_code = {str(row['Abbreviation']).upper(): row for row in frame.to_dict('records')} if verified else {}
    return [{"pos": row['Position'], "driver": row['FullName'], "driver_code": row['Abbreviation'],
             "team": by_code[row['Abbreviation'].upper()].get('TeamName', ''), "points": row['Points']}
            for row in sorted(verified, key=lambda row: row['Position'])]


def _points(value):
    try:
        number = float(value)
        return f'{number:g}' if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def favorites_text(rows, favorites, drivers=None, teams=None, *, round_num=None):
    """Plain text; presentation layers supply their own escaping and spoilers."""
    def records(frame):
        if isinstance(frame, pd.DataFrame):
            if round_num is not None and frame.attrs.get('round', round_num) != round_num:
                return []
            return frame.to_dict('records')
        return frame or []
    drivers, teams = records(drivers), records(teams)
    totals = {str(row.get('driverCode', '')).upper(): _points(row.get('points')) for row in drivers}
    sections, lines = [], []
    for code in dict.fromkeys(str(code).upper() for code in favorites.get('drivers', [])):
        row = next((row for row in rows if str(row.get('driver_code', '')).upper() == code), None)
        if row:
            total = totals.get(code)
            lines.append(f"• {code}: P{row['pos']}, +{_points(row.get('points')) or '0'} очк. за гонку; "
                         + (f'всего {total} очк.' if total is not None else 'сумма в чемпионате уточняется.'))
    if lines:
        sections.append('🏎 Пилоты\n' + '\n'.join(lines))
    lines = []
    def matches(a, b):
        a, b = str(a or '').strip().casefold(), str(b or '').strip().casefold()
        return bool(a and b and (a in b or b in a))
    for team in dict.fromkeys(favorites.get('teams', [])):
        team_rows = [row for row in rows if matches(team, row.get('team'))]
        if not team_rows:
            continue
        standing = next((row for row in teams if matches(team, row.get('constructorName'))), {})
        total = _points(standing.get('points'))
        points = sum(float(row.get('points') or 0) for row in team_rows)
        lines.append(f'• {team}: +{points:g} очк. за гонку; '
                     + (f'всего {total} очк.' if total is not None else 'сумма в чемпионате уточняется.'))
    if lines:
        sections.append('🏁 Команды\n' + '\n'.join(lines))
    return '\n\n'.join(sections)
