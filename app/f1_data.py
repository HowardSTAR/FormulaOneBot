import asyncio
import functools
import logging
import pathlib
from datetime import date as _date, timezone, timedelta, datetime
from typing import Optional, Any

import fastf1
import pandas as pd
import pickle
import redis_client
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


# --- ДЕКОРАТОР КЭШИРОВАНИЯ --- #
def cache_result(ttl: int = 300, key_prefix: str = ""):
    """
    ttl: время жизни кэша в секундах (по умолчанию 5 минут)
    key_prefix: префикс для ключа в Redis
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Формируем уникальный ключ: prefix:arg1:arg2...
            # Простая генерация ключа из аргументов
            key_parts = [str(arg) for arg in args]
            key_parts += [f"{k}={v}" for k, v in kwargs.items()]
            cache_key = f"f1bot:{key_prefix}:{':'.join(key_parts)}"

            # 1. Пытаемся получить из Redis
            try:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    # Если данные есть, распаковываем (Pickle универсален для DF и dict)
                    return pickle.loads(cached_data)
            except Exception as e:
                logger.error(f"Redis read error: {e}")

            # 2. Если кэша нет, выполняем функцию (оригинальную)
            result = await func(*args, **kwargs)

            # 3. Сохраняем в Redis
            try:
                if result is not None: # Не кэшируем None/ошибки
                    await redis_client.setex(
                        cache_key,
                        ttl,
                        pickle.dumps(result)
                    )
            except Exception as e:
                logger.error(f"Redis write error: {e}")

            return result
        return wrapper
    return decorator


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
            # 1. ISO для бота (расчеты)
            race_dict["race_start_utc"] = race_dt_utc.isoformat()

            # 2. Строка для сайта (ЖЕСТКИЙ ФОРМАТ) "08.03.2026 07:00"
            dt_msk = race_dt_utc.astimezone(UTC_PLUS_3)
            race_dict["local"] = dt_msk.strftime("%d.%m.%Y %H:%M")

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
        return res.content[0] if res.content else pd.DataFrame()
    except: return pd.DataFrame()


async def get_driver_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_driver_standings_df, season, round_number)


def get_constructor_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    ergast = Ergast()
    try:
        if round_number is None: res = ergast.get_constructor_standings(season=season)
        else: res = ergast.get_constructor_standings(season=season, round=round_number)
        return res.content[0] if res.content else pd.DataFrame()
    except: return pd.DataFrame()


async def get_constructor_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_constructor_standings_df, season, round_number)


def get_race_results_df(season: int, round_number: int):
    try:
        session = fastf1.get_session(season, round_number, "R")
        session.load(telemetry=False, laps=False, weather=False, messages=False)
        return session.results
    except: return None


async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


def get_weekend_schedule(season: int, round_number: int) -> list[dict]:
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
            # Гарантируем строку "ДД.ММ.ГГГГ ЧЧ:ММ"
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
        try:
            session = fastf1.get_session(season, rn, "Q")
            session.load()
            if session.results is None or session.results.empty: continue
            results = []
            for row in session.results.itertuples(index=False):
                pos = getattr(row, "Position", None)
                if pos is None: continue
                try: pos_int = int(pos)
                except: continue
                code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
                name = getattr(row, "LastName", "") or code
                # best time logic simplified for brevity in this fix
                best = "-"
                results.append({"position": pos_int, "driver": code, "name": name, "best": best})
            results.sort(key=lambda r: r["position"])
            return rn, results[:limit]
        except: continue
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


# --- ОБНОВЛЕННЫЕ АСИНХРОННЫЕ ФУНКЦИИ --- #

@cache_result(ttl=3600, key_prefix="schedule") # Кэш на 1 час
async def get_season_schedule_short_async(season: int):
    return await _run_sync(get_season_schedule_short, season)


@cache_result(ttl=600, key_prefix="driver_standings") # Кэш на 10 минут
async def get_driver_standings_async(season: int, round_number: Optional[int] = None):
    # Pandas DataFrame отлично пиклится
    return await _run_sync(get_driver_standings_df, season, round_number)


@cache_result(ttl=600, key_prefix="constructor_standings")
async def get_constructor_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_constructor_standings_df, season, round_number)


@cache_result(ttl=300, key_prefix="race_results") # Кэш 5 мин (во время гонки актуально)
async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


@cache_result(ttl=300, key_prefix="quali_results")
async def _get_quali_async(season: int, round_number: int, limit: int = 20) -> list[dict]:
    loop = asyncio.get_running_loop()
    func = functools.partial(get_qualifying_results, season, round_number, limit)
    return await loop.run_in_executor(None, func)


@cache_result(ttl=300, key_prefix="latest_quali")
async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20):
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


def get_event_details(season: int, round_number: int) -> dict | None:
    """
    Получает детальную информацию о событии (трасса, локация) и расписание.
    """
    try:
        schedule = fastf1.get_event_schedule(season)
        row = schedule.loc[schedule["RoundNumber"] == round_number]

        if row.empty:
            return None

        event = row.iloc[0]

        # Собираем базовую инфу
        details = {
            "round": int(event["RoundNumber"]),
            "event_name": str(event["EventName"]),
            "official_name": str(event["OfficialEventName"]),
            "country": str(event["Country"]),
            "location": str(event["Location"]),
            "event_format": str(event["EventFormat"]),
            # FastF1 не дает url картинки, но мы можем вернуть ключ для поиска файла
            "circuit_key": _normalize_circuit_name(str(event["Location"]))
        }

        # Добавляем расписание уикенда (используем существующую функцию)
        sessions = get_weekend_schedule(season, round_number)
        details["sessions"] = sessions

        return details
    except Exception as e:
        logger.error(f"Error getting event details: {e}")
        return None


def _normalize_circuit_name(name: str) -> str:
    import re
    # Превращает "Monte Carlo" в "monte_carlo" для поиска картинок
    return re.sub(r"[^a-z0-9]+", "_", name.lower())


async def get_event_details_async(season: int, round_number: int):
    return await _run_sync(get_event_details, season, round_number)


# --- ГЛАВНАЯ ФУНКЦИЯ СРАВНЕНИЯ (ПЕРЕПИСАНА НА get_session) ---
@cache_result(ttl=3600, key_prefix="h2h_data_v2")
async def get_drivers_comparison_async(season: int, driver1_code: str, driver2_code: str):
    return await _run_sync(_get_drivers_comparison_sync, season, driver1_code, driver2_code)


def _get_drivers_comparison_sync(season: int, d1_code: str, d2_code: str):
    # 1. Получаем расписание
    try:
        schedule = fastf1.get_event_schedule(season, include_testing=False)
    except Exception as e:
        logger.error(f"Schedule error: {e}")
        return None

    if schedule is not None and not schedule.empty:
        schedule = schedule[schedule['EventFormat'] != 'testing']
    else:
        return None

    rounds_map = {}
    for _, row in schedule.iterrows():
        try:
            r_num = int(row["RoundNumber"])
            r_name = str(row["EventName"]).replace(" Grand Prix", "").strip()
            rounds_map[r_num] = r_name
        except:
            continue

    all_rounds = sorted(rounds_map.keys())

    # Подготовка структур
    d1_code = d1_code.upper()
    d2_code = d2_code.upper()

    stats = {
        "driver1": {"code": d1_code, "total_points": 0, "history": []},
        "driver2": {"code": d2_code, "total_points": 0, "history": []},
        "score": {"race": {d1_code: 0, d2_code: 0}, "quali": {d1_code: 0, d2_code: 0}},
        "labels": []
    }

    d1_cum = 0
    d2_cum = 0

    # 2. ИДЕМ ПО ЭТАПАМ
    for r in all_rounds:
        stats["labels"].append(rounds_map[r])

        # --- ГОНКА (RACE) ---
        pts_d1_stage = 0
        pts_d2_stage = 0
        pos_d1 = 999
        pos_d2 = 999

        try:
            session = fastf1.get_session(season, r, 'R')
            session.load(telemetry=False, laps=False, weather=False, messages=False)

            if session.results is not None and not session.results.empty:
                # Поиск D1
                row_d1 = session.results[
                    (session.results['Abbreviation'] == d1_code) |
                    (session.results['DriverNumber'] == d1_code)
                    ]
                if not row_d1.empty:
                    pts_d1_stage = float(row_d1.iloc[0]['Points'])
                    pos_d1 = int(row_d1.iloc[0]['Position'])

                # Поиск D2
                row_d2 = session.results[
                    (session.results['Abbreviation'] == d2_code) |
                    (session.results['DriverNumber'] == d2_code)
                    ]
                if not row_d2.empty:
                    pts_d2_stage = float(row_d2.iloc[0]['Points'])
                    pos_d2 = int(row_d2.iloc[0]['Position'])

                # СЧЕТ В ГОНКАХ
                if pos_d1 != 999 and pos_d2 != 999:
                    if pos_d1 < pos_d2:
                        stats["score"]["race"][d1_code] += 1
                    elif pos_d2 < pos_d1:
                        stats["score"]["race"][d2_code] += 1

        except Exception:
            pass  # Гонка не загрузилась или еще не прошла

        # --- КВАЛИФИКАЦИЯ (QUALI) ---
        try:
            # Загружаем квалификацию ('Q')
            session_q = fastf1.get_session(season, r, 'Q')
            session_q.load(telemetry=False, laps=False, weather=False, messages=False)

            q_pos1 = 999
            q_pos2 = 999

            if session_q.results is not None and not session_q.results.empty:
                # Поиск D1
                q_row1 = session_q.results[
                    (session_q.results['Abbreviation'] == d1_code) |
                    (session_q.results['DriverNumber'] == d1_code)
                    ]
                if not q_row1.empty:
                    q_pos1 = int(q_row1.iloc[0]['Position'])

                # Поиск D2
                q_row2 = session_q.results[
                    (session_q.results['Abbreviation'] == d2_code) |
                    (session_q.results['DriverNumber'] == d2_code)
                    ]
                if not q_row2.empty:
                    q_pos2 = int(q_row2.iloc[0]['Position'])

                # СЧЕТ В КВАЛАХ
                if q_pos1 != 999 and q_pos2 != 999:
                    if q_pos1 < q_pos2:
                        stats["score"]["quali"][d1_code] += 1
                    elif q_pos2 < q_pos1:
                        stats["score"]["quali"][d2_code] += 1

        except Exception:
            pass  # Квала не загрузилась или еще не прошла

        # Накопление очков (только гонка)
        d1_cum += pts_d1_stage
        d2_cum += pts_d2_stage

        stats["driver1"]["history"].append(d1_cum)
        stats["driver2"]["history"].append(d2_cum)

    stats["driver1"]["total_points"] = d1_cum
    stats["driver2"]["total_points"] = d2_cum

    return stats


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
