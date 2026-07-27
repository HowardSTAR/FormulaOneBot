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

    from app.db import get_or_create_user

    user_id = await get_or_create_user(999888)
    await save_prediction_profile(user_id, "Test Racer")
    await save_user_prediction(
        user_id,
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


@pytest.mark.asyncio
async def test_recalculation_is_atomic_revisioned_and_does_not_double_count(api_client):
    """Перерасчёт заменяет очки этапа, пишет ревизию и не удваивает общий итог."""
    from app.db import db, get_or_create_user
    from app.services.prediction_service import (
        get_prediction_leaderboard,
        save_prediction_profile,
        save_user_prediction,
        score_prediction_round,
    )

    user_id = await get_or_create_user(700701)
    await save_prediction_profile(user_id, "Revision Racer")
    await save_user_prediction(
        user_id,
        2031,
        2,
        prediction_payload(),
        allowed_driver_codes=set(DRIVERS),
    )
    answers = prediction_payload() | {
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
            "SAI": 20,
        }
    }
    first = await score_prediction_round(
        2031,
        2,
        "Revision Grand Prix",
        answers,
        calculation_source="test",
    )
    assert first["revision"] == 1
    assert first["changed"] is True
    assert first["max_points"] == 37

    corrected = {**answers, "fastest_lap_driver": "VER"}
    second = await score_prediction_round(
        2031,
        2,
        "Revision Grand Prix",
        corrected,
        calculation_source="test",
        actor_user_id=user_id,
    )
    assert second["revision"] == 2
    assert second["changed"] is True

    async with db.conn.execute(
        """
        SELECT points, max_points FROM race_predictions
        WHERE user_id = ? AND season = 2031 AND round = 2
        """,
        (user_id,),
    ) as cursor:
        scored = await cursor.fetchone()
    assert scored["points"] == 35
    assert scored["max_points"] == 37

    async with db.conn.execute(
        """
        SELECT revision, source, actor_user_id
        FROM prediction_score_runs
        WHERE season = 2031 AND round = 2
        ORDER BY revision
        """
    ) as cursor:
        runs = await cursor.fetchall()
    assert [(row["revision"], row["source"]) for row in runs] == [
        (1, "test"),
        (2, "test"),
    ]
    assert runs[-1]["actor_user_id"] == user_id

    leaderboard = await get_prediction_leaderboard()
    entry = next(
        item for item in leaderboard["entries"]
        if item["display_name"] == "Revision Racer"
    )
    assert entry["total_points"] == 35
    assert entry["rounds_scored"] == 1


@pytest.mark.asyncio
async def test_failed_recalculation_rolls_back_round_and_history(api_client, monkeypatch):
    """Любая ошибка в цикле пользователей откатывает факты, очки и score-run."""
    from app.db import db, get_or_create_user
    from app.services import prediction_service

    user_id = await get_or_create_user(700702)
    await prediction_service.save_prediction_profile(user_id, "Rollback Racer")
    await prediction_service.save_user_prediction(
        user_id,
        2032,
        3,
        prediction_payload(),
        allowed_driver_codes=set(DRIVERS),
    )
    answers = prediction_payload() | {
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
            "SAI": 20,
        }
    }
    initial = await prediction_service.score_prediction_round(
        2032,
        3,
        "Atomic Grand Prix",
        answers,
        calculation_source="test",
    )

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic scoring failure")

    monkeypatch.setattr(prediction_service, "calculate_prediction_points", explode)
    with pytest.raises(RuntimeError, match="synthetic"):
        await prediction_service.score_prediction_round(
            2032,
            3,
            "Corrupted Name",
            {**answers, "fastest_lap_driver": "VER"},
            calculation_source="test",
        )

    async with db.conn.execute(
        """
        SELECT event_name, calculation_revision, answers_hash
        FROM prediction_round_results
        WHERE season = 2032 AND round = 3
        """
    ) as cursor:
        stored_round = await cursor.fetchone()
    assert stored_round["event_name"] == "Atomic Grand Prix"
    assert stored_round["calculation_revision"] == 1
    assert stored_round["answers_hash"] == initial["answers_hash"]

    async with db.conn.execute(
        """
        SELECT COUNT(*) AS total FROM prediction_score_runs
        WHERE season = 2032 AND round = 3
        """
    ) as cursor:
        assert (await cursor.fetchone())["total"] == 1


@pytest.mark.asyncio
async def test_leaderboard_tie_breaker_is_stable_and_not_name_dependent(api_client):
    """При полном равенстве переименование профиля не меняет порядок участников."""
    from app.db import get_or_create_user
    from app.services.prediction_service import (
        get_prediction_leaderboard,
        save_prediction_profile,
        save_user_prediction,
        score_prediction_round,
    )

    first_id = await get_or_create_user(700703)
    second_id = await get_or_create_user(700704)
    assert first_id < second_id
    await save_prediction_profile(first_id, "Zulu Racer")
    await save_prediction_profile(second_id, "Alpha Racer")
    for user_id in (first_id, second_id):
        await save_user_prediction(
            user_id,
            2033,
            1,
            prediction_payload(),
            allowed_driver_codes=set(DRIVERS),
        )
    answers = prediction_payload() | {
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
            "SAI": 20,
        }
    }
    await score_prediction_round(
        2033,
        1,
        "Tie Grand Prix",
        answers,
        calculation_source="test",
    )
    entries = (await get_prediction_leaderboard())["entries"]
    tied = [entry for entry in entries if entry["user_id"] in {first_id, second_id}]
    assert [entry["user_id"] for entry in tied] == [first_id, second_id]


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


def test_perfect_sprint_prediction_reaches_published_maximum():
    """Все доступные категории спринт-этапа дают ровно 43 балла."""
    from app.services.prediction_service import (
        EXACT_POINTS,
        calculate_prediction_points,
    )

    prediction = prediction_payload() | {
        "sprint_pole_driver": "VER",
        "sprint_winner_driver": "NOR",
    }
    answers = prediction | {
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
            "RUS": 6,
            "ALO": 7,
            "SAI": 8,
        }
    }
    assert sum(EXACT_POINTS.values()) == 43
    assert calculate_prediction_points(prediction, answers) == 43


def test_completely_wrong_prediction_is_zero_and_never_negative():
    """Пилоты вне диапазона ±3 и неверные бонусы не создают штрафов/NaN."""
    from app.services.prediction_service import calculate_prediction_points

    prediction = {
        "sprint_pole_driver": "BOT",
        "sprint_winner_driver": "BOT",
        "pole_driver": "BOT",
        "winner_driver": "GAS",
        "second_driver": "OCO",
        "third_driver": "TSU",
        "fourth_driver": "ALB",
        "fifth_driver": "HUL",
        "fastest_lap_driver": "BOT",
        "first_retirement_driver": "BOT",
        "safety_car": False,
    }
    answers = prediction_payload() | {
        "sprint_pole_driver": "VER",
        "sprint_winner_driver": "NOR",
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
            "GAS": 10,
            "OCO": 11,
            "TSU": 12,
            "ALB": 13,
            "HUL": 14,
        },
    }
    assert calculate_prediction_points(prediction, answers) == 0


@pytest.mark.parametrize(
    ("field", "target", "actual_position", "expected"),
    [
        ("winner_driver", 1, 1, 8),
        ("winner_driver", 1, 2, 3),
        ("winner_driver", 1, 3, 2),
        ("winner_driver", 1, 4, 1),
        ("winner_driver", 1, 5, 0),
        ("fifth_driver", 5, 4, 3),
        ("fifth_driver", 5, 3, 2),
        ("fifth_driver", 5, 2, 1),
        ("fifth_driver", 5, 1, 0),
    ],
)
def test_position_offset_matrix(field, target, actual_position, expected):
    """Погрешность считается от целевой колонки, а не от позиции победителя."""
    from app.services.prediction_service import calculate_prediction_points

    prediction = {field: "RUS"}
    answers = {
        field: "VER",
        "_race_positions": {"RUS": actual_position, "VER": target},
    }
    assert calculate_prediction_points(prediction, answers) == expected


def test_incomplete_null_and_nan_prediction_is_safe():
    """Legacy/повреждённая неполная запись не вызывает KeyError и получает 0."""
    from app.services.prediction_service import calculate_prediction_points

    answers = prediction_payload() | {
        "_race_positions": {
            "VER": 1,
            "NOR": 2,
            "PIA": 3,
            "LEC": 4,
            "HAM": 5,
        }
    }
    assert calculate_prediction_points({}, answers) == 0
    assert calculate_prediction_points(
        {"winner_driver": None, "second_driver": float("nan")},
        answers,
    ) == 0
    malformed = {**answers, "_race_positions": {"VER": float("nan")}}
    assert calculate_prediction_points({"winner_driver": "VER"}, malformed) == 8


def test_actual_answers_handle_lapped_dns_dsq_and_retirement():
    """Lapped finishers, DNS/DSQ/NC не становятся «первым сходом»."""
    from app.services.prediction_service import build_actual_answers

    race = pd.DataFrame(
        [
            {"Position": 1, "Abbreviation": "VER", "Status": "Finished", "Laps": 58},
            {"Position": 2, "Abbreviation": "NOR", "Status": "+2 Laps", "Laps": 56},
            {"Position": 3, "Abbreviation": "PIA", "Status": "Lapped", "Laps": 55},
            {"Position": 4, "Abbreviation": "LEC", "Status": "Engine", "Laps": 20},
            {"Position": 5, "Abbreviation": "HAM", "Status": "Accident", "Laps": 10},
            {"Position": 18, "Abbreviation": "RUS", "Status": "Not classified", "Laps": 45},
            {"Position": 19, "Abbreviation": "ALO", "Status": "Disqualified", "Laps": 50},
            {"Position": 20, "Abbreviation": "SAI", "Status": "DNS", "Laps": 0},
        ]
    )
    answers = build_actual_answers(race, [{"position": 1, "driver": "VER"}])
    assert answers["first_retirement_driver"] == "HAM"


def test_first_retirement_tie_is_unavailable_without_timing():
    """При одинаковом числе кругов источник не позволяет честно выбрать пилота."""
    from app.services.prediction_service import build_actual_answers

    race = pd.DataFrame(
        [
            {"Position": 1, "Abbreviation": "VER", "Status": "Finished", "Laps": 58},
            {"Position": 2, "Abbreviation": "NOR", "Status": "Finished", "Laps": 58},
            {"Position": 3, "Abbreviation": "PIA", "Status": "Finished", "Laps": 58},
            {"Position": 4, "Abbreviation": "LEC", "Status": "Finished", "Laps": 58},
            {"Position": 5, "Abbreviation": "HAM", "Status": "Finished", "Laps": 58},
            {"Position": 19, "Abbreviation": "RUS", "Status": "Engine", "Laps": 7},
            {"Position": 20, "Abbreviation": "ALO", "Status": "Collision", "Laps": 7},
        ]
    )
    answers = build_actual_answers(race, [{"position": 1, "driver": "VER"}])
    assert answers["first_retirement_driver"] is None


def test_fastest_lap_time_fallback_when_rank_is_empty():
    """Пустая колонка Rank не блокирует корректный fallback по времени круга."""
    from app.services.prediction_service import build_actual_answers

    race = pd.DataFrame(
        [
            {
                "Position": position,
                "Abbreviation": code,
                "FastestLapRank": float("nan"),
                "FastestLapTime": lap,
            }
            for position, code, lap in [
                (1, "VER", "0 days 00:01:31.100"),
                (2, "NOR", "0 days 00:01:30.900"),
                (3, "PIA", "0 days 00:01:31.500"),
                (4, "LEC", "0 days 00:01:32.000"),
                (5, "HAM", "0 days 00:01:31.800"),
            ]
        ]
    )
    answers = build_actual_answers(race, [{"position": 1, "driver": "VER"}])
    assert answers["fastest_lap_driver"] == "NOR"


def test_manual_final_classification_recalculates_post_race_penalty():
    """Полный override протокола меняет позиции и пересчитывает offset после штрафа/DSQ."""
    from app.services.prediction_service import (
        build_actual_answers,
        calculate_prediction_points,
        validate_prediction_answers,
    )

    original = pd.DataFrame([
        {"Position": 1, "Abbreviation": "VER"},
        {"Position": 2, "Abbreviation": "NOR"},
        {"Position": 3, "Abbreviation": "PIA"},
        {"Position": 4, "Abbreviation": "LEC"},
        {"Position": 5, "Abbreviation": "HAM"},
    ])
    official_after_penalty = {
        "NOR": 1,
        "PIA": 2,
        "LEC": 3,
        "HAM": 4,
        "RUS": 5,
        "VER": 20,
    }
    answers = validate_prediction_answers(
        build_actual_answers(
            original,
            [{"position": 1, "driver": "VER"}],
            extra_facts={"_race_positions": official_after_penalty},
        )
    )

    assert [answers[field] for field in (
        "winner_driver",
        "second_driver",
        "third_driver",
        "fourth_driver",
        "fifth_driver",
    )] == ["NOR", "PIA", "LEC", "HAM", "RUS"]
    assert calculate_prediction_points(
        {
            "winner_driver": "VER",
            "second_driver": "NOR",
            "third_driver": "PIA",
            "fourth_driver": "LEC",
            "fifth_driver": "HAM",
        },
        answers,
    ) == 12


def test_sprint_round_waits_for_both_sprint_protocols():
    """Спринт-этап нельзя зафиксировать с неполным спринтовым протоколом."""
    from app.services.prediction_service import validate_prediction_answers

    with pytest.raises(ValueError, match="sprint"):
        validate_prediction_answers(prediction_payload(), require_sprint=True)


@pytest.mark.asyncio
async def test_prediction_schema_contains_optional_sprint_columns(api_client):
    """Миграция создаёт nullable спринт-поля и в прогнозах, и в итогах этапа."""
    from app.db import db

    async with db.conn.execute("PRAGMA table_info(prediction_profiles)") as cursor:
        profile_columns = {row["name"]: row for row in await cursor.fetchall()}
    assert "user_id" in profile_columns
    assert "telegram_id" not in profile_columns

    for table_name in ("race_predictions", "prediction_round_results"):
        async with db.conn.execute(f"PRAGMA table_info({table_name})") as cursor:
            columns = {row["name"]: row for row in await cursor.fetchall()}
        assert "sprint_pole_driver" in columns
        assert "sprint_winner_driver" in columns
        assert columns["sprint_pole_driver"]["notnull"] == 0
    async with db.conn.execute("PRAGMA table_info(prediction_round_results)") as cursor:
        result_columns = {row["name"] for row in await cursor.fetchall()}
    assert {
        "calculation_source",
        "calculation_revision",
        "calculated_by_user_id",
        "answers_hash",
    } <= result_columns
    async with db.conn.execute("PRAGMA table_info(prediction_score_runs)") as cursor:
        score_run_columns = {row["name"] for row in await cursor.fetchall()}
    assert {"revision", "answers_hash", "predictions_scored"} <= score_run_columns


@pytest.mark.asyncio
async def test_legacy_telegram_prediction_profile_migrates_to_user_id(temp_db_path):
    """Существующий Telegram-профиль прогноза сохраняется при переходе на users.id."""
    from app.db import Database

    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    cursor = await database.conn.execute("INSERT INTO users(telegram_id) VALUES (770077)")
    user_id = int(cursor.lastrowid)
    await database.conn.execute("DROP TABLE prediction_profiles")
    await database.conn.execute(
        """
        CREATE TABLE prediction_profiles (
            telegram_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await database.conn.execute(
        "INSERT INTO prediction_profiles(telegram_id, display_name) VALUES (770077, 'Legacy Racer')"
    )
    await database.conn.commit()

    await database.init_tables()

    async with database.conn.execute(
        "SELECT user_id, display_name FROM prediction_profiles"
    ) as rows:
        migrated = await rows.fetchone()
    assert migrated["user_id"] == user_id
    assert migrated["display_name"] == "Legacy Racer"
    await database.close()


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
