import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.db import db, get_or_create_user
from app.f1_data import get_driver_standings_async, get_season_schedule_short_async


SPRINT_FIELDS = (
    "sprint_pole_driver",
    "sprint_winner_driver",
)
PREDICTION_FIELDS = SPRINT_FIELDS + (
    "pole_driver",
    "winner_driver",
    "second_driver",
    "third_driver",
    "fourth_driver",
    "fifth_driver",
    "fastest_lap_driver",
    "first_retirement_driver",
    "safety_car",
)
DRIVER_FIELDS = PREDICTION_FIELDS[:-1]
PLACEMENT_FIELDS = (
    "winner_driver",
    "second_driver",
    "third_driver",
    "fourth_driver",
    "fifth_driver",
)
PLACEMENT_TARGETS = {
    "winner_driver": 1,
    "second_driver": 2,
    "third_driver": 3,
    "fourth_driver": 4,
    "fifth_driver": 5,
}
EXACT_POINTS = {
    "sprint_pole_driver": 3,
    "sprint_winner_driver": 3,
    "pole_driver": 3,
    "winner_driver": 8,
    "second_driver": 5,
    "third_driver": 5,
    "fourth_driver": 5,
    "fifth_driver": 5,
    "fastest_lap_driver": 2,
    "first_retirement_driver": 2,
    "safety_car": 2,
}
PREDICTION_SCORING_RULES = [
    {"key": "sprint_pole_driver", "label": "Спринт-поул", "exact": 3, "offsets": [0, 0, 0]},
    {"key": "sprint_winner_driver", "label": "Спринт-победа", "exact": 3, "offsets": [0, 0, 0]},
    {"key": "pole_driver", "label": "Поул-позиция", "exact": 3, "offsets": [0, 0, 0]},
    {"key": "winner_driver", "label": "Победитель", "exact": 8, "offsets": [3, 2, 1]},
    {"key": "second_driver", "label": "2 место", "exact": 5, "offsets": [3, 2, 1]},
    {"key": "third_driver", "label": "3 место", "exact": 5, "offsets": [3, 2, 1]},
    {"key": "fourth_driver", "label": "4 место", "exact": 5, "offsets": [3, 2, 1]},
    {"key": "fifth_driver", "label": "5 место", "exact": 5, "offsets": [3, 2, 1]},
    {"key": "fastest_lap_driver", "label": "Лучший круг", "exact": 2, "offsets": [0, 0, 0]},
    {"key": "first_retirement_driver", "label": "Сход №1", "exact": 2, "offsets": [0, 0, 0]},
    {"key": "safety_car", "label": "Машина безопасности", "exact": 2, "offsets": [0, 0, 0]},
]
EVENT_SHORT_CODES = {
    "australian": "AUS",
    "chinese": "CHN",
    "japanese": "JPN",
    "bahrain": "BHR",
    "saudi": "SAU",
    "miami": "MIA",
    "emilia": "EMI",
    "monaco": "MON",
    "spanish": "ESP",
    "barcelona": "ESP",
    "canadian": "CAN",
    "austrian": "AUT",
    "british": "GBR",
    "belgian": "BEL",
    "hungarian": "HUN",
    "dutch": "NED",
    "italian": "ITA",
    "azerbaijan": "AZE",
    "singapore": "SGP",
    "united states": "USA",
    "mexico": "MEX",
    "são paulo": "BRA",
    "sao paulo": "BRA",
    "las vegas": "LV",
    "qatar": "QAT",
    "abu dhabi": "ABU",
}


def event_short_code(event_name: str | None, round_num: int) -> str:
    normalized = str(event_name or "").strip().lower()
    for marker, code in EVENT_SHORT_CODES.items():
        if marker in normalized:
            return code
    words = [
        word
        for word in re.findall(r"[A-Za-zА-Яа-яЁё]+", str(event_name or ""))
        if word.lower() not in {"grand", "prix", "гран", "при"}
    ]
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(word[0] for word in words[:3]).upper() or f"R{round_num}"


def normalize_driver_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,4}", code):
        raise ValueError("Некорректный код пилота")
    return code


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


async def get_prediction_context(now_utc: datetime | None = None) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    season = now.year
    schedule = await get_season_schedule_short_async(season) or []
    candidates = []
    for event in schedule:
        if event.get("is_cancelled"):
            continue
        race_at = parse_utc(event.get("race_start_utc"))
        if race_at and now <= race_at + timedelta(hours=6):
            candidates.append((race_at, event))
    if not candidates:
        return {
            "status": "unavailable",
            "season": season,
            "round": None,
            "has_sprint": False,
            "is_open": False,
        }

    _, event = min(candidates, key=lambda item: item[0])
    has_sprint = bool(event.get("sprint_start_utc") or event.get("sprint_quali_start_utc"))
    deadline = parse_utc(
        event.get("sprint_quali_start_utc") if has_sprint else event.get("quali_start_utc")
    )
    return {
        "status": "ok",
        "season": season,
        "round": int(event["round"]),
        "event_name": event.get("event_name") or "Гран-при",
        "deadline_utc": deadline.isoformat() if deadline else None,
        "race_start_utc": event.get("race_start_utc"),
        "has_sprint": has_sprint,
        "is_open": bool(deadline and now < deadline),
    }


async def get_prediction_drivers(season: int) -> list[dict[str, str]]:
    standings = await get_driver_standings_async(season)
    if standings is None or standings.empty:
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in standings.iterrows():
        code = str(row.get("driverCode") or row.get("Abbreviation") or "").strip().upper()
        if not code or code in seen:
            continue
        given = str(row.get("givenName") or row.get("FirstName") or "").strip()
        family = str(row.get("familyName") or row.get("LastName") or "").strip()
        name = f"{given} {family}".strip() or code
        seen.add(code)
        result.append({"code": code, "name": name})
    return result


async def get_prediction_profile(telegram_id: int) -> dict[str, Any]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        "SELECT display_name FROM prediction_profiles WHERE telegram_id = ?",
        (int(telegram_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return {"display_name": str(row["display_name"]) if row else "", "completed": bool(row)}


async def save_prediction_profile(telegram_id: int, display_name: str) -> dict[str, Any]:
    name = " ".join(str(display_name or "").split())
    if not 2 <= len(name) <= 40:
        raise ValueError("Имя участника должно содержать от 2 до 40 символов")
    if not db.conn:
        await db.connect()
    await get_or_create_user(telegram_id)
    async with db.write_lock:
        await db.conn.execute(
            """
            INSERT INTO prediction_profiles(telegram_id, display_name)
            VALUES(?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                display_name = excluded.display_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(telegram_id), name),
        )
        await db.conn.commit()
    return {"display_name": name, "completed": True}


async def get_user_prediction(telegram_id: int, season: int, round_num: int) -> dict[str, Any] | None:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        """
        SELECT rp.* FROM race_predictions rp
        JOIN users u ON u.id = rp.user_id
        WHERE u.telegram_id = ? AND rp.season = ? AND rp.round = ?
        """,
        (int(telegram_id), int(season), int(round_num)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_user_prediction(
    telegram_id: int,
    season: int,
    round_num: int,
    payload: dict[str, Any],
    allowed_driver_codes: set[str] | None = None,
    require_sprint: bool = False,
) -> dict[str, Any]:
    profile = await get_prediction_profile(telegram_id)
    if not profile["completed"]:
        raise ValueError("Сначала укажите имя участника")

    normalized: dict[str, Any] = {}
    for field in DRIVER_FIELDS:
        if field in SPRINT_FIELDS and not require_sprint:
            normalized[field] = None
            continue
        normalized[field] = normalize_driver_code(payload.get(field))
        if allowed_driver_codes and normalized[field] not in allowed_driver_codes:
            raise ValueError(f"Пилот {normalized[field]} отсутствует в текущем сезоне")
    if len({normalized[field] for field in PLACEMENT_FIELDS}) != len(PLACEMENT_FIELDS):
        raise ValueError("Пилоты в первой пятёрке не должны повторяться")

    safety_car = payload.get("safety_car")
    if not isinstance(safety_car, bool):
        raise ValueError("Для машины безопасности выберите Да или Нет")
    normalized["safety_car"] = int(safety_car)

    user_id = await get_or_create_user(telegram_id)
    values = [normalized[field] for field in PREDICTION_FIELDS]
    async with db.write_lock:
        await db.conn.execute(
            """
            INSERT INTO race_predictions(
                user_id, season, round, sprint_pole_driver, sprint_winner_driver,
                pole_driver, winner_driver, second_driver,
                third_driver, fourth_driver, fifth_driver, fastest_lap_driver,
                first_retirement_driver, safety_car
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, season, round) DO UPDATE SET
                sprint_pole_driver=excluded.sprint_pole_driver,
                sprint_winner_driver=excluded.sprint_winner_driver,
                pole_driver=excluded.pole_driver,
                winner_driver=excluded.winner_driver,
                second_driver=excluded.second_driver,
                third_driver=excluded.third_driver,
                fourth_driver=excluded.fourth_driver,
                fifth_driver=excluded.fifth_driver,
                fastest_lap_driver=excluded.fastest_lap_driver,
                first_retirement_driver=excluded.first_retirement_driver,
                safety_car=excluded.safety_car,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, int(season), int(round_num), *values),
        )
        await db.conn.commit()
    return normalized


def _row_code(row: pd.Series) -> str | None:
    for key in ("Abbreviation", "DriverCode", "driverCode"):
        value = row.get(key)
        if value is not None and not pd.isna(value):
            code = str(value).strip().upper()
            if code and code != "?":
                return code
    return None


def build_actual_answers(
    race_results: pd.DataFrame,
    qualifying_results: list[dict[str, Any]],
    sprint_qualifying_results: list[dict[str, Any]] | None = None,
    sprint_results: pd.DataFrame | None = None,
    extra_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Строит только подтверждённые API факты; отсутствующие категории остаются None."""
    answers: dict[str, Any] = {field: None for field in PREDICTION_FIELDS}
    if sprint_qualifying_results:
        sprint_pole = min(
            sprint_qualifying_results,
            key=lambda item: int(item.get("position") or 999),
        )
        answers["sprint_pole_driver"] = (
            str(sprint_pole.get("driver") or "").strip().upper() or None
        )
    if sprint_results is not None and not sprint_results.empty and "Position" in sprint_results.columns:
        sprint_ordered = sprint_results.copy()
        sprint_ordered["_position"] = pd.to_numeric(sprint_ordered["Position"], errors="coerce")
        sprint_ordered = sprint_ordered.dropna(subset=["_position"]).sort_values("_position")
        if not sprint_ordered.empty:
            answers["sprint_winner_driver"] = _row_code(sprint_ordered.iloc[0])
    if qualifying_results:
        pole = min(qualifying_results, key=lambda item: int(item.get("position") or 999))
        answers["pole_driver"] = str(pole.get("driver") or "").strip().upper() or None

    if race_results is not None and not race_results.empty and "Position" in race_results.columns:
        ordered = race_results.copy()
        ordered["_position"] = pd.to_numeric(ordered["Position"], errors="coerce")
        ordered = ordered.dropna(subset=["_position"]).sort_values("_position")
        answers["_race_positions"] = {
            code: int(row["_position"])
            for _, row in ordered.iterrows()
            if (code := _row_code(row)) is not None
        }
        top = [_row_code(row) for _, row in ordered.head(5).iterrows()]
        if len(top) == 5 and all(top):
            for field, code in zip(PLACEMENT_FIELDS, top):
                answers[field] = code

        fastest_row = None
        if "FastestLapRank" in ordered.columns:
            rank = pd.to_numeric(ordered["FastestLapRank"], errors="coerce")
            matches = ordered[rank == 1]
            if not matches.empty:
                fastest_row = matches.iloc[0]
        elif "FastestLapTime" in ordered.columns:
            lap_times = pd.to_timedelta(ordered["FastestLapTime"], errors="coerce")
            if lap_times.notna().any():
                fastest_row = ordered.loc[lap_times.idxmin()]
        if fastest_row is not None:
            answers["fastest_lap_driver"] = _row_code(fastest_row)

        status_column = "Status" if "Status" in ordered.columns else None
        laps_column = next((name for name in ("Laps", "NumberOfLaps") if name in ordered.columns), None)
        if status_column and laps_column:
            retired = ordered[
                ~ordered[status_column].astype(str).str.match(r"^(Finished|\+\d+ Lap)", case=False, na=False)
            ].copy()
            retired["_laps"] = pd.to_numeric(retired[laps_column], errors="coerce")
            retired = retired.dropna(subset=["_laps"]).sort_values("_laps")
            if not retired.empty:
                answers["first_retirement_driver"] = _row_code(retired.iloc[0])

    for key, value in (extra_facts or {}).items():
        if key in answers and value is not None:
            answers[key] = normalize_driver_code(value) if key != "safety_car" else int(bool(value))
    return answers


def calculate_prediction_points(prediction: Any, answers: dict[str, Any]) -> int:
    """Начисляет баллы по матрице сезона-2026 из правил прогнозов."""
    race_positions = dict(answers.get("_race_positions") or {})
    if not race_positions:
        race_positions = {
            str(answers[field]): target
            for field, target in PLACEMENT_TARGETS.items()
            if answers.get(field)
        }

    points = 0
    for field in PREDICTION_FIELDS:
        actual = answers.get(field)
        if actual is None:
            continue
        predicted = prediction[field]
        if field in PLACEMENT_TARGETS:
            actual_position = race_positions.get(str(predicted))
            if actual_position is None:
                continue
            delta = abs(actual_position - PLACEMENT_TARGETS[field])
            if delta == 0:
                points += EXACT_POINTS[field]
            elif delta == 1:
                points += 3
            elif delta == 2:
                points += 2
            elif delta == 3:
                points += 1
        elif predicted == actual:
            points += EXACT_POINTS[field]
    return points


async def score_prediction_round(
    season: int,
    round_num: int,
    event_name: str,
    answers: dict[str, Any],
) -> dict[str, Any]:
    available_fields = [field for field in PREDICTION_FIELDS if answers.get(field) is not None]
    max_points = sum(EXACT_POINTS[field] for field in available_fields)
    if not db.conn:
        await db.connect()

    result_values = [answers.get(field) for field in PREDICTION_FIELDS]
    async with db.write_lock:
        await db.conn.execute(
            """
            INSERT INTO prediction_round_results(
                season, round, event_name, sprint_pole_driver, sprint_winner_driver,
                pole_driver, winner_driver, second_driver,
                third_driver, fourth_driver, fifth_driver, fastest_lap_driver,
                first_retirement_driver, safety_car, max_points
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season, round) DO UPDATE SET
                event_name=excluded.event_name,
                sprint_pole_driver=excluded.sprint_pole_driver,
                sprint_winner_driver=excluded.sprint_winner_driver,
                pole_driver=excluded.pole_driver,
                winner_driver=excluded.winner_driver,
                second_driver=excluded.second_driver,
                third_driver=excluded.third_driver,
                fourth_driver=excluded.fourth_driver,
                fifth_driver=excluded.fifth_driver,
                fastest_lap_driver=excluded.fastest_lap_driver,
                first_retirement_driver=excluded.first_retirement_driver,
                safety_car=excluded.safety_car,
                max_points=excluded.max_points,
                calculated_at=CURRENT_TIMESTAMP
            """,
            (int(season), int(round_num), event_name, *result_values, max_points),
        )
        async with db.conn.execute(
            "SELECT user_id, " + ", ".join(PREDICTION_FIELDS) +
            " FROM race_predictions WHERE season = ? AND round = ?",
            (int(season), int(round_num)),
        ) as cursor:
            predictions = await cursor.fetchall()
        for prediction in predictions:
            points = calculate_prediction_points(prediction, answers)
            await db.conn.execute(
                """
                UPDATE race_predictions SET points = ?, max_points = ?, scored_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND season = ? AND round = ?
                """,
                (points, max_points, prediction["user_id"], int(season), int(round_num)),
            )
        await db.conn.commit()

    return {"max_points": max_points, "available_fields": available_fields, "scored": len(predictions)}


async def get_stage_top(season: int, round_num: int, limit: int = 3) -> list[dict[str, Any]]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        """
        SELECT pp.display_name, rp.points, rp.max_points
        FROM race_predictions rp
        JOIN users u ON u.id = rp.user_id
        JOIN prediction_profiles pp ON pp.telegram_id = u.telegram_id
        WHERE rp.season = ? AND rp.round = ? AND rp.points IS NOT NULL
        ORDER BY rp.points DESC, rp.updated_at ASC, pp.display_name COLLATE NOCASE
        LIMIT ?
        """,
        (int(season), int(round_num), int(limit)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_prediction_leaderboard() -> dict[str, Any]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        "SELECT MAX(season) AS season FROM prediction_round_results"
    ) as cursor:
        latest_round = await cursor.fetchone()
    leaderboard_season = int(latest_round["season"]) if latest_round and latest_round["season"] else datetime.now(timezone.utc).year

    async with db.conn.execute(
        """
        SELECT telegram_id, display_name
        FROM prediction_profiles
        ORDER BY display_name COLLATE NOCASE
        """
    ) as cursor:
        participants = [dict(row) for row in await cursor.fetchall()]

    async with db.conn.execute(
        """
        SELECT u.telegram_id, rp.season, rp.round, rp.points, rp.max_points,
               rr.event_name
        FROM race_predictions rp
        JOIN users u ON u.id = rp.user_id
        LEFT JOIN prediction_round_results rr
          ON rr.season = rp.season AND rr.round = rp.round
        WHERE rp.points IS NOT NULL AND rp.season = ?
        ORDER BY rp.season, rp.round
        """,
        (leaderboard_season,),
    ) as cursor:
        score_rows = [dict(row) for row in await cursor.fetchall()]

    async with db.conn.execute(
        """
        SELECT season, round, event_name, max_points
        FROM prediction_round_results
        WHERE season = ?
        ORDER BY season, round
        """,
        (leaderboard_season,),
    ) as cursor:
        rounds = [dict(row) for row in await cursor.fetchall()]

    round_max: dict[tuple[int, int], int] = {}
    by_user: dict[int, list[dict[str, Any]]] = {}
    for row in score_rows:
        key = (int(row["season"]), int(row["round"]))
        round_max[key] = max(round_max.get(key, 0), int(row["points"] or 0))
        by_user.setdefault(int(row["telegram_id"]), []).append(row)

    for participant in participants:
        history = by_user.get(int(participant["telegram_id"]), [])
        total_points = sum(int(row["points"] or 0) for row in history)
        participant["total_points"] = total_points
        participant["rounds_scored"] = len(history)
        participant["best_points"] = max((int(row["points"] or 0) for row in history), default=0)
        participant["average_points"] = round(total_points / len(history), 1) if history else 0.0
        participant["wins"] = sum(
            1
            for row in history
            if int(row["points"] or 0) > 0
            and int(row["points"] or 0)
            == round_max[(int(row["season"]), int(row["round"]))]
        )
        participant["history"] = [
            {
                **row,
                "short_code": event_short_code(row.get("event_name"), int(row["round"])),
            }
            for row in history
        ]

    participants.sort(
        key=lambda item: (
            -int(item["total_points"]),
            -int(item["wins"]),
            -int(item["best_points"]),
            str(item["display_name"]).casefold(),
        )
    )
    for place, participant in enumerate(participants, start=1):
        participant["place"] = place

    return {
        "season": leaderboard_season,
        "entries": participants,
        "rounds": [
            {
                **round_info,
                "short_code": event_short_code(
                    round_info.get("event_name"),
                    int(round_info["round"]),
                ),
            }
            for round_info in rounds
        ],
    }


async def get_notification_state(season: int, round_num: int) -> dict[str, bool]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        "SELECT opened_sent, results_sent FROM prediction_notification_state WHERE season=? AND round=?",
        (int(season), int(round_num)),
    ) as cursor:
        row = await cursor.fetchone()
    return {
        "opened_sent": bool(row["opened_sent"]) if row else False,
        "results_sent": bool(row["results_sent"]) if row else False,
    }


async def mark_notification_state(season: int, round_num: int, field: str) -> None:
    if field not in {"opened_sent", "results_sent"}:
        raise ValueError("Некорректное поле состояния уведомления")
    if not db.conn:
        await db.connect()
    async with db.write_lock:
        await db.conn.execute(
            f"""
            INSERT INTO prediction_notification_state(season, round, {field}) VALUES(?, ?, 1)
            ON CONFLICT(season, round) DO UPDATE SET {field}=1
            """,
            (int(season), int(round_num)),
        )
        await db.conn.commit()
