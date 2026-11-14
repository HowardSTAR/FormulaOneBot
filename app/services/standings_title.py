"""Conservative title badges: exact round, complete calendar, official points."""
import re
from lxml import html
from app.f1_data import cache_result, _formula1_get_text, get_season_schedule_short_async, get_driver_standings_async, get_constructor_standings_async
from app.services.championship import active_events, _entries, _load_finishes, secured, sprint_event


def official_matches(page, entries, kind):
    if not page or not entries:
        return False
    normalize = lambda s: re.sub(r'[^a-z0-9]', '', str(s).lower())
    for table in html.fromstring(page).xpath('//table'):
        rows = [[" ".join(c.text_content().split()) for c in row.xpath('./td')] for row in table.xpath('.//tbody/tr')]
        rows = [r for r in rows if r and r[0].isdigit()]
        if len(rows) != len(entries):
            continue
        used = set()
        for entry in entries:
            needle = normalize(entry['driverCode'] if kind == 'drivers' else entry['constructorName'])
            matches = [i for i, row in enumerate(rows) if len(row) >= 3 and needle and (normalize(row[1]).endswith(needle) if kind == 'drivers' else needle in normalize(row[1]))]
            if len(matches) != 1 or matches[0] in used:
                break
            i = matches[0]
            try:
                if float(rows[i][-1]) != float(entry['points']):
                    break
            except (ValueError, TypeError):
                break
            used.add(i)
        else:
            return True
    return False


@cache_result(ttl=60, key_prefix='standings_title_v1')
async def standings_title(season, round_num, kind):
    empty = {'status': 'unavailable', 'season': season, 'round': round_num}
    if season not in (2025, 2026) or kind not in ('drivers', 'constructors'):
        return empty
    try:
        raw_schedule = await get_season_schedule_short_async(season) or []
        schedule = active_events(raw_schedule)
        rounds = [int(e.get('round') or 0) for e in raw_schedule if not e.get('is_testing')]
        if not rounds or round_num not in rounds or sorted(rounds) != list(range(1, max(rounds) + 1)):
            return empty
        load = get_driver_standings_async if kind == 'drivers' else get_constructor_standings_async
        frame = await load(season, round_num)
        if frame is None or frame.empty or frame.attrs.get('round') != round_num:
            return empty
        candidates = _entries(frame, kind)
        if len(candidates) < 2:
            return empty
        await _load_finishes(season, round_num + 1, schedule,
                             candidates if kind == 'drivers' else [],
                             candidates if kind == 'constructors' else [])
        future = [e for e in schedule if int(e['round']) > round_num]
        identifier = next((c['id'] for c in candidates if secured(c, [r for r in candidates if r != c], len(future), sum(sprint_event(e) for e in future), 1 if kind == 'drivers' else 2)), None)
        if not identifier:
            return {**empty, 'status': 'open'}
        entries = frame.to_dict('records')
        key = 'driverCode' if kind == 'drivers' else 'constructorId'
        champion = next((r for r in entries if r.get(key) == identifier), None)
        source = f"https://www.formula1.com/en/results/{season}/{'drivers' if kind == 'drivers' else 'team'}"
        if not champion or not official_matches(await _formula1_get_text(source), entries, kind):
            return empty
        return {**empty, 'status': 'secured', 'id': identifier, 'points': float(champion['points']), 'source': source}
    except Exception:
        return empty
