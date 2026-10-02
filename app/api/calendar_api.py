"""Public, read-only calendar export; no account data or external requests."""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix='/api/calendar', tags=['calendar'])


def session_calendar(title: str, start: str) -> str:
    try:
        date = datetime.fromisoformat(start.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('Timezone required')
        date = date.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Некорректное время сессии') from None
    if not title.strip() or len(title) > 240 or len(start) > 64:
        raise ValueError('Некорректное название сессии')
    stamp = date.strftime('%Y%m%dT%H%M%SZ')
    uid = hashlib.sha256(f'{title}|{stamp}'.encode()).hexdigest()[:32]
    escaped = title.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//TurboTears//Sessions//RU',
             'CALSCALE:GREGORIAN', 'BEGIN:VEVENT', f'UID:{uid}@f1hub.ru',
             f'DTSTAMP:{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',
             f'DTSTART:{stamp}', f'SUMMARY:{escaped}',
             'DESCRIPTION:Время начала сессии. Проверьте расписание перед этапом: оно может измениться.',
             'END:VEVENT', 'END:VCALENDAR']
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
