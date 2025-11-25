import asyncio
import logging
import pathlib
from datetime import date as _date, timezone, timedelta, datetime
from typing import Optional

import fastf1
import pandas as pd
from fastf1._api import SessionNotAvailableError
from fastf1.ergast import Ergast

# --- ИНИЦИАЛИЗАЦИЯ КЭША --- #

_project_root = pathlib.Path(__file__).resolve().parent.parent
_cache_dir = _project_root / "fastf1_cache"
_cache_dir.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(_cache_dir)

logger = logging.getLogger(__name__)

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

        # пропускаем тесты и всё с round <= 0
        if round_num <= 0:
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

        race_dict = {
            "round": round_num,
            "event_name": event_name,
            "country": country,
            "location": location,
            "date": race_date_iso,
        }

        if race_dt_utc is not None:
            if race_dt_utc.tzinfo is None:
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


def get_race_results_df(season: int, round_number: int):
    session = fastf1.get_session(season, round_number, "R")
    # грузим минимум (без телеметрии / погоды / статусов)
    session.load(
        telemetry=False,
        laps=False,
        weather=False,
        messages=False
    )
    return session.results


async def _get_race_results_async(season: int, round_number: int):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: get_race_results_df(season, round_number)
    )


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


async def _get_quali_async(season: int, round_number: int, limit: int = 100):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: get_qualifying_results(season, round_number, limit)
    )


def _warmup_session_sync(season: int, round_number: int, session_code: str) -> None:
    """
    Синхронный прогрев одной сессии FastF1 (Q/R).
    Вызывается из отдельного потока, чтобы не блокировать event loop.
    """
    try:
        s = fastf1.get_session(season, round_number, session_code)
        # livedata=False — берём только архивные данные / кэш
        s.load(livedata=False)
        logger.info(
            "[WARMUP] Прогрел сессию %s: сезон=%s, раунд=%s",
            session_code, season, round_number
        )
    except SessionNotAvailableError:
        # нет данных (ещё рано или сессия не существует) — это нормально
        logger.info(
            "[WARMUP] Нет данных для сессии %s (season=%s, round=%s)",
            session_code, season, round_number
        )
    except Exception as exc:
        logger.warning(
            "[WARMUP] Ошибка при прогреве сессии %s (season=%s, round=%s): %s",
            session_code, season, round_number, exc
        )


async def warmup_current_season_sessions() -> None:
    """
    Асинхронная обёртка: в фоне прогреваем FastF1 для
    последней прошедшей гонки и ближайшей будущей гонки (Q и R).
    Вызывать:
      - один раз при старте бота
      - периодически через APScheduler (каждые 2 минуты)
    """
    from app.f1_data import get_season_schedule_short  # чтобы избежать циклического импорта

    season = datetime.now().year
    schedule = get_season_schedule_short(season)
    if not schedule:
        logger.info("[WARMUP] Нет расписания для сезона %s", season)
        return

    now_utc = datetime.now(timezone.utc)

    # разделим на прошедшие и будущие
    past = []
    future = []
    for r in schedule:
        race_start_str = r.get("race_start_utc")
        if race_start_str:
            try:
                race_dt = datetime.fromisoformat(race_start_str)
                if race_dt.tzinfo is None:
                    race_dt = race_dt.replace(tzinfo=timezone.utc)
            except Exception:
                race_dt = None
        else:
            race_dt = None

        if race_dt and race_dt <= now_utc:
            past.append(r)
        else:
            future.append(r)

    targets: list[tuple[int, int]] = []

    # последняя прошедшая
    if past:
        last_race = max(past, key=lambda r: r["round"])
        targets.append((season, last_race["round"]))

    # ближайшая будущая
    if future:
        next_race = min(future, key=lambda r: r["round"])
        # избегаем дубликата, если это тот же раунд
        if not targets or targets[0][1] != next_race["round"]:
            targets.append((season, next_race["round"]))

    if not targets:
        logger.info("[WARMUP] Нет подходящих этапов для прогрева (season=%s)", season)
        return

    loop = asyncio.get_running_loop()

    # параллельно греть Q и R для каждого выбранного этапа
    tasks = []
    for yr, rnd in targets:
        for code in ("Q", "R"):
            tasks.append(loop.run_in_executor(None, _warmup_session_sync, yr, rnd, code))

    if tasks:
        logger.info(
            "[WARMUP] Начинаю прогрев FastF1 для %d сессий (season=%s)",
            len(tasks), season
        )
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("[WARMUP] Прогрев FastF1 завершён")

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
