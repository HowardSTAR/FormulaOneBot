"""Conservative evidence checks for personal post-race highlights."""
from bisect import bisect_right
from datetime import datetime, timedelta, timezone


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


class RetainedOvertakes:
    """A feed swap alone is insufficient evidence of a retained on-track pass.

    Require adjacent positions exchanging, both cars on a non-pit lap, no nearby
    penalty or neutralisation, unchanged subsequent position and a classified
    finish at that position. Missing timing evidence excludes the candidate.
    """

    def __init__(self, key, finish, positions, laps, pits, results, controls):
        self.key, self.finish = key, finish
        self.positions, self.laps, self.pits, self.results = {}, {}, {}, {}
        self.blocked = []
        for row in positions or []:
            date, position = timestamp(row.get('date')), row.get('position')
            if row.get('session_key') == key and date and isinstance(position, int) and not isinstance(position, bool) and 1 <= position <= 30:
                self.positions.setdefault(str(row.get('driver_number')), []).append((date, position))
        for values in self.positions.values():
            values.sort()
        for row in laps or []:
            start, duration = timestamp(row.get('date_start')), row.get('lap_duration')
            if row.get('session_key') == key and start and isinstance(duration, (int, float)) and 0 < duration < 7200:
                self.laps.setdefault(str(row.get('driver_number')), []).append((start, start + timedelta(seconds=duration), row))
        for row in pits or []:
            if row.get('session_key') == key:
                self.pits.setdefault(str(row.get('driver_number')), []).append(row)
        for row in results or []:
            if row.get('session_key') == key:
                self.results[str(row.get('driver_number'))] = row
        neutral_start = None
        for row in sorted(controls or [], key=lambda row: str(row.get('date', ''))):
            if row.get('session_key') != key:
                continue
            date = timestamp(row.get('date'))
            if not date:
                continue
            message = str(row.get('message', '')).upper()
            if 'PENALTY' in message:
                self.blocked.append((date - timedelta(seconds=90), date + timedelta(seconds=90)))
            if (row.get('category') == 'SafetyCar' and 'DEPLOYED' in message
                    or row.get('flag') == 'RED' and row.get('scope') == 'Track'):
                neutral_start = neutral_start or date
            elif neutral_start and ('ENDING' in message or 'SAFETY CAR IN THIS LAP' in message
                                    or row.get('flag') == 'GREEN' and row.get('scope') == 'Track'):
                self.blocked.append((neutral_start, date + timedelta(seconds=120)))
                neutral_start = None
        if neutral_start:
            self.blocked.append((neutral_start, finish))

    def _on_track(self, number, date):
        lap = next((row for start, end, row in self.laps.get(number, []) if start <= date < end), None)
        if not lap or lap.get('is_pit_out_lap') is not False or not isinstance(lap.get('lap_number'), int) or lap['lap_number'] < 1:
            return None
        for pit in self.pits.get(number, []):
            if pit.get('lap_number') == lap.get('lap_number'):
                return None  # Exclude the whole in-lap, as well as out-laps.
            pit_date = timestamp(pit.get('date'))
            if pit_date and abs((pit_date - date).total_seconds()) <= 90:
                return None
        return lap.get('lap_number')

    def check(self, row):
        date = timestamp(row.get('date'))
        position = row.get('position')
        number, other = str(row.get('overtaking_driver_number')), str(row.get('overtaken_driver_number'))
        if not date or date >= self.finish or not isinstance(position, int) or isinstance(position, bool) or position < 1:
            return None
        if any(start <= date <= end for start, end in self.blocked):
            return None
        result = self.results.get(number, {})
        if (result.get('position') != position or result.get('dnf') is not False
                or result.get('dns') is not False or result.get('dsq') is not False):
            return None
        lap = self._on_track(number, date)
        if lap is None or self._on_track(other, date) is None:
            return None
        # A position gained by passing a stopped/retiring car is ambiguous.
        other_result = self.results.get(other, {})
        if other_result.get('dnf') is not False or other_result.get('dns') is not False or other_result.get('dsq') is not False:
            return None
        for driver, before, after in ((number, position + 1, position), (other, position, position + 1)):
            values = self.positions.get(driver, [])
            dates = [item[0] for item in values]
            index = bisect_right(dates, date - timedelta(microseconds=1))
            # Feeds timestamp the swap and its position update independently.
            # Find the exchange in a narrow window around this exact event.
            possible = [i for i in range(max(1, index - 1), min(len(values), index + 2))
                        if abs((values[i][0] - date).total_seconds()) <= 10
                        and values[i - 1][1] == before and values[i][1] == after]
            if not possible:
                return None
            changed = possible[0]
            if driver == number and any(value != position for _, value in values[changed:]):
                return None
        return lap


def select_highlights(rows, favorites=(), limit=4):
    """General incidents/penalties and only the caller's retained overtakes."""
    from app.services.recap_chronicle import select_events
    codes = {str(code).upper() for code in favorites}
    eligible = [row for row in rows if row.get('category') in {'incident', 'penalty'}
                or row.get('category') == 'retained_overtake' and row.get('driver_code') in codes]
    return select_events(eligible, limit=limit)


def personalize_recap(recap, favorites=()):
    candidates = recap.get('highlight_candidates')
    if candidates is None:
        return recap
    return {**recap, 'chronicle': select_highlights(candidates, favorites)}
