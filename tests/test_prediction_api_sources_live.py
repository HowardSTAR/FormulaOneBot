"""Opt-in, read-only comparison of every prediction field for the latest finished race.

Run with output visible:
    $env:RUN_LIVE_PREDICTION_APIS='1'
    python -m unittest discover -s tests -p test_prediction_api_sources_live.py -v

Optional: set PREDICTION_TEST_SEASON and PREDICTION_TEST_ROUND to inspect a specific race.
This test never reads or changes the prediction database and never recalculates scores.
"""

import asyncio
import math
import os
import unittest
from datetime import datetime, timedelta, timezone

import aiohttp
import fastf1
import pandas as pd

from app.f1_data import OPENF1_BASE, _profile_http_session, get_season_schedule_short_async
from app.services.prediction_race_facts import (
    _openf1_race_session, _utc, extract_openf1_race_facts, extract_race_facts,
)
from app.services.prediction_service import (
    PREDICTION_FIELDS, PREDICTION_SCORING_RULES, build_actual_answers,
)


LABELS = {rule["key"]: rule["label"] for rule in PREDICTION_SCORING_RULES}
SPRINT_FIELDS = {"sprint_pole_driver", "sprint_winner_driver"}


def _latest_completed_event(schedule):
    round_override = os.getenv("PREDICTION_TEST_ROUND")
    if round_override:
        return next((event for event in schedule if int(event.get("round") or 0) == int(round_override)), None)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    completed = [event for event in schedule if (start := _utc(event.get("race_start_utc")))
                 and start < cutoff]
    return max(completed, key=lambda event: _utc(event["race_start_utc"])) if completed else None


def _empty_answers():
    return {field: None for field in PREDICTION_FIELDS}


def _format_answers(answers, sprint_weekend, names, retirement_candidate=None):
    lines = []
    for field in PREDICTION_FIELDS:
        value = answers.get(field)
        if field in SPRINT_FIELDS and not sprint_weekend:
            rendered = "НЕ ПРИМЕНИМО (без спринта)"
        elif value is None:
            if field == "first_retirement_driver" and retirement_candidate:
                code = retirement_candidate["driver"]
                rendered = (f"НЕТ ПОДТВЕРЖДЁННОГО ФАКТА · диагностический кандидат {code}"
                            f" — {names.get(code, code)} (условия расчёта не выполнены)")
            else:
                rendered = "НЕТ ДАННЫХ"
        elif field == "safety_car":
            rendered = "Да" if value else "Нет"
        else:
            rendered = f"{value} — {names[value]}" if value in names else str(value)
        lines.append(f"  {LABELS[field]:23} [{field}]: {rendered}")
    return "\n".join(lines)


def _fastf1_session(season, round_num, kind, *, messages=False):
    try:
        session = fastf1.get_session(season, round_num, kind)
        session.load(telemetry=False, laps=messages, weather=False, messages=messages)
        return session, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _fastf1_report(season, round_num, sprint_weekend):
    errors = {}
    race, errors["Race"] = _fastf1_session(season, round_num, "R", messages=True)
    if race is None:
        # The classification may exist even when timing/race-control data fail.
        race, fallback_error = _fastf1_session(season, round_num, "R")
        if fallback_error:
            errors["Race classification"] = fallback_error
    quali, errors["Qualifying"] = _fastf1_session(season, round_num, "Q")
    sprint = sprint_quali = None
    if sprint_weekend:
        sprint, errors["Sprint"] = _fastf1_session(season, round_num, "S")
        sprint_quali, errors["Sprint Qualifying"] = _fastf1_session(season, round_num, "SQ")
        if sprint_quali is None:
            sprint_quali, errors["Sprint Shootout"] = _fastf1_session(season, round_num, "SS")

    def classification(session):
        return session.results if session is not None and session.results is not None else pd.DataFrame()

    def qualifying_rows(session):
        frame = classification(session)
        if frame.empty or not {"Position", "Abbreviation"}.issubset(frame.columns):
            return []
        return [{"position": int(row.Position), "driver": str(row.Abbreviation)}
                for row in frame.itertuples(index=False)
                if pd.notna(row.Position) and pd.notna(row.Abbreviation)]

    facts = extract_race_facts(race) if race is not None else {}
    answers = build_actual_answers(
        classification(race), qualifying_rows(quali), qualifying_rows(sprint_quali),
        classification(sprint), extra_facts=facts,
    )
    counts = {"race_results": len(classification(race)),
              "qualifying_results": len(classification(quali)),
              "sprint_results": len(classification(sprint)),
              "sprint_qualifying_results": len(classification(sprint_quali)),
              "valid_laps": len(facts.get("laps") or []),
              "retirement_events": len(facts.get("retirements") or []),
              "safety_events": len(facts.get("safety_events") or [])}
    names = {}
    for session in (race, quali, sprint, sprint_quali):
        frame = classification(session)
        if {"Abbreviation", "FullName"}.issubset(frame.columns):
            names.update({str(row.Abbreviation): str(row.FullName) for row in frame.itertuples(index=False)
                          if pd.notna(row.Abbreviation) and pd.notna(row.FullName)})
    return answers, facts, counts, names, {key: value for key, value in errors.items() if value}


async def _openf1_fetch(path, **params):
    token = (os.getenv("OPENF1_ACCESS_TOKEN") or os.getenv("OPENF1_API_KEY") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        async with _profile_http_session() as client:
            async with client.get(f"{OPENF1_BASE}/{path}", params=params,
                                  headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return None, f"HTTP {response.status}"
                payload = await response.json()
                if not isinstance(payload, list):
                    return None, "Ответ API не является списком записей"
                return payload, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _openf1_session(sessions, expected_start, names):
    expected = _utc(expected_start)
    if expected is None or not isinstance(sessions, list):
        return None
    candidates = []
    for session in sessions:
        name = str(session.get("session_name") or "").lower()
        kind = str(session.get("session_type") or "").lower()
        started = _utc(session.get("date_start"))
        if not started or session.get("is_cancelled") or not ({name, kind} & names):
            continue
        distance = abs((started - expected).total_seconds())
        if distance <= 12 * 3600:
            candidates.append((distance, session))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else None


def _last_lap_retirement_candidate(results, laps, drivers):
    """Diagnostic inference only: never feed this into prediction scoring."""
    codes = {str(driver.get("driver_number")): str(driver.get("name_acronym") or "").upper()
             for driver in drivers or [] if driver.get("driver_number") is not None}
    last_laps = {}
    for lap in laps or []:
        number = str(lap.get("driver_number"))
        try:
            lap_number = int(lap.get("lap_number"))
            duration = float(lap.get("lap_duration"))
        except (TypeError, ValueError):
            continue
        started = _utc(lap.get("date_start"))
        if started is None or lap_number < 1 or not math.isfinite(duration) or duration <= 0:
            continue
        previous = last_laps.get(number)
        if previous is None or lap_number > previous[0]:
            last_laps[number] = (lap_number, started + timedelta(seconds=duration))
    chronology = []
    for row in results or []:
        if row.get("dnf") is not True or row.get("dns") or row.get("dsq"):
            continue
        number = str(row.get("driver_number"))
        last = last_laps.get(number)
        try:
            official_laps = int(row.get("number_of_laps"))
        except (TypeError, ValueError):
            official_laps = None
        chronology.append({"driver": codes.get(number, number),
                           "official_laps": official_laps,
                           "last_lap": last[0] if last else None,
                           "last_lap_end": last[1] if last else None})
    chronology.sort(key=lambda row: row["last_lap_end"] or datetime.max.replace(tzinfo=timezone.utc))
    complete = len(chronology) >= 2 and all(
        row["last_lap_end"] is not None and row["official_laps"] is not None
        and row["last_lap"] >= row["official_laps"] for row in chronology
    )
    candidate = None
    if complete:
        gap = (chronology[1]["last_lap_end"] - chronology[0]["last_lap_end"]).total_seconds()
        if gap >= 600:
            candidate = {"driver": chronology[0]["driver"], "gap_seconds": round(gap)}
    printable = [{**row, "last_lap_end": row["last_lap_end"].isoformat() if row["last_lap_end"] else None}
                 for row in chronology]
    return candidate, printable


class RetirementChronologyDiagnosticTest(unittest.TestCase):
    def test_clear_gap_is_only_a_candidate(self):
        results = [{"driver_number": 18, "dnf": True, "number_of_laps": 7},
                   {"driver_number": 14, "dnf": True, "number_of_laps": 20}]
        drivers = [{"driver_number": 18, "name_acronym": "STR"},
                   {"driver_number": 14, "name_acronym": "ALO"}]
        laps = [{"driver_number": 18, "lap_number": 7, "lap_duration": 105,
                 "date_start": "2026-09-26T11:12:00Z"},
                {"driver_number": 14, "lap_number": 20, "lap_duration": 105,
                 "date_start": "2026-09-26T11:40:00Z"}]
        candidate, chronology = _last_lap_retirement_candidate(results, laps, drivers)
        self.assertEqual(candidate["driver"], "STR")
        self.assertEqual([row["driver"] for row in chronology], ["STR", "ALO"])
        laps[1]["date_start"] = "2026-09-26T11:15:00Z"
        self.assertIsNone(_last_lap_retirement_candidate(results, laps, drivers)[0])


async def _openf1_report(season, event, sprint_weekend):
    errors = {}
    sessions, errors["sessions"] = await _openf1_fetch("sessions", year=season)
    race = _openf1_race_session(event, sessions)
    quali = _openf1_session(sessions, event.get("quali_start_utc"), {"qualifying"})
    sprint = _openf1_session(sessions, event.get("sprint_start_utc"), {"sprint"}) if sprint_weekend else None
    sprint_quali = (_openf1_session(sessions, event.get("sprint_quali_start_utc"),
                                  {"sprint qualifying", "sprint shootout"}) if sprint_weekend else None)
    selected = {"Race": race, "Qualifying": quali, "Sprint": sprint,
                "Sprint Qualifying": sprint_quali}
    payloads = {}
    for label, session in selected.items():
        if session is None:
            if label in {"Race", "Qualifying"} or sprint_weekend:
                errors[label] = "Сессия нужного этапа не найдена"
            continue
        key = session.get("session_key")
        if key is None:
            errors[label] = "Нет session_key"
            continue
        result, error = await _openf1_fetch("session_result", session_key=key)
        payloads[label] = result or []
        if error:
            errors[f"{label} session_result"] = error

    race_key = race.get("session_key") if race else None
    if race_key is not None:
        (race_drivers, driver_error), (laps, lap_error), (messages, control_error) = await asyncio.gather(
            _openf1_fetch("drivers", session_key=race_key),
            _openf1_fetch("laps", session_key=race_key),
            _openf1_fetch("race_control", session_key=race_key),
        )
        for label, error in (("drivers", driver_error), ("laps", lap_error),
                             ("race_control", control_error)):
            if error:
                errors[label] = error
    else:
        race_drivers = laps = messages = None
    drivers = race_drivers or []
    codes = {str(driver.get("driver_number")): str(driver.get("name_acronym") or "").upper()
             for driver in drivers if driver.get("driver_number") is not None}
    names = {str(driver.get("name_acronym") or "").upper(): str(driver.get("full_name") or "")
             for driver in drivers if driver.get("name_acronym")}

    def ordered(label):
        rows = []
        for item in payloads.get(label, []):
            try:
                position = int(item.get("position"))
            except (TypeError, ValueError):
                continue
            code = codes.get(str(item.get("driver_number")))
            if position > 0 and code:
                rows.append((position, code))
        return [code for _, code in sorted(rows)]

    answers = _empty_answers()
    for label, field in (("Qualifying", "pole_driver"),
                         ("Sprint Qualifying", "sprint_pole_driver"),
                         ("Sprint", "sprint_winner_driver")):
        sequence = ordered(label)
        if sequence:
            answers[field] = sequence[0]
    race_order = ordered("Race")
    for index, field in enumerate(("winner_driver", "second_driver", "third_driver",
                                   "fourth_driver", "fifth_driver")):
        if len(race_order) >= 5:
            answers[field] = race_order[index]
    facts = extract_openf1_race_facts(race or {}, payloads.get("Race"), laps, messages, drivers)
    retirement_candidate, retirement_chronology = _last_lap_retirement_candidate(
        payloads.get("Race"), laps, drivers)
    for field in ("fastest_lap_driver", "first_retirement_driver", "safety_car"):
        answers[field] = facts.get(field)
    counts = {"sessions": len(sessions or []), "race_results": len(payloads.get("Race", [])),
              "qualifying_results": len(payloads.get("Qualifying", [])),
              "sprint_results": len(payloads.get("Sprint", [])),
              "sprint_qualifying_results": len(payloads.get("Sprint Qualifying", [])),
              "drivers": len(drivers), "laps": len(laps or []),
              "race_control_messages": len(messages or [])}
    keys = {label: session.get("session_key") for label, session in selected.items() if session}
    return (answers, facts, counts, names, keys, retirement_candidate,
            retirement_chronology, {key: value for key, value in errors.items() if value})


@unittest.skipUnless(os.getenv("RUN_LIVE_PREDICTION_APIS") == "1", "Включите RUN_LIVE_PREDICTION_APIS=1")
class LivePredictionApiSourcesTest(unittest.IsolatedAsyncioTestCase):
    async def test_latest_race_prediction_fields_from_fastf1_and_openf1(self):
        season = int(os.getenv("PREDICTION_TEST_SEASON") or datetime.now(timezone.utc).year)
        schedule = await get_season_schedule_short_async(season)
        event = _latest_completed_event(schedule or [])
        if event is None:
            self.fail(f"Нет завершённой гонки в расписании {season}; укажите PREDICTION_TEST_SEASON/ROUND")
        round_num = int(event["round"])
        sprint_weekend = bool(event.get("sprint_start_utc") or event.get("sprint_quali_start_utc"))
        print(f"\nГОНКА: {event.get('event_name')} · сезон {season}, этап {round_num}", flush=True)
        print(f"Старт (UTC): {event.get('race_start_utc')} · спринт: {'да' if sprint_weekend else 'нет'}", flush=True)
        fast_answers, fast_facts, fast_counts, fast_names, fast_errors = await asyncio.to_thread(
            _fastf1_report, season, round_num, sprint_weekend)
        (open_answers, open_facts, open_counts, open_names, session_keys,
         retirement_candidate, retirement_chronology, open_errors) = await _openf1_report(
            season, event, sprint_weekend)
        for name, answers, facts, counts, names, errors in (
            ("FastF1", fast_answers, fast_facts, fast_counts, fast_names, fast_errors),
            ("OpenF1", open_answers, open_facts, open_counts, open_names, open_errors),
        ):
            print(f"\n=== {name} ===")
            if name == "OpenF1":
                print(f"Ключи сессий: {session_keys}")
            print(f"Получено записей: {counts}")
            print(_format_answers(answers, sprint_weekend, names,
                                  retirement_candidate if name == "OpenF1" else None))
            print(f"Лучший круг: {facts.get('fastest_lap') or 'нет подтверждённого времени'}")
            print(f"Первая группа схода для расчёта: {facts.get('first_retirement_drivers') or 'не установлена'}"
                  f" · метод: {facts.get('retirement_order_method') or '—'}")
            print(f"Сходы по времени: {facts.get('retirements') or 'нет подтверждённой последовательности'}")
            if name == "OpenF1":
                print(f"Последние круги сошедших: {retirement_chronology}")
                if retirement_candidate:
                    print(f"Независимая диагностическая проверка: {retirement_candidate['driver']}"
                          f" · отрыв до следующего последнего круга {retirement_candidate['gap_seconds']} с"
                          " · это вывод из хронологии, не сообщение дирекции гонки")
            print(f"События SC/VSC: {facts.get('safety_events') or 'нет подтверждённых событий'}")
            if facts.get("note"):
                print(f"Примечание: {facts['note']}")
            for label, error in errors.items():
                print(f"Ошибка {label}: {error}")
        differences = [field for field in PREDICTION_FIELDS
                       if (sprint_weekend or field not in SPRINT_FIELDS)
                       and fast_answers.get(field) != open_answers.get(field)]
        print("\nРазличаются или недоступны в одном из API: " +
              (", ".join(LABELS[field] for field in differences) if differences else "нет"))
        print("\nТест только читает API: БД, баллы и рассылки не меняются.\n", flush=True)
