import asyncio
import functools
import logging
import pathlib
from datetime import date as _date, timezone, timedelta, datetime
from typing import Optional, Any

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


async def _run_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


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
    schedule = fastf1.get_event_schedule(season)
    races: list[dict] = []

    for _, row in schedule.iterrows():
        event_name = row.get("EventName")
        if not isinstance(event_name, str) or not event_name: continue
        try:
            round_num = int(row["RoundNumber"])
        except:
            continue
        if round_num <= 0: continue

        country = str(row.get("Country") or "")
        location = str(row.get("Location") or "")

        race_dt_utc = None
        for i in range(1, 9):
            name_col = f"Session{i}"
            date_col = f"Session{i}DateUtc"
            if name_col not in row.index or date_col not in row.index: continue
            if str(row[name_col]) == "Race" and row[date_col] is not None:
                race_dt_utc = row[date_col].to_pydatetime()
                break

        if race_dt_utc:
            if race_dt_utc.tzinfo is None: race_dt_utc = race_dt_utc.replace(tzinfo=timezone.utc)
            date_iso = race_dt_utc.date().isoformat()
        else:
            try:
                date_iso = row["EventDate"].to_pydatetime().date().isoformat()
            except:
                date_iso = _date.today().isoformat()

        race_dict = {
            "round": round_num,
            "event_name": event_name,
            "country": country,
            "location": location,
            "date": date_iso,
        }

        if race_dt_utc:
            # Для бота (расчеты)
            race_dict["race_start_utc"] = race_dt_utc.isoformat()
            # Для сайта (готовая строка)
            dt_msk = race_dt_utc.astimezone(UTC_PLUS_3)
            race_dict["local"] = dt_msk.strftime("%d.%m.%Y %H:%M")  # "08.03.2026 07:00"

        races.append(race_dict)

    races.sort(key=lambda r: r["round"])
    return races


async def get_season_schedule_short_async(season: int):
    return await _run_sync(get_season_schedule_short, season)


def get_driver_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    ergast = Ergast()
    try:
        if round_number is None: res = ergast.get_driver_standings(season=season)
        else: res = ergast.get_driver_standings(season=season, round=round_number)
        if not res.content: return pd.DataFrame()
        return res.content[0]
    except: return pd.DataFrame()


async def get_driver_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_driver_standings_df, season, round_number)


def get_constructor_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    ergast = Ergast()
    try:
        if round_number is None: res = ergast.get_constructor_standings(season=season)
        else: res = ergast.get_constructor_standings(season=season, round=round_number)
        if not res.content: return pd.DataFrame()
        return res.content[0]
    except: return pd.DataFrame()


async def get_constructor_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_constructor_standings_df, season, round_number)


def get_race_results_df(season: int, round_number: int):
    session = fastf1.get_session(season, round_number, "R")
    session.load(telemetry=False, laps=False, weather=False, messages=False)
    return session.results


async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


def get_weekend_schedule(season: int, round_number: int) -> list[dict]:
    """Возвращает расписание сессий уикенда."""
    schedule = fastf1.get_event_schedule(season)
    row = schedule.loc[schedule["RoundNumber"] == round_number]
    if row.empty: return []
    row = row.iloc[0]
    sessions: list[dict] = []

    for i in range(1, 9):
        name_col = f"Session{i}"
        date_col = f"Session{i}DateUtc"
        if name_col not in row.index or date_col not in row.index: continue

        sess_name = row[name_col]
        sess_dt = row[date_col]

        if not isinstance(sess_name, str) or not sess_name: continue
        if sess_dt is None: continue

        dt_utc = sess_dt.to_pydatetime()
        if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        dt_msk = dt_utc.astimezone(UTC_PLUS_3)

        sessions.append({
            "name": sess_name,
            "utc_iso": dt_utc.isoformat(),
            "utc": dt_utc.strftime("%H:%M UTC"),
            # 👇 ГАРАНТИРУЕМ ФОРМАТ СТРОКИ ДЛЯ САЙТА
            "local": dt_msk.strftime("%d.%m.%Y %H:%M"),
        })
    return sessions


def get_qualifying_results(season: int, round_number: int, limit: int = 20) -> list[dict]:
    session = fastf1.get_session(season, round_number, "Q")
    session.load()
    if session.results is None or session.results.empty: return []
    results = []
    for row in session.results.itertuples(index=False):
        pos = getattr(row, "Position", None)
        if pos is None: continue
        try: pos_int = int(pos)
        except: continue
        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
        name = getattr(row, "LastName", "") or code
        q3, q2, q1 = getattr(row, "Q3", None), getattr(row, "Q2", None), getattr(row, "Q1", None)
        best = _format_quali_time(q3 or q2 or q1)
        results.append({"position": pos_int, "driver": code, "name": name, "best": best})
    results.sort(key=lambda r: r["position"])
    return results[:limit]


async def _get_quali_async(season: int, round_number: int, limit: int = 20) -> list[dict]:
    """
    Асинхронная обёртка над get_qualifying_results, чтобы не блокировать event-loop.
    """
    loop = asyncio.get_running_loop()
    func = functools.partial(get_qualifying_results, season, round_number, limit)
    return await loop.run_in_executor(None, func)


def get_latest_quali_results(season: int, max_round: int | None = None, limit: int = 20):
    schedule = get_season_schedule_short(season)
    if not schedule: return None, []
    rounds = sorted([r["round"] for r in schedule])
    if max_round: rounds = [r for r in rounds if r <= max_round]
    today = _date.today()
    passed = []
    for rn in rounds:
        item = next(r for r in schedule if r["round"] == rn)
        try: d = _date.fromisoformat(item["date"])
        except: d = today
        if d <= today: passed.append(rn)
    for rn in sorted(passed, reverse=True):
        try: res = get_qualifying_results(season, rn, limit)
        except: continue
        if res: return rn, res
    return None, []


async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20):
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


def _format_quali_time(value: Any) -> str | None:
    if value is None: return None
    try: td = pd.to_timedelta(value)
    except: return None
    if pd.isna(td): return None
    ms = int(td.total_seconds() * 1000 + 0.5)
    return f"{ms // 60000}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}"


def _warmup_session_sync(season: int, round_number: int, session_code: str) -> None:
    try:
        s = fastf1.get_session(season, round_number, session_code)
        # минимальная загрузка, только чтобы закешировать результаты
        s.load(
            telemetry=False,
            laps=False,
            weather=False,
            messages=False,
        )
        logger.info(
            "[WARMUP] Прогрел сессию %s: сезон=%s, раунд=%s",
            session_code, season, round_number
        )
    except SessionNotAvailableError:
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
    двух последних прошедших гонок (Q и R).
    Вызывать:
      - один раз при старте бота
      - периодически через APScheduler (каждые N минут)
    """
    # здесь можно уже просто вызывать напрямую,
    # без локального импорта, функция выше в этом же модуле
    season = datetime.now().year
    schedule = get_season_schedule_short(season)
    if not schedule:
        logger.info("[WARMUP] Нет расписания для сезона %s", season)
        return

    now_utc = datetime.now(timezone.utc)

    past: list[dict] = []

    for r in schedule:
        race_start_str = r.get("race_start_utc")
        race_dt = None

        if race_start_str:
            try:
                race_dt = datetime.fromisoformat(race_start_str)
                if race_dt.tzinfo is None:
                    race_dt = race_dt.replace(tzinfo=timezone.utc)
            except Exception:
                race_dt = None

        # если времени старта нет, можно подстраховаться датой
        if race_dt is None:
            try:
                race_date = _date.fromisoformat(r["date"])
                # считаем прошедшей, если дата гонки < сегодняшней по UTC
                if race_date < _date.today():
                    past.append(r)
                continue
            except Exception:
                continue

        if race_dt <= now_utc:
            past.append(r)

    if not past:
        logger.info("[WARMUP] Пока нет прошедших гонок для сезона %s", season)
        return

    # сортируем по номеру этапа и берём последние два
    past_sorted = sorted(past, key=lambda x: x["round"])
    last_two = past_sorted[-2:]  # если была всего одна — возьмётся одна

    targets: list[tuple[int, int]] = [
        (season, r["round"]) for r in last_two
    ]

    loop = asyncio.get_running_loop()

    if not targets:
        logger.info("[WARMUP] Нечего прогревать (season=%s)", season)
        return

    logger.info(
        "[WARMUP] Начинаю прогрев FastF1 (последовательно) для season=%s, rounds=%s",
        season,
        [r["round"] for r in last_two],
    )

    for yr, rnd in targets:
        for code in ("Q", "R"):
            await loop.run_in_executor(None, _warmup_session_sync, yr, rnd, code)

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
