"""Additional race facts. Missing feeds must never mean a negative answer."""
import asyncio
import logging
import math
import re
from datetime import datetime, timezone

import fastf1
import pandas as pd
from fastf1.exceptions import DataNotLoadedError
from app.f1_data import _openf1_get, get_season_schedule_short_async

logger = logging.getLogger(__name__)


def _frame(session, name):
    try:
        value = getattr(session, name)
        return value if isinstance(value, pd.DataFrame) else pd.DataFrame()
    except (DataNotLoadedError, AttributeError):
        return pd.DataFrame()


def extract_race_facts(session):
    facts = {"fastest_lap_driver": None, "first_retirement_driver": None,
             "safety_car": None, "source": "FastF1", "laps": [],
             "retirements": [], "safety_events": [], "retirement_order_confirmed": False}
    laps = _frame(session, "laps")
    results = _frame(session, "results")
    messages = _frame(session, "race_control_messages")
    statuses = _frame(session, "session_status")
    track = _frame(session, "track_status")
    finished = "Status" in statuses and statuses["Status"].eq("Finished").any()
    if not finished:
        facts["note"] = ("Источник не предоставил статусы сессии; дополнительные факты не подтверждены."
                         if statuses.empty else "Сессия ещё не подтверждена как завершённая.")
        logger.warning("Race facts withheld: %s", facts["note"])
        return facts

    # Deleted flags require race-control messages; do not score unverified laps.
    required = {"Driver", "LapTime", "LapNumber", "Deleted"}
    if required.issubset(laps.columns) and not messages.empty:
        valid = laps[laps["Deleted"].eq(False)].copy()
        if "FastF1Generated" in valid:
            valid = valid[valid["FastF1Generated"].eq(False)]
        valid["_seconds"] = pd.to_timedelta(valid["LapTime"], errors="coerce").dt.total_seconds()
        valid = valid[(valid["_seconds"] > 0) & valid["LapNumber"].notna() & valid["Driver"].notna()]
        for _, lap in valid.iterrows():
            facts["laps"].append({"driver": str(lap["Driver"]), "lap": int(lap["LapNumber"]),
                                  "seconds": round(float(lap["_seconds"]), 3)})
        if facts["laps"]:
            fastest = min(facts["laps"], key=lambda lap: (lap["seconds"], lap["lap"]))
            facts["fastest_lap_driver"] = fastest["driver"]
            facts["fastest_lap"] = fastest

    if {"Status", "Time"}.issubset(track.columns):
        for _, event in track.iterrows():
            status = str(event["Status"])
            if status in {"4", "6", "7"}:
                facts["safety_events"].append({"type": "SC" if status == "4" else "VSC",
                                               "time": str(event["Time"]), "status": status})
        if any(event["type"] == "SC" for event in facts["safety_events"]):
            facts["safety_car"] = 1
        elif not track.empty and "Time" in statuses:
            # Confirm absence only if the feed has coverage from race start.
            starts = statuses.loc[statuses["Status"].eq("Started"), "Time"]
            first = pd.to_timedelta(track["Time"], errors="coerce").min()
            if not starts.empty and pd.notna(first) and first <= pd.to_timedelta(starts.iloc[0]):
                facts["safety_car"] = 0

    if {"Status", "Abbreviation", "DriverNumber"}.issubset(results.columns):
        for _, driver in results.iterrows():
            status = str(driver["Status"])
            if re.match(r"^(Finished|\+\d+ Laps?|Disqualified|Did not start|Did not qualify|Withdrawn)$", status, re.I):
                continue
            if not status or status.lower() in {"nan", "none"}:
                continue
            number = str(driver["DriverNumber"])
            retirement_time = None
            if {"Message", "Time"}.issubset(messages.columns):
                # A STOPPED message alone does not prove a retirement.
                pattern = rf"\bCAR\s+{re.escape(number)}\b.*\bRETIRED\b"
                confirmed = messages[messages["Message"].astype(str).str.contains(pattern, case=False, regex=True)]
                times = pd.to_datetime(confirmed["Time"], errors="coerce", utc=True).dropna()
                if not times.empty:
                    retirement_time = times.min().isoformat()
            count = driver.get("Laps", driver.get("NumberOfLaps"))
            facts["retirements"].append({"driver": str(driver["Abbreviation"]), "status": status,
                                         "laps": int(count) if pd.notna(count) else None,
                                         "time": retirement_time})
        retired = facts["retirements"]
        if retired and all(row["time"] for row in retired):
            retired.sort(key=lambda row: row["time"])
            unique_first = len(retired) == 1 or retired[0]["time"] != retired[1]["time"]
            facts["retirement_order_confirmed"] = unique_first
            if unique_first:
                facts["first_retirement_driver"] = retired[0]["driver"]
        elif len(retired) == 1:
            facts["first_retirement_driver"] = retired[0]["driver"]
            facts["retirement_order_confirmed"] = True
    return facts


def _load_race_facts(season, round_num):
    session = fastf1.get_session(int(season), int(round_num), "R")
    session.load(telemetry=False, laps=True, weather=False, messages=True)
    return extract_race_facts(session)


_FACT_FIELDS = ("fastest_lap_driver", "first_retirement_driver", "safety_car")


def _utc(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _openf1_race_session(event, sessions):
    """Match an exact scheduled race, never OpenF1's unrelated `latest` session."""
    expected = _utc(event.get("race_start_utc"))
    if expected is None:
        return None
    candidates = []
    for session in sessions or []:
        if str(session.get("session_type") or "").lower() != "race" or session.get("is_cancelled"):
            continue
        start = _utc(session.get("date_start"))
        if start is None:
            continue
        distance = abs((start - expected).total_seconds())
        if distance <= 12 * 3600:
            candidates.append((distance, session))
    candidates.sort(key=lambda item: item[0])
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        return None
    return candidates[0][1]


def extract_openf1_race_facts(session, results, laps, messages, drivers):
    """Only completed official classifications can authorize additional scoring."""
    facts = {"fastest_lap_driver": None, "first_retirement_driver": None,
             "safety_car": None, "source": "OpenF1", "laps": [],
             "retirements": [], "safety_events": [], "retirement_order_confirmed": False}
    if not isinstance(results, list) or len(results) < 10:
        facts["note"] = "OpenF1: итоговый протокол гонки ещё недоступен."
        return facts
    if not isinstance(messages, list) or not messages:
        facts["note"] = "OpenF1: сообщения дирекции гонки ещё недоступны."
        return facts
    codes = {str(d.get("driver_number")): str(d.get("name_acronym") or "").upper()
             for d in drivers or [] if d.get("driver_number") is not None}
    finishers = {str(r.get("driver_number")) for r in results if r.get("driver_number") is not None}
    if len(finishers) < 10:
        facts["note"] = "OpenF1: список участников гонки неполон."
        return facts

    deleted = set()
    for event in messages:
        message = str(event.get("message") or "")
        if "LAP TIME" in message.upper() and "DELETED" in message.upper():
            number = event.get("driver_number")
            if number is None:
                match = re.search(r"\bCAR\s+(\d+)\b", message, re.I)
                number = match.group(1) if match else None
            lap_match = re.search(r"\bLAP\s+(\d+)\b", message, re.I)
            if number is not None and lap_match:
                deleted.add((str(number), int(lap_match.group(1))))
    if isinstance(laps, list):
        lap_coverage = {}
        for lap in laps:
            number = lap.get("driver_number")
            code = codes.get(str(number))
            try:
                duration = float(lap.get("lap_duration"))
                lap_number = int(lap.get("lap_number"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(duration) or duration <= 0:
                continue
            lap_coverage[str(number)] = max(lap_coverage.get(str(number), 0), lap_number)
            if (code and str(number) in finishers and 20 < duration < 300
                    and lap_number > 0 and not lap.get("is_pit_out_lap")
                    and (str(number), lap_number) not in deleted):
                facts["laps"].append({"driver": code, "lap": lap_number,
                                      "seconds": round(duration, 3)})
        classified_finishers = [r for r in results if r.get("dnf") is False
                                and not r.get("dns") and not r.get("dsq")]
        coverage_complete = bool(classified_finishers) and all(
            lap_coverage.get(str(row.get("driver_number")), 0) >= int(row.get("number_of_laps") or 0)
            for row in classified_finishers
        )
        if facts["laps"] and coverage_complete:
            fastest = min(facts["laps"], key=lambda lap: (lap["seconds"], lap["lap"]))
            facts["fastest_lap_driver"] = fastest["driver"]
            facts["fastest_lap"] = fastest

    sc_events = []
    session_started = session_ended = False
    retirement_times = {}
    for event in messages:
        category = str(event.get("category") or "").lower()
        message = str(event.get("message") or "").upper()
        occurred = _utc(event.get("date"))
        if category == "sessionstatus":
            session_started |= "START" in message or "GREEN LIGHT" in message
            session_ended |= "END" in message or "FINISH" in message or "CHEQUERED" in message
        if "CHEQUERED" in message and category == "flag":
            session_ended = True
        if category == "safetycar" or "SAFETY CAR" in message:
            if "VIRTUAL" in message or "VSC" in message:
                kind = "VSC"
            elif "SAFETY CAR" in message or category == "safetycar":
                kind = "SC"
            else:
                continue
            if "DEPLOY" in message or "ACTIVATE" in message:
                sc_events.append({"type": kind, "time": event.get("date"), "message": message})
        if "RETIRED" in message and occurred is not None:
            number = event.get("driver_number")
            if number is None:
                match = re.search(r"\bCAR\s+(\d+)\b", message)
                number = match.group(1) if match else None
            if number is not None:
                key = str(number)
                retirement_times[key] = min(retirement_times.get(key, occurred), occurred)
    facts["safety_events"] = sc_events
    if any(event["type"] == "SC" for event in sc_events):
        facts["safety_car"] = 1
    elif session_started and session_ended:
        facts["safety_car"] = 0

    retired = []
    for result in results:
        if result.get("dnf") is not True or result.get("dns") or result.get("dsq"):
            continue
        number = str(result.get("driver_number"))
        code = codes.get(number)
        if code:
            retired.append({"driver": code, "number": number,
                            "time": retirement_times.get(number)})
    facts["retirements"] = [
        {"driver": row["driver"], "time": row["time"].isoformat() if row["time"] else None}
        for row in retired
    ]
    if len(retired) == 1:
        facts["first_retirement_driver"] = retired[0]["driver"]
        facts["retirement_order_confirmed"] = True
    elif retired and all(row["time"] for row in retired):
        retired.sort(key=lambda row: row["time"])
        if retired[0]["time"] != retired[1]["time"]:
            facts["first_retirement_driver"] = retired[0]["driver"]
            facts["retirement_order_confirmed"] = True
    return facts


async def _load_openf1_race_facts(season, round_num):
    schedule = await get_season_schedule_short_async(season)
    event = next((item for item in schedule or [] if int(item.get("round") or 0) == round_num), None)
    if event is None:
        return None
    session = _openf1_race_session(event, await _openf1_get("sessions", year=season))
    if session is None or session.get("session_key") is None:
        return None
    key = session["session_key"]
    results, laps, messages, drivers = await asyncio.gather(
        _openf1_get("session_result", session_key=key),
        _openf1_get("laps", session_key=key),
        _openf1_get("race_control", session_key=key),
        _openf1_get("drivers", session_key=key),
    )
    return extract_openf1_race_facts(session, results, laps, messages, drivers)


async def get_prediction_race_facts(season, round_num):
    fastf1_facts = None
    try:
        fastf1_facts = await asyncio.wait_for(asyncio.to_thread(_load_race_facts, season, round_num), timeout=120)
    except Exception:
        logger.exception("FastF1 prediction facts unavailable for %s/%s", season, round_num)
    if fastf1_facts is not None and all(fastf1_facts.get(field) is not None for field in _FACT_FIELDS):
        return fastf1_facts
    try:
        openf1_facts = await asyncio.wait_for(_load_openf1_race_facts(season, round_num), timeout=70)
    except Exception:
        logger.exception("OpenF1 prediction facts unavailable for %s/%s", season, round_num)
        openf1_facts = None
    if fastf1_facts is None:
        return openf1_facts or {"fastest_lap_driver": None, "first_retirement_driver": None,
                                "safety_car": None, "source": "FastF1 / OpenF1",
                                "note": "Дополнительные данные пока недоступны."}
    if openf1_facts is None:
        return fastf1_facts
    conflicts = [field for field in _FACT_FIELDS if fastf1_facts.get(field) is not None
                 and openf1_facts.get(field) is not None and fastf1_facts[field] != openf1_facts[field]]
    merged = {**fastf1_facts, "source": "FastF1 + OpenF1"}
    merged["field_sources"] = {}
    for field in _FACT_FIELDS:
        if field in conflicts:
            merged[field] = None
        elif merged.get(field) is None:
            merged[field] = openf1_facts.get(field)
            if merged[field] is not None:
                merged["field_sources"][field] = "OpenF1"
        else:
            merged["field_sources"][field] = "FastF1"
    for detail in ("laps", "retirements", "safety_events", "fastest_lap"):
        if not merged.get(detail) and openf1_facts.get(detail):
            merged[detail] = openf1_facts[detail]
    if not merged.get("retirement_order_confirmed"):
        merged["retirement_order_confirmed"] = bool(openf1_facts.get("retirement_order_confirmed"))
    if conflicts:
        merged["note"] = "Источники расходятся по: " + ", ".join(conflicts) + ". Нужна ручная проверка."
        merged["conflicts"] = conflicts
    return merged
