import re

import httpx
import pytest
from fastapi import FastAPI

from app.api.calendar_api import router, session_calendar


def test_calendar_exports_utc_and_folds_multibyte_lines():
    text = session_calendar('Гран-при Сингапура: Спринт-квалификация ' * 4, '2026-10-09T15:30:00+03:00')
    assert 'DTSTART:20261009T123000Z\r\n' in text
    assert text.endswith('END:VCALENDAR\r\n')
    assert all(len(line.encode()) <= 74 for line in text.split('\r\n'))
    assert re.search(r'UID:([a-f0-9]{32})@f1hub.ru', text)
    # No invented finish or user-specific details.
    assert 'DTEND:' not in text
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
