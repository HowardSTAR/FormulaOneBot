"""Additional race facts. Missing feeds must never mean a negative answer."""
import asyncio
import logging
import re

import fastf1
import pandas as pd
from fastf1.exceptions import DataNotLoadedError

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


async def get_prediction_race_facts(season, round_num):
    try:
        return await asyncio.wait_for(asyncio.to_thread(_load_race_facts, season, round_num), timeout=120)
    except Exception:
        logger.exception("Additional prediction facts unavailable for %s/%s", season, round_num)
        return {"fastest_lap_driver": None, "first_retirement_driver": None, "safety_car": None,
                "source": "FastF1", "note": "Дополнительные данные пока недоступны."}
