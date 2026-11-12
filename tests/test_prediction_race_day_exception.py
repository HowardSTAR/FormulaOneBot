from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services import prediction_service as service


EVENT = {
    'round': 20, 'event_name': 'São Paulo Grand Prix',
    'practice1_start_utc': '2026-11-06T15:30:00Z',
    'quali_start_utc': '2026-11-07T18:00:00Z',
    'race_start_utc': '2026-11-08T17:00:00Z',
}


@pytest.mark.parametrize('instant,opened', [
    ('2026-11-08T12:00:00+00:00', True),
    ('2026-11-08T16:59:59.999999+00:00', True),
    ('2026-11-08T17:00:00+00:00', False),
    ('2026-11-08T17:00:00.000001+00:00', False),
])
async def test_race_day_exception_closes_exactly_at_start(monkeypatch, instant, opened):
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION', '2026:20:2026-11-08')
    monkeypatch.setattr(service, 'get_season_schedule_short_async', AsyncMock(return_value=[EVENT]))
    data = await service.get_prediction_context(datetime.fromisoformat(instant))
    assert data['is_open'] is opened
    assert data['race_day_exception'] is True
    assert data['deadline_utc'] == '2026-11-08T17:00:00+00:00'


@pytest.mark.parametrize('changed', [
    {'round': 21}, {'race_start_utc': '2027-11-08T17:00:00Z'},
    {'race_start_utc': '2026-11-09T17:00:00Z'},
])
def test_exception_never_affects_other_stage_or_day(monkeypatch, changed):
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION', '2026:20:2026-11-08')
    event = {**EVENT, **changed}
    assert not service.race_day_prediction_exception(event)
    assert service.get_prediction_window(event)[1] == service.parse_utc(EVENT['quali_start_utc'])


def test_normal_deadline_remains_qualifying(monkeypatch):
    monkeypatch.delenv('PREDICTION_RACE_DAY_EXCEPTION', raising=False)
    assert service.get_prediction_window(EVENT)[1] == service.parse_utc(EVENT['quali_start_utc'])


def test_explicit_exception_end_cannot_be_extended_by_calendar(monkeypatch):
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION', '2026:20:2026-11-08')
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION_UNTIL', '2026-11-08T17:00:00Z')
    event = {**EVENT, 'race_start_utc': '2026-11-08T18:00:00Z'}
    assert service.get_prediction_window(event)[1] == service.parse_utc('2026-11-08T17:00:00Z')


def test_invalid_exception_end_fails_closed(monkeypatch):
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION', '2026:20:2026-11-08')
    monkeypatch.setenv('PREDICTION_RACE_DAY_EXCEPTION_UNTIL', 'invalid')
    assert not service.race_day_prediction_exception(EVENT)
    assert service.get_prediction_window(EVENT)[1] == service.parse_utc(EVENT['quali_start_utc'])


async def test_deadline_rechecked_under_database_write_lock(api_client):
    from app.db import db, get_or_create_user
    from tests.test_predictions import prediction_payload, DRIVERS
    user_id = await get_or_create_user(2099386)
    await service.save_prediction_profile(user_id, 'Deadline test')
    with pytest.raises(service.PredictionWindowClosed):
        await service.save_user_prediction(user_id, 2026, 20, prediction_payload(),
            allowed_driver_codes=set(DRIVERS),
            deadline_utc=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    row = await (await db.conn.execute('SELECT COUNT(*) FROM race_predictions WHERE user_id=? AND season=2026 AND round=20', (user_id,))).fetchone()
    assert row[0] == 0
