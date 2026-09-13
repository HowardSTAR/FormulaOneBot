from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.prediction_race_facts import extract_race_facts, get_prediction_race_facts
from app.services.prediction_service import build_actual_answers


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


def test_tied_or_stopped_retirement_messages_do_not_establish_first():
    source = session()
    source.race_control_messages["Time"] = "2025-01-01T14:00:00Z"
    assert extract_race_facts(source)["first_retirement_driver"] is None
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
    facts = await get_prediction_race_facts(2025, 1)
    assert facts["safety_car"] is None
    assert facts["note"]
