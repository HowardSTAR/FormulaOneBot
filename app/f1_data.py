import pathlib
from datetime import date as _date, timezone, timedelta
from typing import Optional

import fastf1
import pandas as pd
from fastf1.ergast import Ergast

# --- ИНИЦИАЛИЗАЦИЯ КЭША --- #

_project_root = pathlib.Path(__file__).resolve().parent.parent
_cache_dir = _project_root / "fastf1_cache"
_cache_dir.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(_cache_dir)

UTC_PLUS_3 = timezone(timedelta(hours=3))


def get_season_schedule_df(season: int) -> pd.DataFrame:
    """
    Вернуть расписание F1 сезона в виде pandas.DataFrame.

    Колонки по доке FastF1, среди них:
    - RoundNumber
    - Country
    - Location
    - OfficialEventName
    - EventDate
    - EventName
    - EventFormat
    - Session1..Session5 и соответствующие даты. :contentReference[oaicite:5]{index=5}
    """
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    return schedule


def get_season_schedule_short(season: int) -> list[dict]:
    """
    Возвращает список гонок сезона в удобном виде.

    Берём из fastf1.get_event_schedule(season):
      - RoundNumber
      - EventName
      - Country
      - Location
      - EventDate (дата гонки)
    Плюс, если удаётся найти Race-сессию (SessionX == 'Race'),
    добавляем:
      - race_start_utc   (ISO, UTC)
      - race_start_local (ISO, UTC+3)
    """
    schedule = fastf1.get_event_schedule(season)

    races: list[dict] = []

    for _, row in schedule.iterrows():
        event_name = row.get("EventName")
        if not isinstance(event_name, str) or not event_name:
            continue

        # Номер этапа
        try:
            round_num = int(row["RoundNumber"])
        except Exception:
            continue

        country = str(row.get("Country") or "")
        location = str(row.get("Location") or "")

        # Дата гонки (EventDate — Timestamp)
        event_date = row.get("EventDate")
        if event_date is not None and hasattr(event_date, "to_pydatetime"):
            dt = event_date.to_pydatetime()
            race_date_iso = dt.date().isoformat()
        else:
            race_date_iso = _date.today().isoformat()

        # Пытаемся найти время старта RACE-сессии
        race_dt_utc = None
        for i in range(1, 9):  # с запасом до Session8
            name_col = f"Session{i}"
            date_col = f"Session{i}DateUtc"

            if name_col not in row.index or date_col not in row.index:
                continue

            sess_name = row[name_col]
            sess_dt_utc = row[date_col]

            if not isinstance(sess_name, str):
                continue
            if "Race" not in sess_name:
                continue
            if sess_dt_utc is None or not hasattr(sess_dt_utc, "to_pydatetime"):
                continue

            race_dt_utc = sess_dt_utc.to_pydatetime()
            break

        # Базовые поля гонки
        race_dict = {
            "round": round_num,
            "event_name": event_name,
            "country": country,
            "location": location,
            "date": race_date_iso,
        }

        # Если время гонки удалось найти — добавляем время
        if race_dt_utc is not None:
            if race_dt_utc.tzinfo is None:
                # Явно считаем это временем в UTC
                race_dt_utc = race_dt_utc.replace(tzinfo=timezone.utc)

            race_dict["race_start_utc"] = race_dt_utc.isoformat()
            race_dict["race_start_local"] = race_dt_utc.astimezone(UTC_PLUS_3).isoformat()

        races.append(race_dict)

    races.sort(key=lambda r: r["round"])
    return races


def get_driver_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    """
    Вернуть личный зачёт пилотов как DataFrame.

    По доке FastF1 используется Ergast-интерфейс: :contentReference[oaicite:6]{index=6}
      ergast = Ergast()
      ergast.get_driver_standings(season=SEASON, round=ROUND)

    Здесь:
    - season: год чемпионата
    - round_number: номер этапа (если None — текущие standings по последнему этапу).
    """
    ergast = Ergast()

    if round_number is None:
        res = ergast.get_driver_standings(season=season)
    else:
        res = ergast.get_driver_standings(season=season, round=round_number)

    df = res.content[0]
    return df


def get_constructor_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    """
    Вернуть кубок конструкторов как DataFrame.

    Аналогично get_driver_standings_df, только для конструкторов.
    """
    ergast = Ergast()

    if round_number is None:
        res = ergast.get_constructor_standings(season=season)
    else:
        res = ergast.get_constructor_standings(season=season, round=round_number)

    df = res.content[0]
    return df


def get_race_results_df(season: int, round_number: int) -> pd.DataFrame:
    """
    Вернуть результаты гонки (Race) как DataFrame.

    Логика по доке:
      session = fastf1.get_session(year, round, 'R')
      session.load()
      results = session.results

    В results есть столбцы вроде Abbreviation, TeamName, ClassifiedPosition, Points и т.д. :contentReference[oaicite:7]{index=7}
    """
    session = fastf1.get_session(season, round_number, "R")
    session.load()
    return session.results


def get_race_results(season: int, round_number: int, limit: int = 20) -> list[dict]:
    session = fastf1.get_session(season, round_number, "R")
    session.load(telemetry=False, weather=False)

    df = session.results
    results: list[dict] = []

    for _, row in df.iterrows():
        pos = int(row["Position"])
        code = row["Abbreviation"]
        team = row["TeamName"]
        time_ = row.get("Time")
        status = row.get("Status")
        points = row.get("Points")

        time_str = str(time_) if pd.notna(time_) else ""
        status_str = str(status) if pd.notna(status) else ""
        pts = int(points) if pd.notna(points) else 0

        results.append(
            {
                "position": pos,
                "driver": code,
                "team": team,
                "time": time_str,
                "status": status_str,
                "points": pts,
            }
        )

    results.sort(key=lambda r: r["position"])
    return results[:limit]


def get_weekend_schedule(season: int, round_number: int) -> list[dict]:
    """
    Возвращает список сессий уикенда для заданного этапа:
    [
      {"name": "Practice 1", "utc": "...", "local": "..."},
      ...
    ]
    """
    schedule = fastf1.get_event_schedule(season)

    row = schedule.loc[schedule["RoundNumber"] == round_number]
    if row.empty:
        return []

    row = row.iloc[0]
    sessions: list[dict] = []

    for i in range(1, 9):
        name_col = f"Session{i}"
        date_col = f"Session{i}DateUtc"

        if name_col not in row.index or date_col not in row.index:
            continue

        sess_name = row[name_col]
        sess_dt = row[date_col]

        if not isinstance(sess_name, str) or not sess_name:
            continue
        if sess_dt is None or not hasattr(sess_dt, "to_pydatetime"):
            continue

        dt_utc = sess_dt.to_pydatetime()
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(UTC_PLUS_3)

        sessions.append(
            {
                "name": sess_name,
                "utc": dt_utc.strftime("%H:%M UTC"),
                "local": dt_local.strftime("%d.%m.%Y %H:%M МСК"),
            }
        )

    return sessions


def get_qualifying_results(season: int, round_number: int, limit: int = 20) -> list[dict]:
    """
    Возвращает результаты квалификации (топ N):
    [
      {"position": 1, "driver": "VER", "team": "Red Bull", "best": "1:23.456"},
      ...
    ]
    """
    session = fastf1.get_session(season, round_number, "Q")
    session.load(telemetry=False, weather=False)

    df = session.results
    results: list[dict] = []

    for _, row in df.iterrows():
        pos = int(row["Position"])
        code = row["Abbreviation"]
        team = row["TeamName"]

        q1 = row.get("Q1")
        q2 = row.get("Q2")
        q3 = row.get("Q3")

        best = q3 if pd.notna(q3) else q2 if pd.notna(q2) else q1
        best_str = str(best) if pd.notna(best) else ""

        results.append(
            {
                "position": pos,
                "driver": code,
                "team": team,
                "best": best_str,
            }
        )

    results.sort(key=lambda r: r["position"])
    return results[:limit]


# можно удалить
if __name__ == "__main__":
    # Небольшой self-test, чтобы можно было запустить модуль отдельно
    year = 2025

    print("=== Краткое расписание сезона ===")
    schedule_short = get_season_schedule_short(year)
    for race in schedule_short:
        print(
            f"{race['round']:02d}. {race['event_name']} "
            f"({race['country']}, {race['location']}) — {race['date']}"
        )

    print("\n=== Личный зачёт пилотов (первые строки) ===")
    drivers_df = get_driver_standings_df(year)
    print(drivers_df.head())
    print("\nКолонки driver standings:", list(drivers_df.columns))

    print("\n=== Кубок конструкторов (первые строки) ===")
    constructors_df = get_constructor_standings_df(year)
    print(constructors_df.head())
    print("\nКолонки constructor standings:", list(constructors_df.columns))

    print("\n=== Результаты первой гонки сезона ===")
    race_results_df = get_race_results_df(year, round_number=1)
    print(race_results_df.head())
    print("\nКолонки race results:", list(race_results_df.columns))
