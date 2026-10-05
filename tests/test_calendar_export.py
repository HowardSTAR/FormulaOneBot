import re

import httpx
import pytest
from fastapi import FastAPI

from app.api.calendar_api import router, session_calendar, weekend_calendar
from app.api import calendar_api


def test_calendar_exports_utc_and_folds_multibyte_lines():
    text = session_calendar('Гран-при Сингапура: Спринт-квалификация ' * 4, '2026-10-09T15:30:00+03:00')
    assert 'DTSTART:20261009T123000Z\r\n' in text
    assert text.endswith('END:VCALENDAR\r\n')
    assert all(len(line.encode()) <= 74 for line in text.split('\r\n'))
    assert re.search(r'UID:([a-f0-9]{32})@f1hub.ru', text)
    assert 'DTEND:20261009T133000Z\r\n' in text
    assert 'окончания ориентировочное' in text.replace('\r\n ', '')
    assert 'URL:' not in text


def test_calendar_title_cannot_inject_ics_properties():
    text = session_calendar('Race\r\nATTENDEE:evil@example.test; test,\\', '2026-10-09T12:30:00Z')
    unfolded = text.replace('\r\n ', '')
    assert 'SUMMARY:Race\\nATTENDEE:evil@example.test\\; test\\,\\\\\r\n' in unfolded
    assert '\r\nATTENDEE:' not in unfolded


@pytest.mark.parametrize('value', ['bad', '', '2026-10-09T12:30:00', '2026-10-09', '99999999'])
def test_calendar_rejects_unknown_or_timezone_ambiguous_starts(value):
    with pytest.raises(ValueError):
        session_calendar('Race', value)


@pytest.mark.asyncio
async def test_calendar_http_download_is_public_bounded_and_not_html():
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/calendar/session.ics', params={'title': 'Спринт', 'start': '2026-10-09T12:30:00Z'})
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/calendar')
        assert response.headers['content-disposition'] == 'attachment; filename="f1-session.ics"'
        assert response.headers['cache-control'] == 'no-store'
        assert 'SUMMARY:Спринт' in response.text
        assert (await client.get('/api/calendar/session.ics', params={'title': 'Race', 'start': 'bad'})).status_code == 400
        assert (await client.get('/api/calendar/session.ics', params={'title': 'X'*241, 'start': '2026-10-09T12:30:00Z'})).status_code == 422


def test_weekend_contains_every_session_once_in_chronological_order():
    sessions = [
        {'name': 'Race', 'utc_iso': '2026-10-11T15:00:00+03:00'},
        {'name': 'Practice 1', 'utc_iso': '2026-10-09T12:30:00Z'},
        {'name': 'Sprint Qualifying', 'utc_iso': '2026-10-09T16:00:00Z'},
        {'name': 'Sprint', 'utc_iso': '2026-10-10T12:00:00Z'},
        {'name': 'Qualifying', 'utc_iso': '2026-10-10T16:00:00Z'},
        {'name': 'Race', 'utc_iso': '2026-10-11T12:00:00Z'},
        {'name': 'Practice 2', 'utc_iso': None},
        {'name': 'Practice 3', 'utc_iso': '2026-10-10T11:00:00'},
    ]
    content = weekend_calendar('Singapore Grand Prix', sessions, 2026, 17)
    unfolded = content.replace('\r\n ', '')
    assert content.count('BEGIN:VCALENDAR') == 1
    assert content.count('BEGIN:VEVENT') == 5
    assert len(set(re.findall(r'UID:(.+)', unfolded))) == 5
    assert re.findall(r'DTSTART:(.+)', unfolded) == [
        '20261009T123000Z\r', '20261009T160000Z\r', '20261010T120000Z\r',
        '20261010T160000Z\r', '20261011T120000Z\r',
    ]
    assert 'SUMMARY:Singapore Grand Prix: Спринт-квалификация' in unfolded
    assert re.findall(r'DTEND:(.+)', unfolded) == [
        '20261009T133000Z\r', '20261009T170000Z\r', '20261010T130000Z\r',
        '20261010T173000Z\r', '20261011T150000Z\r',
    ]
    assert all(len(line.encode()) <= 74 for line in content.split('\r\n'))


@pytest.mark.parametrize(('title', 'end'), [
    ('Гонка', '20261010T013000Z'), ('Race', '20261010T013000Z'),
    ('Квалификация', '20261010T000000Z'), ('Qualifying', '20261010T000000Z'),
    ('Спринт-квалификация', '20261009T233000Z'), ('Practice 3', '20261009T233000Z'),
])
def test_calendar_reserves_session_window_across_midnight(title, end):
    content = session_calendar(title, '2026-10-10T01:30:00+03:00')
    assert 'DTSTART:20261009T223000Z' in content
    assert f'DTEND:{end}' in content


def test_weekend_session_identity_survives_rescheduling_and_escapes_text():
    session = {'name': 'Race', 'utc_iso': '2026-10-11T12:00:00Z'}
    first = weekend_calendar('Race\nATTENDEE:bad@example.test', [session], 2026, 17)
    changed = weekend_calendar('Race', [{**session, 'utc_iso': '2026-10-11T13:00:00Z'}], 2026, 17)
    another = weekend_calendar('Race', [session], 2026, 18)
    uid = lambda content: re.search(r'UID:(.+)', content)[1]
    assert uid(first) == uid(changed)
    assert uid(first) != uid(another)
    assert '\r\nATTENDEE:' not in first
    with pytest.raises(ValueError, match='пока не опубликовано'):
        weekend_calendar('Race', [], 2026, 17)


@pytest.mark.asyncio
async def test_weekend_download_uses_requested_stage_and_all_published_sessions(monkeypatch):
    seen = []
    async def load(season, round_number):
        seen.append((season, round_number))
        return {'event_name': 'Singapore Grand Prix', 'sessions': [
            {'name': 'Practice 1', 'utc_iso': '2026-10-09T12:00:00Z'},
            {'name': 'Race', 'utc_iso': '2026-10-11T12:00:00Z'},
        ]}
    monkeypatch.setattr(calendar_api, '_load_weekend', load)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/calendar/weekend.ics', params={'season': 2026, 'round': 17})
        assert response.status_code == 200
        assert seen == [(2026, 17)]
        assert response.text.count('BEGIN:VEVENT') == 2
        assert response.headers['content-disposition'] == 'attachment; filename="f1-weekend-2026-17.ics"'
        assert response.headers['content-type'].startswith('text/calendar')
        assert response.headers['cache-control'] == 'no-store'
        assert (await client.get('/api/calendar/weekend.ics', params={'season': 2026, 'round': 0})).status_code == 422
        assert (await client.get('/api/calendar/weekend.ics', params={'season': 1949, 'round': 1})).status_code == 422
        assert seen == [(2026, 17)]


@pytest.mark.asyncio
@pytest.mark.parametrize(('race', 'status'), [
    (None, 404), ({'is_cancelled': True}, 409),
    ({'event_name': 'Race', 'sessions': []}, 409),
])
async def test_weekend_download_does_not_export_missing_or_cancelled_schedule(monkeypatch, race, status):
    async def load(*_):
        return race
    monkeypatch.setattr(calendar_api, '_load_weekend', load)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/calendar/weekend.ics?season=2026&round=17')
        assert response.status_code == status
        assert 'BEGIN:VCALENDAR' not in response.text
