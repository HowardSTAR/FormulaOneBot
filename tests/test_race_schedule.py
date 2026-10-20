"""Shared calendar boundaries used by the bot and web results."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.handlers import races
from app.services.race_schedule import (
    last_completed_race, latest_started_weekend_round, parse_utc_iso,
    should_reset_previous_results,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [None, "", "invalid", 123])
def test_missing_or_invalid_session_time_is_ignored(value):
    assert parse_utc_iso(value) is None


@pytest.mark.parametrize("value", [
    "2026-10-20T12:00:00", "2026-10-20T12:00:00Z", "2026-10-20T15:00:00+03:00",
])
def test_schedule_times_compare_as_the_same_instant(value):
    assert parse_utc_iso(value) == NOW


def test_previous_results_reset_at_first_weekend_session():
    schedule = [
        {"round": 1, "race_start_utc": (NOW - timedelta(days=7)).isoformat()},
        {"round": 2, "first_session_start_utc": NOW.isoformat(),
         "quali_start_utc": (NOW + timedelta(days=1)).isoformat()},
        {"round": 3, "first_session_start_utc": (NOW + timedelta(days=7)).isoformat()},
    ]
    assert latest_started_weekend_round(schedule, NOW - timedelta(seconds=1)) == 1
    assert not should_reset_previous_results(schedule, NOW - timedelta(seconds=1), 1)
    assert latest_started_weekend_round(schedule, NOW) == 2
    assert should_reset_previous_results(schedule, NOW, 1)
    assert not should_reset_previous_results(schedule, NOW, 2)
    assert not should_reset_previous_results(schedule, NOW, None)


def test_missing_times_do_not_hide_started_weekend():
    schedule = [{"round": 1, "race_start_utc": "broken"},
                {"round": 2, "sprint_quali_start_utc": NOW.isoformat()}]
    assert latest_started_weekend_round(schedule, NOW) == 2
    assert not should_reset_previous_results([], NOW, 1)


@pytest.mark.parametrize("testing,hours", [(False, 1), (True, 9)])
def test_completion_window_remains_strict_and_depends_on_session(testing, hours):
    race = {"round": 1, "race_start_utc": NOW.isoformat(), "is_testing": testing}
    schedule = [{"round": 0, "race_start_utc": "invalid"}, race]
    boundary = NOW + timedelta(hours=hours)
    assert last_completed_race(schedule, boundary) is None
    assert last_completed_race(schedule, boundary + timedelta(seconds=1)) == race


@pytest.mark.parametrize("spoiler", [False, True])
async def test_bot_race_results_use_requested_users_spoiler_setting(monkeypatch, spoiler):
    callback = MagicMock()
    callback.data = "race_2020"
    callback.from_user.id = 123
    callback.message = AsyncMock()
    callback.message.chat.type = "private"
    schedule = AsyncMock(return_value=[{
        "round": 1, "race_start_utc": "2020-03-01T12:00:00Z", "event_name": "Test GP",
    }])
    settings = AsyncMock(return_value={"results_spoiler": spoiler})
    loader = MagicMock()
    loader.__aenter__ = AsyncMock()
    loader.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(races, "Loader", lambda *args: loader)
    monkeypatch.setattr(races, "get_season_schedule_short_async", schedule)
    monkeypatch.setattr(races, "get_user_settings", settings)
    for name in ("get_favorite_drivers", "get_favorite_teams"):
        monkeypatch.setattr(races, name, AsyncMock(return_value=[]))
    for name in ("get_driver_standings_async", "get_constructor_standings_async"):
        monkeypatch.setattr(races, name, AsyncMock(return_value=pd.DataFrame()))
    monkeypatch.setattr(races, "get_race_results_async", AsyncMock(return_value=pd.DataFrame([{
        "Position": 1, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "Points": 25,
    }])))
    monkeypatch.setattr(races, "create_f1_style_classification_image", lambda **kwargs: BytesIO(b"png"))
    monkeypatch.setattr(races, "safe_answer_callback", AsyncMock())

    await races.race_callback(callback)

    settings.assert_awaited_once_with(123)
    schedule.assert_awaited_once_with(2020)
    callback.message.answer_photo.assert_awaited_once()
    assert callback.message.answer_photo.await_args.kwargs["has_spoiler"] is spoiler
