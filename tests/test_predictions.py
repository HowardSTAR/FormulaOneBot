from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from aiogram.types import InputMediaPhoto

from app.utils.safe_send import safe_send_media_group


DRIVERS = ["VER", "NOR", "PIA", "LEC", "HAM", "RUS", "ALO", "SAI"]


def prediction_payload() -> dict:
    return {
        "sprint_pole_driver": None,
        "sprint_winner_driver": None,
        "pole_driver": "VER",
        "winner_driver": "VER",
        "second_driver": "NOR",
        "third_driver": "PIA",
        "fourth_driver": "LEC",
        "fifth_driver": "HAM",
        "fastest_lap_driver": "NOR",
        "first_retirement_driver": "SAI",
        "safety_car": True,
    }


def test_broadcast_payload_preserves_telegram_formatting():
    """Подпись альбома сохраняет entities после удаления команды."""
    from app.handlers.secret import _broadcast_html_payload

    message = type("BroadcastMessage", (), {"html_text": "/broadcast <b>Важный текст</b>"})()
    assert _broadcast_html_payload(message) == "<b>Важный текст</b>"


@pytest.mark.asyncio
async def test_long_broadcast_text_is_split_at_telegram_limit():
    """Текст длиннее 4096 символов отправляется безопасными отдельными сообщениями."""
    from app.handlers.secret import _send_broadcast_text

    bot = AsyncMock()
    plain = "A" * 8500
    with patch("app.handlers.secret.safe_send_message", new_callable=AsyncMock, return_value=True) as send:
        assert await _send_broadcast_text(
            bot,
            12345,
            plain,
            plain,
            disable_notification=False,
        )
    assert send.await_count == 3
    assert all(len(call.args[2]) <= 4000 for call in send.await_args_list)


def test_prediction_fallback_excludes_unavailable_api_categories():
    """Нет данных по SC/первому сходу/лучшему кругу — категории остаются недоступными."""
    from app.services.prediction_service import build_actual_answers

    race = pd.DataFrame([
        {"Position": 1, "Abbreviation": "VER"},
        {"Position": 2, "Abbreviation": "NOR"},
        {"Position": 3, "Abbreviation": "PIA"},
        {"Position": 4, "Abbreviation": "LEC"},
        {"Position": 5, "Abbreviation": "HAM"},
    ])
    answers = build_actual_answers(race, [{"position": 1, "driver": "VER"}])
    assert answers["pole_driver"] == "VER"
    assert answers["winner_driver"] == "VER"
    assert answers["safety_car"] is None
    assert answers["first_retirement_driver"] is None
    assert answers["fastest_lap_driver"] is None


def test_prediction_open_trigger_after_fp2():
    """Открытие прогнозов планируется после FP2, даже если FP3 ещё не началась."""
    from app.services.prediction_notifications import _prediction_open_trigger

    trigger = _prediction_open_trigger([
        {"name": "Practice 2", "utc_iso": "2030-05-10T12:00:00+00:00"},
        {"name": "Practice 3", "utc_iso": "2030-05-11T10:00:00+00:00"},
    ])
    assert trigger == datetime(2030, 5, 10, 13, 30, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_prediction_profile_scoring_and_leaderboard(api_client):
    """Профиль, прогноз, расчёт этапа и общая таблица используют одну историю БД."""
    from app.services.prediction_service import (
        get_prediction_leaderboard,
        save_prediction_profile,
        save_user_prediction,
        score_prediction_round,
    )

    telegram_id = 999888
    await save_prediction_profile(telegram_id, "Test Racer")
    await save_user_prediction(
        telegram_id,
        2030,
        4,
        prediction_payload(),
        allowed_driver_codes=set(DRIVERS),
    )
    answers = prediction_payload() | {
        "fastest_lap_driver": None,
        "first_retirement_driver": None,
        "safety_car": None,
    }
    score = await score_prediction_round(2030, 4, "Test Grand Prix", answers)
    assert score["max_points"] == 31
    assert score["scored"] == 1
    leaderboard = await get_prediction_leaderboard()
    entry = next(item for item in leaderboard["entries"] if item["display_name"] == "Test Racer")
    assert entry["total_points"] == 31
    assert entry["best_points"] == 31
    assert entry["average_points"] == 31.0
    assert entry["wins"] == 1
    assert entry["history"][0]["max_points"] == 31
    assert leaderboard["rounds"][0]["short_code"] == "TES"


def test_prediction_points_follow_2026_matrix():
    """Матрица учитывает точные спринты и отклонение финишной позиции до трёх мест."""
    from app.services.prediction_service import calculate_prediction_points

    prediction = prediction_payload() | {
        "sprint_pole_driver": "VER",
        "sprint_winner_driver": "NOR",
        "winner_driver": "NOR",
        "second_driver": "VER",
    }
    answers = {
        **prediction_payload(),
        "sprint_pole_driver": "VER",
        "sprint_winner_driver": "NOR",
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
        },
    }
    assert calculate_prediction_points(prediction, answers) == 36


@pytest.mark.asyncio
async def test_prediction_schema_contains_optional_sprint_columns(api_client):
    """Миграция создаёт nullable спринт-поля и в прогнозах, и в итогах этапа."""
    from app.db import db

    for table_name in ("race_predictions", "prediction_round_results"):
        async with db.conn.execute(f"PRAGMA table_info({table_name})") as cursor:
            columns = {row["name"]: row for row in await cursor.fetchall()}
        assert "sprint_pole_driver" in columns
        assert "sprint_winner_driver" in columns
        assert columns["sprint_pole_driver"]["notnull"] == 0


@pytest.mark.asyncio
async def test_prediction_api_rejects_after_deadline(api_client):
    """Сервер отклоняет запись после квалификации независимо от клиентской блокировки."""
    with patch("app.api.miniapp_api.get_prediction_context", new_callable=AsyncMock) as context:
        context.return_value = {
            "status": "ok",
            "season": 2030,
            "round": 3,
            "event_name": "Closed GP",
            "is_open": False,
        }
        response = await api_client.post("/api/predictions/current", json=prediction_payload())
    assert response.status_code == 409
    assert "квалификация" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_safe_send_media_group_preserves_album_caption():
    """Telegram-альбом отправляется одним sendMediaGroup, caption находится на первом фото."""
    bot = AsyncMock()
    media = [
        InputMediaPhoto(media="file-1", caption="<b>Рассылка</b>", parse_mode="HTML"),
        InputMediaPhoto(media="file-2"),
    ]
    assert await safe_send_media_group(bot, 12345, media, disable_notification=True)
    bot.send_media_group.assert_awaited_once()
    sent_media = bot.send_media_group.await_args.kwargs["media"]
    assert sent_media[0].caption == "<b>Рассылка</b>"
    assert sent_media[1].caption is None
