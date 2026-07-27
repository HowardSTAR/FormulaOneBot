import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.db import db
from app.f1_data import (
    get_driver_standings_async,
    get_qualifying_results,
    get_race_results_df,
    get_season_schedule_short_async,
    get_sprint_quali_results,
    get_sprint_results_df,
)


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
POSITION_OFFSET_POINTS = {
    1: 3,
    2: 2,
    3: 1,
}
CORE_RESULT_FIELDS = (
    "pole_driver",
    *PLACEMENT_FIELDS,
)
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
CALCULATION_SOURCES = {"scheduler", "admin", "test"}
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


def _optional_driver_code(value: Any) -> str | None:
    """Return a canonical driver code or ``None`` for missing/invalid facts."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return normalize_driver_code(value)
    except ValueError:
        return None


def _safe_positive_position(value: Any) -> int | None:
    """Accept only finite positive integer positions from an official result."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(numeric) or numeric <= 0 or not numeric.is_integer():
        return None
    return int(numeric)


def _normalize_race_positions(value: Any) -> dict[str, int]:
    """Validate a complete/partial official classification mapping."""
    if not isinstance(value, Mapping):
        raise ValueError("Порядок финиша должен быть объектом {код_пилота: позиция}")
    normalized: dict[str, int] = {}
    used_positions: set[int] = set()
    for raw_code, raw_position in value.items():
        code = normalize_driver_code(raw_code)
        position = _safe_positive_position(raw_position)
        if position is None:
            raise ValueError(f"Некорректная финишная позиция для {code}")
        if position in used_positions:
            raise ValueError("Официальный порядок содержит повторяющиеся позиции")
        normalized[code] = position
        used_positions.add(position)
    if not normalized:
        raise ValueError("Официальный порядок финиша не может быть пустым")
    return normalized


def _value_from(record: Any, field: str) -> Any:
    """Read dictionaries, sqlite rows and objects without raising on old/corrupt rows."""
    if isinstance(record, Mapping):
        return record.get(field)
    try:
        return record[field]
    except (KeyError, IndexError, TypeError):
        return getattr(record, field, None)


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


async def get_prediction_profile(user_id: int) -> dict[str, Any]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        "SELECT display_name FROM prediction_profiles WHERE user_id = ?",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return {"display_name": str(row["display_name"]) if row else "", "completed": bool(row)}


async def save_prediction_profile(user_id: int, display_name: str) -> dict[str, Any]:
    name = " ".join(str(display_name or "").split())
    if not 2 <= len(name) <= 40:
        raise ValueError("Имя участника должно содержать от 2 до 40 символов")
    if not db.conn:
        await db.connect()
    async with db.write_lock:
        await db.conn.execute(
            """
            INSERT INTO prediction_profiles(user_id, display_name)
            VALUES(?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(user_id), name),
        )
        await db.conn.commit()
    return {"display_name": name, "completed": True}


async def get_user_prediction(user_id: int, season: int, round_num: int) -> dict[str, Any] | None:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        """
        SELECT rp.* FROM race_predictions rp
        WHERE rp.user_id = ? AND rp.season = ? AND rp.round = ?
        """,
        (int(user_id), int(season), int(round_num)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_user_prediction(
    user_id: int,
    season: int,
    round_num: int,
    payload: dict[str, Any],
    allowed_driver_codes: set[str] | None = None,
    require_sprint: bool = False,
) -> dict[str, Any]:
    profile = await get_prediction_profile(user_id)
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
        code = _optional_driver_code(row.get(key))
        if code:
            return code
    return None


def _winner_from_position_rows(rows: list[dict[str, Any]] | None) -> str | None:
    """Resolve P1 only when the classification contains one unambiguous winner."""
    winners = {
        code
        for item in rows or []
        if _safe_positive_position(item.get("position")) == 1
        if (code := _optional_driver_code(item.get("driver")))
    }
    return next(iter(winners)) if len(winners) == 1 else None


def _classified_rows(results: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize an official classification and discard ambiguous duplicate facts."""
    if results is None or results.empty or "Position" not in results.columns:
        return pd.DataFrame()
    rows = results.copy()
    rows["_position"] = rows["Position"].map(_safe_positive_position)
    rows["_driver_code"] = rows.apply(_row_code, axis=1)
    rows = rows.dropna(subset=["_position", "_driver_code"])
    rows["_position"] = rows["_position"].astype(int)
    # Duplicate driver codes or positions are not a valid final classification.
    duplicate_codes = rows["_driver_code"].duplicated(keep=False)
    duplicate_positions = rows["_position"].duplicated(keep=False)
    return rows.loc[~duplicate_codes & ~duplicate_positions].sort_values("_position")


_FINISHED_STATUS = re.compile(
    r"^\s*(?:finished|lapped|\+\s*\d+\s+laps?)\s*$",
    re.IGNORECASE,
)
_NON_RETIREMENT_STATUS = re.compile(
    r"(?:did\s+not\s+start|\bdns\b|withdrawn|did\s+not\s+qualify|"
    r"disqualif|\bdsq\b|excluded|not\s+classified|^\s*nc\s*$)",
    re.IGNORECASE,
)


def _first_retirement_from_results(results: pd.DataFrame | None) -> str | None:
    """Return a defensible first retirement or ``None`` when the order is ambiguous.

    DNS, DSQ and generic NC are not retirements. A lapped classified finisher is
    also not a retirement. When two retirements have the same completed-lap count
    and the feed has no unique timing value, no points are awarded for this
    category instead of selecting a driver arbitrarily.
    """
    if results is None or results.empty or "Status" not in results.columns:
        return None
    laps_column = next(
        (name for name in ("Laps", "NumberOfLaps") if name in results.columns),
        None,
    )
    if not laps_column:
        return None

    candidates = results.copy()
    statuses = candidates["Status"].fillna("").astype(str)
    candidates = candidates.loc[
        ~statuses.str.match(_FINISHED_STATUS)
        & ~statuses.str.contains(_NON_RETIREMENT_STATUS)
    ].copy()
    candidates["_laps"] = pd.to_numeric(candidates[laps_column], errors="coerce")
    candidates["_driver_code"] = candidates.apply(_row_code, axis=1)
    candidates = candidates.dropna(subset=["_laps", "_driver_code"])
    candidates = candidates[candidates["_laps"] >= 0]
    if candidates.empty:
        return None

    first_lap_count = candidates["_laps"].min()
    earliest = candidates[candidates["_laps"] == first_lap_count].copy()
    if len(earliest.index) == 1:
        return str(earliest.iloc[0]["_driver_code"])

    # Some providers expose a terminal session-relative time for retired cars.
    # Use it only when exactly one candidate has the earliest valid timestamp.
    for column in ("RetirementTime", "RetiredAt", "Time"):
        if column not in earliest.columns:
            continue
        timed = pd.to_timedelta(earliest[column], errors="coerce")
        if not timed.notna().any():
            continue
        minimum = timed.min()
        matches = earliest[timed == minimum]
        if len(matches.index) == 1:
            return str(matches.iloc[0]["_driver_code"])
    return None


def _fastest_lap_from_results(
    classified: pd.DataFrame,
    raw_results: pd.DataFrame | None,
) -> str | None:
    if classified.empty:
        return None
    if "FastestLapRank" in classified.columns:
        ranks = pd.to_numeric(classified["FastestLapRank"], errors="coerce")
        matches = classified[ranks == 1]
        codes = set(matches["_driver_code"].dropna().astype(str))
        if len(codes) == 1:
            return next(iter(codes))

    # Some official feeds omit the rank but expose comparable lap durations.
    source = classified if "FastestLapTime" in classified.columns else raw_results
    if source is None or source.empty or "FastestLapTime" not in source.columns:
        return None
    times = pd.to_timedelta(source["FastestLapTime"], errors="coerce")
    if not times.notna().any():
        return None
    minimum = times.min()
    matches = source[times == minimum]
    codes = {
        code
        for _, row in matches.iterrows()
        if (code := _row_code(row)) is not None
    }
    return next(iter(codes)) if len(codes) == 1 else None


def build_actual_answers(
    race_results: pd.DataFrame,
    qualifying_results: list[dict[str, Any]],
    sprint_qualifying_results: list[dict[str, Any]] | None = None,
    sprint_results: pd.DataFrame | None = None,
    extra_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Строит только подтверждённые API факты; отсутствующие категории остаются None."""
    answers: dict[str, Any] = {field: None for field in PREDICTION_FIELDS}
    answers["sprint_pole_driver"] = _winner_from_position_rows(
        sprint_qualifying_results
    )
    sprint_ordered = _classified_rows(sprint_results)
    if not sprint_ordered.empty:
        sprint_winners = sprint_ordered[sprint_ordered["_position"] == 1]
        if len(sprint_winners.index) == 1:
            answers["sprint_winner_driver"] = str(
                sprint_winners.iloc[0]["_driver_code"]
            )
    answers["pole_driver"] = _winner_from_position_rows(qualifying_results)

    ordered = _classified_rows(race_results)
    if not ordered.empty:
        answers["_race_positions"] = {
            str(row["_driver_code"]): int(row["_position"])
            for _, row in ordered.iterrows()
        }
        by_position = {
            int(row["_position"]): str(row["_driver_code"])
            for _, row in ordered.iterrows()
        }
        for field, target in PLACEMENT_TARGETS.items():
            answers[field] = by_position.get(target)

        answers["fastest_lap_driver"] = _fastest_lap_from_results(
            ordered,
            race_results,
        )
        answers["first_retirement_driver"] = _first_retirement_from_results(
            race_results
        )

    manual_positions = (extra_facts or {}).get("_race_positions")
    if manual_positions is not None:
        answers["_race_positions"] = _normalize_race_positions(manual_positions)
        by_position = {
            position: code
            for code, position in answers["_race_positions"].items()
        }
        for field, target in PLACEMENT_TARGETS.items():
            answers[field] = by_position.get(target)

    for key, value in (extra_facts or {}).items():
        if key == "_race_positions":
            continue
        if key in answers and value is not None:
            if key in PLACEMENT_FIELDS:
                continue
            answers[key] = (
                normalize_driver_code(value)
                if key != "safety_car"
                else int(bool(value))
            )
    return answers


def calculate_prediction_points(prediction: Any, answers: dict[str, Any]) -> int:
    """Calculate deterministic non-negative points using the published 2026 matrix."""
    race_positions: dict[str, int] = {}
    raw_positions = answers.get("_race_positions")
    if isinstance(raw_positions, Mapping):
        for raw_code, raw_position in raw_positions.items():
            code = _optional_driver_code(raw_code)
            position = _safe_positive_position(raw_position)
            if code and position is not None:
                race_positions[code] = position
    if not race_positions:
        race_positions = {
            code: target
            for field, target in PLACEMENT_TARGETS.items()
            if (code := _optional_driver_code(answers.get(field)))
        }

    points = 0
    for field in PREDICTION_FIELDS:
        actual = answers.get(field)
        if actual is None:
            continue
        predicted = _value_from(prediction, field)
        if field in PLACEMENT_TARGETS:
            predicted_code = _optional_driver_code(predicted)
            if not predicted_code:
                continue
            actual_position = race_positions.get(predicted_code)
            if actual_position is None:
                continue
            delta = abs(actual_position - PLACEMENT_TARGETS[field])
            if delta == 0:
                points += EXACT_POINTS[field]
            else:
                points += POSITION_OFFSET_POINTS.get(delta, 0)
        elif field == "safety_car":
            if predicted in (True, False, 0, 1) and int(bool(predicted)) == int(bool(actual)):
                points += EXACT_POINTS[field]
        else:
            predicted_code = _optional_driver_code(predicted)
            actual_code = _optional_driver_code(actual)
            if predicted_code and actual_code and predicted_code == actual_code:
                points += EXACT_POINTS[field]

    max_points = sum(
        EXACT_POINTS[field]
        for field in PREDICTION_FIELDS
        if answers.get(field) is not None
    )
    return max(0, min(int(points), int(max_points)))


def validate_prediction_answers(
    answers: dict[str, Any],
    *,
    require_sprint: bool = False,
) -> dict[str, Any]:
    """Validate and canonicalize facts before any score is persisted."""
    normalized: dict[str, Any] = {field: None for field in PREDICTION_FIELDS}
    for field in DRIVER_FIELDS:
        normalized[field] = _optional_driver_code(answers.get(field))

    safety_car = answers.get("safety_car")
    if safety_car in (True, False, 0, 1):
        normalized["safety_car"] = int(bool(safety_car))

    placements = [normalized[field] for field in PLACEMENT_FIELDS]
    required_fields = (
        (*SPRINT_FIELDS, *CORE_RESULT_FIELDS)
        if require_sprint
        else CORE_RESULT_FIELDS
    )
    missing_core = [field for field in required_fields if normalized.get(field) is None]
    if missing_core:
        raise ValueError(
            "Нельзя рассчитать этап без официальных результатов: "
            + ", ".join(missing_core)
        )
    if len(set(placements)) != len(placements):
        raise ValueError("Официальная первая пятёрка содержит повторяющихся пилотов")

    race_positions: dict[str, int] = {}
    raw_positions = answers.get("_race_positions")
    if raw_positions is not None:
        race_positions = _normalize_race_positions(raw_positions)
        for field, target in PLACEMENT_TARGETS.items():
            if race_positions.get(str(normalized[field])) != target:
                raise ValueError(
                    "Первая пятёрка не совпадает с полным официальным порядком"
                )
    for field, target in PLACEMENT_TARGETS.items():
        race_positions.setdefault(str(normalized[field]), target)
    normalized["_race_positions"] = race_positions
    return normalized


def _answers_audit_payload(answers: dict[str, Any]) -> dict[str, Any]:
    return {
        **{field: answers.get(field) for field in PREDICTION_FIELDS},
        "_race_positions": dict(sorted((answers.get("_race_positions") or {}).items())),
    }


async def load_official_prediction_answers(
    season: int,
    round_num: int,
    *,
    has_sprint: bool,
    extra_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load post-session classifications from FastF1, bypassing live OpenF1 data.

    The direct synchronous loaders deliberately bypass the application's 24-hour
    result decorator, so an administrator can pick up post-race penalties during
    a recalculation.
    """
    # FastF1 uses one process-wide on-disk cache. Load sessions sequentially to
    # avoid concurrent SQLite/cache writes from several worker threads.
    race_results = await asyncio.to_thread(
        get_race_results_df,
        int(season),
        int(round_num),
    )
    qualifying_results = await asyncio.to_thread(
        get_qualifying_results,
        int(season),
        int(round_num),
        100,
    )
    if has_sprint:
        sprint_qualifying = await asyncio.to_thread(
            get_sprint_quali_results,
            int(season),
            int(round_num),
            100,
        )
        sprint_results = await asyncio.to_thread(
            get_sprint_results_df,
            int(season),
            int(round_num),
        )
    else:
        sprint_qualifying = []
        sprint_results = None
    if race_results is None or race_results.empty:
        raise ValueError("Официальный протокол гонки пока недоступен")
    return validate_prediction_answers(
        build_actual_answers(
            race_results,
            qualifying_results or [],
            sprint_qualifying_results=sprint_qualifying or [],
            sprint_results=sprint_results,
            extra_facts=extra_facts,
        ),
        require_sprint=has_sprint,
    )


async def score_prediction_round(
    season: int,
    round_num: int,
    event_name: str,
    answers: dict[str, Any],
    *,
    calculation_source: str = "scheduler",
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    if calculation_source not in CALCULATION_SOURCES:
        raise ValueError("Некорректный источник расчёта прогнозов")
    answers = validate_prediction_answers(answers)
    available_fields = [
        field for field in PREDICTION_FIELDS if answers.get(field) is not None
    ]
    max_points = sum(EXACT_POINTS[field] for field in available_fields)
    if not db.conn:
        await db.connect()

    audit_payload = _answers_audit_payload(answers)
    answers_json = json.dumps(
        audit_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    answers_hash = hashlib.sha256(answers_json.encode("utf-8")).hexdigest()
    result_values = [answers.get(field) for field in PREDICTION_FIELDS]
    async with db.write_lock:
        try:
            await db.conn.execute("BEGIN IMMEDIATE")
            async with db.conn.execute(
                """
                SELECT calculation_revision, answers_hash
                FROM prediction_round_results
                WHERE season = ? AND round = ?
                """,
                (int(season), int(round_num)),
            ) as cursor:
                previous = await cursor.fetchone()
            revision = int(previous["calculation_revision"] or 0) + 1 if previous else 1
            changed = not previous or previous["answers_hash"] != answers_hash

            await db.conn.execute(
                """
                INSERT INTO prediction_round_results(
                    season, round, event_name, sprint_pole_driver, sprint_winner_driver,
                    pole_driver, winner_driver, second_driver,
                    third_driver, fourth_driver, fifth_driver, fastest_lap_driver,
                    first_retirement_driver, safety_car, max_points,
                    calculation_source, calculation_revision, calculated_by_user_id,
                    answers_hash
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    calculation_source=excluded.calculation_source,
                    calculation_revision=excluded.calculation_revision,
                    calculated_by_user_id=excluded.calculated_by_user_id,
                    answers_hash=excluded.answers_hash,
                    calculated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(season),
                    int(round_num),
                    event_name,
                    *result_values,
                    max_points,
                    calculation_source,
                    revision,
                    int(actor_user_id) if actor_user_id is not None else None,
                    answers_hash,
                ),
            )
            async with db.conn.execute(
                "SELECT user_id, "
                + ", ".join(PREDICTION_FIELDS)
                + " FROM race_predictions WHERE season = ? AND round = ?",
                (int(season), int(round_num)),
            ) as cursor:
                predictions = await cursor.fetchall()
            for prediction in predictions:
                points = calculate_prediction_points(prediction, answers)
                if not 0 <= points <= max_points:
                    raise ArithmeticError("Расчёт прогнозов вышел за допустимые границы")
                await db.conn.execute(
                    """
                    UPDATE race_predictions
                    SET points = ?, max_points = ?, scored_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND season = ? AND round = ?
                    """,
                    (
                        points,
                        max_points,
                        prediction["user_id"],
                        int(season),
                        int(round_num),
                    ),
                )
            await db.conn.execute(
                """
                INSERT INTO prediction_score_runs(
                    season, round, revision, source, actor_user_id, answers_json,
                    answers_hash, max_points, predictions_scored
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(season),
                    int(round_num),
                    revision,
                    calculation_source,
                    int(actor_user_id) if actor_user_id is not None else None,
                    answers_json,
                    answers_hash,
                    max_points,
                    len(predictions),
                ),
            )
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise

    return {
        "max_points": max_points,
        "available_fields": available_fields,
        "scored": len(predictions),
        "revision": revision,
        "changed": changed,
        "answers_hash": answers_hash,
    }


async def recalculate_prediction_round(
    season: int,
    round_num: int,
    event_name: str,
    *,
    has_sprint: bool,
    extra_facts: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    calculation_source: str = "admin",
) -> dict[str, Any]:
    answers = await load_official_prediction_answers(
        season,
        round_num,
        has_sprint=has_sprint,
        extra_facts=extra_facts,
    )
    result = await score_prediction_round(
        season,
        round_num,
        event_name,
        answers,
        calculation_source=calculation_source,
        actor_user_id=actor_user_id,
    )
    return {**result, "answers": _answers_audit_payload(answers)}


async def get_stage_top(season: int, round_num: int, limit: int = 3) -> list[dict[str, Any]]:
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        """
        SELECT pp.display_name, rp.points, rp.max_points
        FROM race_predictions rp
        JOIN prediction_profiles pp ON pp.user_id = rp.user_id
        WHERE rp.season = ? AND rp.round = ? AND rp.points IS NOT NULL
        ORDER BY rp.points DESC, rp.updated_at ASC, rp.user_id ASC
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
        SELECT user_id, display_name
        FROM prediction_profiles
        ORDER BY display_name COLLATE NOCASE
        """
    ) as cursor:
        participants = [dict(row) for row in await cursor.fetchall()]

    async with db.conn.execute(
        """
        SELECT rp.user_id, rp.season, rp.round, rp.points, rp.max_points,
               rr.event_name
        FROM race_predictions rp
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
        by_user.setdefault(int(row["user_id"]), []).append(row)

    for participant in participants:
        history = by_user.get(int(participant["user_id"]), [])
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
            int(item["user_id"]),
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
