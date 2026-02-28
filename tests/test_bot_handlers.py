"""
Тесты хендлеров Telegram-бота.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.handlers.races import (
    build_next_race_payload,
    _parse_season_from_text,
)
from app.handlers.compare import build_drivers_keyboard
from app.utils.default import validate_f1_year


@pytest.mark.asyncio
async def test_build_next_race_payload_ok():
    """build_next_race_payload возвращает данные о ближайшей гонке."""
    schedule = [
        {"round": 1, "date": "2030-06-01", "event_name": "Monaco GP", "country": "Monaco", "location": "Monte Carlo", "race_start_utc": "2030-06-01T13:00:00+00:00"},
    ]
    with patch("app.handlers.races.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = schedule
        with patch("app.handlers.races.get_user_settings", new_callable=AsyncMock) as m2:
            m2.return_value = {"timezone": "Europe/Moscow"}
            payload = await build_next_race_payload(2030, user_id=123)
    assert payload["status"] == "ok"
    assert payload["season"] == 2030
    assert payload["round"] == 1
    assert "Monaco" in payload["event_name"]


@pytest.mark.asyncio
async def test_build_next_race_payload_no_schedule():
    """build_next_race_payload — нет расписания."""
    with patch("app.handlers.races.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = []
        payload = await build_next_race_payload(2024)
    assert payload["status"] == "no_schedule"


@pytest.mark.asyncio
async def test_build_next_race_payload_season_finished():
    """build_next_race_payload — сезон завершён (все гонки в прошлом)."""
    schedule = [
        {"round": 1, "date": "2020-03-01", "event_name": "Bahrain GP", "country": "Bahrain", "location": "Sakhir"},
    ]
    with patch("app.handlers.races.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = schedule
        payload = await build_next_race_payload(2020)
    assert payload["status"] == "season_finished"


def test_parse_season_from_text_default():
    """_parse_season_from_text — по умолчанию текущий год."""
    text = "/races"
    assert _parse_season_from_text(text) == datetime.now().year


def test_parse_season_from_text_with_year():
    """_parse_season_from_text — год в аргументе."""
    text = "/races 2007"
    assert _parse_season_from_text(text) == 2007


def test_parse_season_from_text_invalid():
    """_parse_season_from_text — нечисловой аргумент."""
    text = "/races abc"
    assert _parse_season_from_text(text) == datetime.now().year


def test_build_drivers_keyboard():
    """build_drivers_keyboard создаёт клавиатуру с пилотами."""
    drivers = [
        {"code": "VER", "name": "Verstappen"},
        {"code": "NOR", "name": "Norris"},
    ]
    kb = build_drivers_keyboard(drivers, "cmp_d1_")
    assert kb is not None
    assert kb.inline_keyboard
    # Должны быть кнопки для обоих пилотов
    flat = [b for row in kb.inline_keyboard for b in row]
    assert len(flat) >= 2


def test_build_drivers_keyboard_exclude():
    """build_drivers_keyboard с exclude_code не показывает этого пилота."""
    drivers = [
        {"code": "VER", "name": "Verstappen"},
        {"code": "NOR", "name": "Norris"},
    ]
    kb = build_drivers_keyboard(drivers, "cmp_d2_", exclude_code="VER")
    flat = [b for row in kb.inline_keyboard for b in row]
    # Только NOR
    callback_data = [b.callback_data for b in flat]
    assert "cmp_d2_VER" not in callback_data
    assert any("cmp_d2_NOR" in c for c in callback_data)


def test_validate_f1_year_valid():
    """validate_f1_year — валидные годы."""
    assert validate_f1_year(1950) is None
    assert validate_f1_year(2000) is None
    assert validate_f1_year(datetime.now().year) is None


def test_validate_f1_year_too_old():
    """validate_f1_year — до 1950."""
    msg = validate_f1_year(1949)
    assert msg is not None
    assert "1950" in msg


def test_validate_f1_year_future():
    """validate_f1_year — будущий год."""
    msg = validate_f1_year(datetime.now().year + 5)
    assert msg is not None
