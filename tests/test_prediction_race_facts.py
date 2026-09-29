from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.prediction_race_facts import (
    _openf1_race_session, extract_openf1_race_facts, extract_race_facts,
    get_prediction_race_facts,
)
from app.services.prediction_service import build_actual_answers, calculate_prediction_points, prediction_breakdown


def session():
    return SimpleNamespace(
        session_status=pd.DataFrame({"Status": ["Started", "Finished"], "Time": pd.to_timedelta([0, 7200], unit="s")}),
        track_status=pd.DataFrame({"Status": ["1", "6", "7", "1"], "Time": pd.to_timedelta([0, 10, 20, 30], unit="s")}),
        results=pd.DataFrame([
            {"Abbreviation": "VER", "DriverNumber": "1", "Status": "Finished", "Laps": 60},
            {"Abbreviation": "HAM", "DriverNumber": "44", "Status": "Engine", "Laps": 10},
            {"Abbreviation": "STR", "DriverNumber": "18", "Status": "Accident", "Laps": 10},
            {"Abbreviation": "NOR", "DriverNumber": "4", "Status": "Did not start", "Laps": 0},
        ]),
        laps=pd.DataFrame([
            {"Driver": "VER", "LapTime": pd.Timedelta(seconds=90.123), "LapNumber": 2, "Deleted": False, "FastF1Generated": False},
            {"Driver": "HAM", "LapTime": pd.Timedelta(seconds=80), "LapNumber": 1, "Deleted": True, "FastF1Generated": False},
            {"Driver": "STR", "LapTime": pd.Timedelta(seconds=70), "LapNumber": 1, "Deleted": False, "FastF1Generated": True},
        ]),
        race_control_messages=pd.DataFrame({"Message": ["CAR 18 (STR) RETIRED", "CAR 44 (HAM) RETIRED"],
                                            "Time": ["2025-01-01T14:00:00Z", "2025-01-01T14:01:00Z"]}),
    )


def test_fastest_valid_lap_retirement_chronology_and_vsc():
    facts = extract_race_facts(session())
    assert facts["fastest_lap_driver"] == "VER"
    assert facts["fastest_lap"]["seconds"] == 90.123
    assert len(facts["laps"]) == 1
    assert facts["first_retirement_driver"] == "STR"
    assert [r["driver"] for r in facts["retirements"]] == ["STR", "HAM"]
    assert facts["safety_car"] == 0
    assert {e["type"] for e in facts["safety_events"]} == {"VSC"}
    source = session()
    source.track_status.loc[1, "Status"] = "4"
    assert extract_race_facts(source)["safety_car"] == 1


def test_missing_data_and_incomplete_session_are_not_negative_answers():
    source = session()
    source.track_status = pd.DataFrame()
    source.race_control_messages = pd.DataFrame()
    facts = extract_race_facts(source)
    assert all(facts[key] is None for key in ("safety_car", "first_retirement_driver", "fastest_lap_driver"))
    assert not facts["retirement_order_confirmed"]
    source = session()
    source.session_status = source.session_status.iloc[:1]
    assert extract_race_facts(source)["fastest_lap_driver"] is None


def test_tied_retirement_messages_credit_both_but_stopped_is_unconfirmed():
    source = session()
    source.race_control_messages["Time"] = "2025-01-01T14:00:00Z"
    facts = extract_race_facts(source)
    assert facts["first_retirement_drivers"] == ["HAM", "STR"]
    answers = build_actual_answers(pd.DataFrame(), [], extra_facts=facts)
    for code in ("HAM", "STR"):
        prediction = {field: None for field in answers if not field.startswith("_")}
        prediction["first_retirement_driver"] = code
        assert calculate_prediction_points(prediction, answers) == 2
        item = next(i for i in prediction_breakdown(prediction, answers) if i["key"] == "first_retirement_driver")
        assert item["status"] == "exact" and item["actual"] == ["HAM", "STR"]
    source.race_control_messages["Message"] = "CAR 18 (STR) STOPPED"
    assert extract_race_facts(source)["first_retirement_driver"] is None


def test_additional_facts_override_unsafe_lap_count_guess():
    race = pd.DataFrame([{"Position": i, "Abbreviation": code, "Status": "Engine", "Laps": i}
                         for i, code in enumerate(["VER", "HAM", "STR", "NOR", "LEC"], 1)])
    answers = build_actual_answers(race, [], extra_facts={"first_retirement_driver": None, "safety_car": 0})
    assert answers["first_retirement_driver"] is None
    assert answers["safety_car"] == 0
    assert "_race_facts" in answers


@pytest.mark.asyncio
async def test_source_failure_is_safe(monkeypatch):
    import app.services.prediction_race_facts as module
    monkeypatch.setattr(module.asyncio, "to_thread", AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(module, "_load_openf1_race_facts", AsyncMock(return_value=None))
    facts = await get_prediction_race_facts(2025, 1)
    assert facts["safety_car"] is None
    assert facts["note"]


def test_openf1_session_matches_exact_schedule_only():
    event = {"race_start_utc": "2026-09-26T14:00:00+00:00"}
    sessions = [
        {"session_type": "Race", "date_start": "2026-09-20T14:00:00+00:00", "session_key": 1},
        {"session_type": "Race", "date_start": "2026-09-26T14:02:00+00:00", "session_key": 2},
    ]
    assert _openf1_race_session(event, sessions)["session_key"] == 2
    assert _openf1_race_session(event, sessions[:1]) is None


def test_openf1_completed_race_facts_exclude_deleted_lap_and_vsc():
    results = [
        {"driver_number": number, "dnf": number in (18, 44), "dns": False,
         "dsq": False, "number_of_laps": 3 if number == 1 else 2}
        for number in (1, 18, 44, 4, 5, 6, 7, 8, 9, 10)
    ]
    drivers = [{"driver_number": number, "name_acronym": code} for number, code in
               ((1, "VER"), (18, "STR"), (44, "HAM"), (4, "NOR"), (5, "BOR"),
                (6, "HAD"), (7, "GAS"), (8, "ALO"), (9, "LEC"), (10, "ANT"))]
    laps = [{"driver_number": number, "lap_number": 2, "lap_duration": 90 + number / 100}
            for number in (1, 18, 44, 4, 5, 6, 7, 8, 9, 10)]
    laps += [{"driver_number": 1, "lap_number": 3, "lap_duration": 89},
             {"driver_number": 44, "lap_number": 1, "lap_duration": 70}]
    messages = [
        {"category": "SessionStatus", "message": "SESSION STARTED", "date": "2026-09-26T14:00:00Z"},
        {"category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED", "date": "2026-09-26T14:03:00Z"},
        {"category": "Other", "message": "CAR 44 LAP 1 LAP TIME DELETED", "date": "2026-09-26T14:04:00Z"},
        {"category": "CarEvent", "message": "CAR 18 RETIRED", "date": "2026-09-26T14:15:00Z"},
        {"category": "CarEvent", "message": "CAR 44 RETIRED", "date": "2026-09-26T14:20:00Z"},
        {"category": "SessionStatus", "message": "SESSION ENDED", "date": "2026-09-26T16:00:00Z"},
    ]
    facts = extract_openf1_race_facts({}, results, laps, messages, drivers)
    assert facts["fastest_lap_driver"] == "VER"
    assert facts["first_retirement_driver"] == "STR"
    assert facts["safety_car"] == 0  # VSC is not a physical safety car.
    messages[1]["message"] = "SAFETY CAR DEPLOYED"
    assert extract_openf1_race_facts({}, results, laps, messages, drivers)["safety_car"] == 1
    assert extract_openf1_race_facts({}, results[:3], laps, messages, drivers)["safety_car"] is None
    messages[4]["date"] = messages[3]["date"]
    assert extract_openf1_race_facts({}, results, laps, messages, drivers)["first_retirement_drivers"] == ["HAM", "STR"]
    assert extract_openf1_race_facts({}, results, laps[:2], messages, drivers)["fastest_lap_driver"] is None


def test_openf1_last_lap_chronology_only_with_clear_gap_and_tied_group():
    drivers = [{"driver_number": n, "name_acronym": code} for n, code in
               ((1, "VER"), (18, "STR"), (44, "HAM"), (4, "NOR"), (5, "LEC"),
                (6, "RUS"), (7, "GAS"), (8, "ALO"), (9, "ANT"), (10, "PIA"))]
    results = [{"driver_number": d["driver_number"], "dnf": d["name_acronym"] in {"STR", "HAM", "NOR"},
                "dns": False, "dsq": False, "number_of_laps": 9 if d["name_acronym"] in {"STR", "HAM"} else 20}
               for d in drivers]
    laps = [{"driver_number": d["driver_number"], "lap_number": 9 if d["name_acronym"] in {"STR", "HAM"} else 20,
             "date_start": "2026-09-26T11:00:00Z" if d["name_acronym"] == "STR" else
                           "2026-09-26T11:00:20Z" if d["name_acronym"] == "HAM" else "2026-09-26T11:30:00Z",
             "lap_duration": 100} for d in drivers]
    messages = [{"category": "SessionStatus", "message": "SESSION ENDED", "date": "2026-09-26T13:00:00Z"}]
    facts = extract_openf1_race_facts({}, results, laps, messages, drivers)
    assert facts["first_retirement_drivers"] == ["HAM", "STR"]
    assert facts["retirement_order_method"] == "last_lap_chronology"
    laps[1]["date_start"] = "2026-09-26T11:05:00Z"
    assert extract_openf1_race_facts({}, results, laps, messages, drivers)["first_retirement_driver"] is None


@pytest.mark.asyncio
async def test_openf1_fills_missing_facts_without_overwriting_fastf1(monkeypatch):
    import app.services.prediction_race_facts as module
    primary = {"fastest_lap_driver": "VER", "first_retirement_driver": None,
               "safety_car": None, "source": "FastF1"}
    secondary = {"fastest_lap_driver": "VER", "first_retirement_driver": "STR",
                 "safety_car": 0, "source": "OpenF1"}
    monkeypatch.setattr(module.asyncio, "to_thread", AsyncMock(return_value=primary))
    monkeypatch.setattr(module, "_load_openf1_race_facts", AsyncMock(return_value=secondary))
    facts = await get_prediction_race_facts(2026, 15)
    assert (facts["fastest_lap_driver"], facts["first_retirement_driver"], facts["safety_car"]) == ("VER", "STR", 0)
    secondary["fastest_lap_driver"] = "NOR"
    assert (await get_prediction_race_facts(2026, 15))["fastest_lap_driver"] is None


@pytest.mark.asyncio
async def test_sources_can_reconcile_same_first_retirement_group(monkeypatch):
    import app.services.prediction_race_facts as module
    primary = {"fastest_lap_driver": None, "first_retirement_driver": "STR",
               "first_retirement_drivers": ["STR"], "safety_car": None, "source": "FastF1"}
    secondary = {"fastest_lap_driver": None, "first_retirement_driver": "HAM",
                 "first_retirement_drivers": ["HAM", "STR"], "safety_car": None, "source": "OpenF1"}
    monkeypatch.setattr(module.asyncio, "to_thread", AsyncMock(return_value=primary))
    monkeypatch.setattr(module, "_load_openf1_race_facts", AsyncMock(return_value=secondary))
    facts = await get_prediction_race_facts(2026, 15)
    assert facts["first_retirement_drivers"] == ["HAM", "STR"]
    assert "first_retirement_driver" not in facts.get("conflicts", [])
