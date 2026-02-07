import asyncio
import functools
import logging
import pathlib
import time
import pickle
import hashlib
from datetime import date as _date, timezone, timedelta, datetime
from typing import Optional, Any, Dict, Tuple, List

import fastf1
import pandas as pd
from fastf1._api import SessionNotAvailableError
from fastf1.ergast import Ergast
from redis.asyncio import Redis  # Требуется установленный redis

# --- ЛОГИРОВАНИЕ --- #
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА КЭША FASTF1 (Файловый) --- #
# Это кэш самой библиотеки (сырые данные от API)
_project_root = pathlib.Path(__file__).resolve().parent.parent
_cache_dir = _project_root / "fastf1_cache"
_cache_dir.mkdir(exist_ok=True)
try:
    fastf1.Cache.enable_cache(_cache_dir)
    logger.info(f"FastF1 cache enabled at: {_cache_dir}")
except Exception as e:
    logger.warning(f"Could not enable FastF1 cache: {e}")

UTC_PLUS_3 = timezone(timedelta(hours=3))

# --- REDIS CLIENT (Глобальный) --- #
_REDIS_CLIENT: Redis | None = None


async def init_redis_cache(redis_url: str):
    """Инициализация Redis клиента для кэширования данных."""
    global _REDIS_CLIENT
    try:
        _REDIS_CLIENT = Redis.from_url(redis_url)
        # Проверка соединения
        await _REDIS_CLIENT.ping()
        logger.info("Redis cache initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Redis cache: {e}")
        _REDIS_CLIENT = None


# --- ДЕКОРАТОРЫ --- #

def cache_result(ttl: int = 300, key_prefix: str = ""):
    """
    Кэширует результат выполнения функции в Redis.
    Если Redis недоступен — просто выполняет функцию.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 1. Если Redis не работает, просто выполняем
            if _REDIS_CLIENT is None:
                return await func(*args, **kwargs)

            # 2. Формируем уникальный ключ
            try:
                # Используем repr для аргументов, чтобы получить строковое представление
                arg_str = f"{args}_{kwargs}"
                arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
                cache_key = f"f1bot:cache:{key_prefix}:{func.__name__}:{arg_hash}"

                # 3. Пробуем достать из кэша
                cached_data = await _REDIS_CLIENT.get(cache_key)
                if cached_data:
                    return pickle.loads(cached_data)
            except Exception as e:
                logger.error(f"Redis READ error for {func.__name__}: {e}")

            # 4. Выполняем функцию
            result = await func(*args, **kwargs)

            # 5. Решаем, нужно ли кэшировать результат
            should_cache = True
            if result is None:
                should_cache = False
            elif isinstance(result, pd.DataFrame) and result.empty:
                # Пустые DataFrame кэшируем на очень короткое время (на случай сбоя API),
                # чтобы не долбить API каждую секунду
                ttl_override = 60
            elif isinstance(result, (list, tuple, dict)) and not result:
                should_cache = False

            # Если получили ошибку или пустоту, возможно стоит кэшировать ненадолго?
            # Пока просто не кэшируем пустые списки/dict.

            if should_cache:
                try:
                    packed = pickle.dumps(result)
                    # Используем setex для атомарной установки с TTL
                    await _REDIS_CLIENT.setex(cache_key, ttl, packed)
                except Exception as e:
                    logger.error(f"Redis WRITE error for {func.__name__}: {e}")

            return result

        return wrapper

    return decorator


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --- #

async def _run_sync(func, *args, **kwargs):
    """Запускает синхронные блокирующие функции в отдельном потоке."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# --- ОСНОВНАЯ ЛОГИКА (Синхронная часть) --- #

def get_season_schedule_short(season: int) -> list[dict]:
    """Синхронное получение расписания с защитой от ошибок."""
    try:
        schedule = fastf1.get_event_schedule(season)
        if schedule is None or schedule.empty:
            logger.warning(f"Schedule for season {season} is empty.")
            return []
    except Exception as e:
        logger.error(f"Failed to get schedule for {season}: {e}")
        return []

    races: list[dict] = []

    for _, row in schedule.iterrows():
        try:
            event_name = row.get("EventName")
            if not isinstance(event_name, str) or not event_name: continue

            # Проверка номера этапа (иногда бывает 0 для тестов)
            round_val = row.get("RoundNumber")
            try:
                round_num = int(round_val)
            except (ValueError, TypeError):
                continue

            if round_num <= 0: continue

            country = str(row.get("Country") or "")
            location = str(row.get("Location") or "")

            # Поиск времени гонки
            race_dt_utc = None
            for i in range(1, 6):
                name_col = f"Session{i}"
                date_col = f"Session{i}DateUtc"
                if name_col in row and date_col in row:
                    if str(row[name_col]) == "Race" and pd.notna(row[date_col]):
                        race_dt_utc = row[date_col].to_pydatetime()
                        break

            if race_dt_utc:
                if race_dt_utc.tzinfo is None:
                    race_dt_utc = race_dt_utc.replace(tzinfo=timezone.utc)
                # Сохраняем полную дату-время для точных уведомлений
                race_start_utc = race_dt_utc.isoformat()
                date_iso = race_dt_utc.date().isoformat()
            else:
                # Если даты гонки нет, берем общую дату ивента
                try:
                    event_dt = row.get("EventDate")
                    if pd.notna(event_dt):
                        date_iso = event_dt.to_pydatetime().date().isoformat()
                    else:
                        date_iso = _date.today().isoformat()
                except:
                    date_iso = _date.today().isoformat()
                race_start_utc = None

            races.append({
                "round": round_num,
                "event_name": event_name,
                "country": country,
                "location": location,
                "date": date_iso,
                "race_start_utc": race_start_utc
            })
        except Exception as e:
            logger.error(f"Error parsing schedule row: {e}")
            continue

    return races


def get_driver_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    ergast = Ergast()
    try:
        if round_number is None:
            res = ergast.get_driver_standings(season=season)
        else:
            res = ergast.get_driver_standings(season=season, round=round_number)

        if res.content and len(res.content) > 0:
            return res.content[0]
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Ergast API failed for driver {season}: {e}",
                     exc_info=True)  # exc_info=True покажет где именно упало
        return pd.DataFrame()


def get_constructor_standings_df(season: int, round_number: Optional[int] = None) -> pd.DataFrame:
    ergast = Ergast()
    try:
        if round_number is None:
            res = ergast.get_constructor_standings(season=season)
        else:
            res = ergast.get_constructor_standings(season=season, round=round_number)

        if res.content and len(res.content) > 0:
            return res.content[0]
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Ergast API failed for constructor {season}: {e}",
                     exc_info=True)  # exc_info=True покажет где именно упало
        return pd.DataFrame()


def get_race_results_df(season: int, round_number: int):
    try:
        session = fastf1.get_session(season, round_number, "R")
        # Грузим только результаты, без телеметрии и погоды
        session.load(telemetry=False, laps=False, weather=False, messages=False)
        return session.results
    except Exception as e:
        logger.error(f"FastF1 Race load error {season}/{round_number}: {e}")
        return pd.DataFrame()


def get_qualifying_results(season: int, round_number: int, limit: int = 20) -> list[dict]:
    try:
        session = fastf1.get_session(season, round_number, "Q")
        session.load(telemetry=False, laps=False, weather=False, messages=False)

        if session.results is None or session.results.empty:
            return []

        results = []
        for row in session.results.itertuples(index=False):
            pos = getattr(row, "Position", None)
            if pd.isna(pos): continue

            try:
                pos_int = int(pos)
            except:
                continue

            code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
            name = getattr(row, "LastName", "") or code

            # Время (Q1, Q2, Q3)
            q3 = getattr(row, "Q3", None)
            q2 = getattr(row, "Q2", None)
            q1 = getattr(row, "Q1", None)

            # Логика выбора лучшего времени
            best_time = None
            for t in [q3, q2, q1]:
                if pd.notna(t):
                    best_time = t
                    break

            best_str = _format_quali_time(best_time) if best_time is not None else "-"

            results.append({
                "position": pos_int,
                "driver": code,
                "name": name,
                "best": best_str
            })

        results.sort(key=lambda r: r["position"])
        return results[:limit]

    except Exception as e:
        logger.error(f"Quali load error {season}/{round_number}: {e}")
        return []


def get_latest_quali_results(season: int, max_round: int | None = None, limit: int = 20):
    """
    Ищет последнюю прошедшую квалификацию.
    Возвращает Tuple (round_number, results_list).
    НИКОГДА не возвращает None! В случае ошибки вернет (None, []).
    """
    schedule = get_season_schedule_short(season)
    if not schedule:
        return None, []

    # Фильтруем только прошедшие этапы
    today = datetime.now(timezone.utc).date()
    passed_rounds = []

    for r in schedule:
        # Проверяем дату
        try:
            r_date = _date.fromisoformat(r["date"])
            if r_date <= today:
                passed_rounds.append(r["round"])
        except:
            continue

    # Если max_round задан, фильтруем по нему
    if max_round:
        passed_rounds = [rn for rn in passed_rounds if rn <= max_round]

    passed_rounds.sort(reverse=True)  # От новых к старым

    for rn in passed_rounds:
        try:
            # Пытаемся загрузить результаты
            res = get_qualifying_results(season, rn, limit)
            if res:
                return rn, res
        except Exception:
            continue

    return None, []


def _format_quali_time(value: Any) -> str | None:
    if value is None: return None
    try:
        td = pd.to_timedelta(value)
    except:
        return None

    if pd.isna(td): return None

    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    millis = int((total_seconds * 1000) % 1000)

    return f"{minutes}:{seconds:02d}.{millis:03d}"


def get_event_details(season: int, round_number: int) -> dict | None:
    try:
        schedule = fastf1.get_event_schedule(season)
        row = schedule.loc[schedule["RoundNumber"] == round_number]

        if row.empty: return None
        event = row.iloc[0]

        # Безопасное получение данных
        def safe_str(val):
            return str(val) if pd.notna(val) else ""

        details = {
            "round": int(event["RoundNumber"]),
            "event_name": safe_str(event["EventName"]),
            "official_name": safe_str(event["OfficialEventName"]),
            "country": safe_str(event["Country"]),
            "location": safe_str(event["Location"]),
            "event_format": safe_str(event["EventFormat"]),
            "sessions": get_weekend_schedule(season, round_number)
        }
        return details
    except Exception as e:
        logger.error(f"Event details error: {e}")
        return None


def get_weekend_schedule(season: int, round_number: int) -> list[dict]:
    try:
        schedule = fastf1.get_event_schedule(season)
        row = schedule.loc[schedule["RoundNumber"] == round_number]
        if row.empty: return []
        row = row.iloc[0]
        sessions: list[dict] = []

        for i in range(1, 9):  # Session 1-8 (обычно до 5)
            name_col = f"Session{i}"
            date_col = f"Session{i}DateUtc"

            if name_col not in row.index or date_col not in row.index: continue

            sess_name = row[name_col]
            sess_dt = row[date_col]

            if pd.isna(sess_name) or pd.isna(sess_dt): continue

            dt_utc = sess_dt.to_pydatetime()
            if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)

            sessions.append({
                "name": str(sess_name),
                "utc_iso": dt_utc.isoformat(),
            })
        return sessions
    except Exception as e:
        logger.error(f"Weekend schedule error: {e}")
        return []


# --- АСИНХРОННЫЕ ОБЕРТКИ (С КЭШИРОВАНИЕМ) --- #

@cache_result(ttl=3600, key_prefix="schedule")  # Кэш 1 час
async def get_season_schedule_short_async(season: int):
    return await _run_sync(get_season_schedule_short, season)


@cache_result(ttl=600, key_prefix="dr_standings")  # Кэш 10 мин
async def get_driver_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_driver_standings_df, season, round_number)


@cache_result(ttl=600, key_prefix="con_standings")
async def get_constructor_standings_async(season: int, round_number: Optional[int] = None):
    return await _run_sync(get_constructor_standings_df, season, round_number)


@cache_result(ttl=300, key_prefix="race_res")  # Кэш 5 мин
async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


@cache_result(ttl=300, key_prefix="quali_res")
async def _get_quali_async(season: int, round_number: int, limit: int = 20):
    return await _run_sync(get_qualifying_results, season, round_number, limit)


@cache_result(ttl=300, key_prefix="lat_quali")
async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20):
    # Эта функция уже возвращает Tuple, поэтому _run_sync вернет Tuple
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


async def get_event_details_async(season: int, round_number: int):
    # Детали ивента меняются редко, можно кэшировать надолго
    # Но так как там есть время сессий, которое иногда уточняют, оставим без кэша или с малым TTL
    return await _run_sync(get_event_details, season, round_number)


# --- ПРОГРЕВ КЭША --- #

async def warmup_cache(season: int | None = None):
    """
    Умный прогрев:
    1. Расписание.
    2. Таблицы чемпионата.
    3. Результаты ПОСЛЕДНЕЙ прошедшей гонки (чтобы они были готовы к показу).
    """
    if season is None:
        season = datetime.now().year

    logger.info(f"🔥 Starting cache warmup for season {season}...")

    # 1. Расписание
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        logger.warning("Warmup failed: Empty schedule.")
        return

    # 2. Таблицы
    await get_driver_standings_async(season)
    await get_constructor_standings_async(season)

    # 3. Находим последний этап
    now = datetime.now().date()
    last_round = None
    for r in schedule:
        try:
            d = _date.fromisoformat(r["date"])
            if d <= now:
                last_round = r["round"]
        except:
            pass

    if last_round:
        logger.info(f"🔥 Warming up results for round {last_round}...")
        # Запускаем параллельно прогрев гонки и квалы
        await asyncio.gather(
            get_race_results_async(season, last_round),
            _get_latest_quali_async(season, limit=20)
        )

    logger.info("✅ Cache warmup finished.")