"""Public calendar downloads from the published race schedule."""
import asyncio
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix='/api/calendar', tags=['calendar'])


def _session_date(start: str) -> datetime:
    try:
        date = datetime.fromisoformat(start.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('Timezone required')
        date = date.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Некорректное время сессии') from None
    return date


def _event_lines(title: str, start: str, identity: str | None = None) -> list[str]:
    date = _session_date(start)
    if not title.strip() or len(title) > 240 or len(start) > 64:
        raise ValueError('Некорректное название сессии')
    stamp = date.strftime('%Y%m%dT%H%M%SZ')
    uid = hashlib.sha256((identity or f'{title}|{stamp}').encode()).hexdigest()[:32]
    escaped = title.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    return ['BEGIN:VEVENT', f'UID:{uid}@f1hub.ru',
             f'DTSTAMP:{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',
             f'DTSTART:{stamp}', f'SUMMARY:{escaped}',
             'DESCRIPTION:Время начала сессии. Проверьте расписание перед этапом: оно может измениться.',
             'END:VEVENT']


def _calendar(events: list[list[str]]) -> str:
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//TurboTears//Sessions//RU',
             'CALSCALE:GREGORIAN', *[line for event in events for line in event],
             'END:VCALENDAR']
    folded = []
    for line in lines:
        part = ''
        size = 0
        for char in line:
            octets = len(char.encode('utf-8'))
            if size + octets > 74:
                folded.append(part)
                part, size = ' ', 1
            part += char
            size += octets
        folded.append(part)
    return '\r\n'.join(folded) + '\r\n'


def session_calendar(title: str, start: str) -> str:
    return _calendar([_event_lines(title, start)])


SESSION_NAMES = {
    'Practice 1': 'Практика 1', 'Practice 2': 'Практика 2',
    'Practice 3': 'Практика 3', 'Qualifying': 'Квалификация',
    'Sprint': 'Спринт', 'Sprint Qualifying': 'Спринт-квалификация', 'Race': 'Гонка',
}


def weekend_calendar(title: str, sessions: list[dict], season: int, round_number: int) -> str:
    seen = set()
    dated = []
    for session in sessions:
        name = SESSION_NAMES.get(session.get('name'), session.get('name'))
        start = session.get('utc_iso')
        if not isinstance(name, str) or not name.strip() or not isinstance(start, str):
            continue
        try:
            date = _session_date(start)
            event = _event_lines(f'{title}: {name}', start, f'{season}|{round_number}|{name}')
        except ValueError:
            continue
        if name not in seen:
            seen.add(name)
            dated.append((date, event))
    events = [event for _, event in sorted(dated, key=lambda item: item[0])]
    if not events:
        raise ValueError('Время сессий этапа пока не опубликовано')
    return _calendar(events)


async def _load_weekend(season: int, round_number: int) -> dict | None:
    from app.f1_data import get_season_schedule_short_async, get_weekend_schedule

    schedule = await get_season_schedule_short_async(season)
    race = next((race for race in (schedule or []) if race.get('round') == round_number), None)
    if race is None or race.get('is_cancelled'):
        return race
    sessions = await asyncio.to_thread(get_weekend_schedule, season, round_number)
    return {**race, 'sessions': sessions}


@router.get('/weekend.ics')
async def download_weekend(
    season: int = Query(ge=1950, le=2100),
    round_number: int = Query(alias='round', ge=1, le=30),
):
    race = await _load_weekend(season, round_number)
    if race is None:
        raise HTTPException(404, 'Этап не найден')
    if race.get('is_cancelled'):
        raise HTTPException(409, 'Этап отменён')
    try:
        content = weekend_calendar(race.get('event_name') or f'Этап {round_number}',
                                   race.get('sessions') or [], season, round_number)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(content, media_type='text/calendar; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="f1-weekend-{season}-{round_number}.ics"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.get('/session.ics')
async def download_session(title: str = Query(min_length=1, max_length=240), start: str = Query(min_length=1, max_length=64)):
    try:
        content = session_calendar(title, start)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return Response(content, media_type='text/calendar; charset=utf-8', headers={
        'Content-Disposition': 'attachment; filename="f1-session.ics"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })
