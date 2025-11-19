import pathlib
from typing import Optional

import fastf1
from fastf1.ergast import Ergast
import pandas as pd

from datetime import date as _date


# --- ИНИЦИАЛИЗАЦИЯ КЭША --- #

_project_root = pathlib.Path(__file__).resolve().parent.parent
_cache_dir = _project_root / "fastf1_cache"
_cache_dir.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(_cache_dir)


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

    Используем fastf1.get_event_schedule(season), где каждый ряд —
    одно Гран-при. Берём:
      - RoundNumber
      - EventName
      - Country
      - Location
      - EventDate (дата гонки)
    Никаких SessionName / SessionStart тут нет.
    """
    schedule = fastf1.get_event_schedule(season)

    races: list[dict] = []

    for _, row in schedule.iterrows():
        event_name = row.get("EventName")
        if not isinstance(event_name, str) or not event_name:
            # иногда в расписании бывают пустые строки — пропускаем
            continue

        # номер этапа
        try:
            round_num = int(row["RoundNumber"])
        except Exception:
            continue

        country = str(row.get("Country") or "")
        location = str(row.get("Location") or "")

        # дата гонки (EventDate — это Timestamp)
        event_date = row.get("EventDate")
        if event_date is not None:
            try:
                dt = event_date.to_pydatetime()
                race_date_iso = dt.date().isoformat()
            except Exception:
                race_date_iso = str(event_date)
        else:
            # на всякий случай fallback — сегодняшняя дата
            race_date_iso = _date.today().isoformat()

        races.append(
            {
                "round": round_num,
                "event_name": event_name,
                "country": country,
                "location": location,
                "date": race_date_iso,
                # ВАЖНО: больше НЕТ полей SessionName/SessionStart/race_start_utc
            }
        )

    # сортируем по номеру этапа на всякий случай
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
