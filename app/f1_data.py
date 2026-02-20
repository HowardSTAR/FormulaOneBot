import asyncio
import functools
import logging
import pathlib
import time
import pickle
import hashlib
from datetime import date as _date, timezone, timedelta, datetime
from typing import Optional, Any, Dict, Tuple, List

import aiohttp
import fastf1
import pandas as pd
from fastf1._api import SessionNotAvailableError
from fastf1.ergast import Ergast
from redis.asyncio import Redis

# --- ЛОГИРОВАНИЕ --- #
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА КЭША FASTF1 (Файловый) --- #
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
        await _REDIS_CLIENT.ping()
        logger.info("Redis cache initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Redis cache: {e}")
        _REDIS_CLIENT = None


# --- ДЕКОРАТОРЫ --- #

def cache_result(ttl: int = 300, key_prefix: str = ""):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if _REDIS_CLIENT is None:
                return await func(*args, **kwargs)

            try:
                arg_str = f"{args}_{kwargs}"
                arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
                cache_key = f"f1bot:cache:{key_prefix}:{func.__name__}:{arg_hash}"

                cached_data = await _REDIS_CLIENT.get(cache_key)
                if cached_data:
                    return pickle.loads(cached_data)
            except Exception as e:
                logger.error(f"Redis READ error for {func.__name__}: {e}")

            result = await func(*args, **kwargs)

            should_cache = True
            if result is None:
                should_cache = False
            elif isinstance(result, pd.DataFrame) and result.empty:
                ttl_override = 60
            elif isinstance(result, (list, tuple, dict)) and not result:
                should_cache = False

            if should_cache:
                try:
                    packed = pickle.dumps(result)
                    await _REDIS_CLIENT.setex(cache_key, ttl, packed)
                except Exception as e:
                    logger.error(f"Redis WRITE error for {func.__name__}: {e}")

            return result

        return wrapper

    return decorator


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --- #

async def _run_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# --- ОСНОВНАЯ ЛОГИКА (Синхронная часть) --- #

def get_season_schedule_short(season: int) -> list[dict]:
    try:
        schedule = fastf1.get_event_schedule(season)
        if schedule is None or schedule.empty:
            return []
    except Exception as e:
        logger.error(f"Failed to get schedule for {season}: {e}")
        return []

    races: list[dict] = []

    for _, row in schedule.iterrows():
        try:
            event_name = row.get("EventName")
            if not isinstance(event_name, str) or not event_name: continue

            round_val = row.get("RoundNumber")
            try:
                round_num = int(round_val)
            except:
                continue

            if round_num <= 0: continue

            country = str(row.get("Country") or "")
            location = str(row.get("Location") or "")

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
                race_start_utc = race_dt_utc.isoformat()
                date_iso = race_dt_utc.date().isoformat()
            else:
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
        except Exception:
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
        logger.error(f"Ergast API error (drivers): {e}")
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
        logger.error(f"Ergast API error (constructors): {e}")
        return pd.DataFrame()


def get_race_results_df(season: int, round_number: int):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            session = fastf1.get_session(season, round_number, "R")
            session.load(telemetry=False, laps=False, weather=False, messages=False)

            if session.results is not None and not session.results.empty:
                return session.results

            if attempt < max_retries - 1:
                logger.warning(
                    f"⚠️ Empty race results for {season} round {round_number} (Attempt {attempt + 1}). Retrying...")
                time.sleep(1.5)
                continue

        # ДОБАВЬТЕ ЭТОТ БЛОК:
        except SessionNotAvailableError:
            # Это нормальная ошибка, если гонки еще не было. Не надо Retry, просто выходим.
            logger.warning(f"Results not available yet for {season} round {round_number}")
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"❌ FastF1 error: {e}")
            if attempt < max_retries - 1:
                time.sleep(1.5)
            else:
                return pd.DataFrame()

    return pd.DataFrame()


def get_qualifying_results(season: int, round_number: int, limit: int = 20) -> list[dict]:
    # Механизм Retry для квалификации тоже не помешает
    max_retries = 2
    for attempt in range(max_retries):
        try:
            session = fastf1.get_session(season, round_number, "Q")
            session.load(telemetry=False, laps=False, weather=False, messages=False)

            if session.results is None or session.results.empty:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
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
            if attempt < max_retries - 1:
                time.sleep(1)
    return []


def get_latest_quali_results(season: int, max_round: int | None = None, limit: int = 20):
    schedule = get_season_schedule_short(season)
    if not schedule:
        return None, []

    today = datetime.now(timezone.utc).date()
    passed_rounds = []

    for r in schedule:
        try:
            r_date = _date.fromisoformat(r["date"])
            if r_date <= today:
                passed_rounds.append(r["round"])
        except:
            continue

    if max_round:
        passed_rounds = [rn for rn in passed_rounds if rn <= max_round]

    passed_rounds.sort(reverse=True)

    for rn in passed_rounds:
        try:
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

        for i in range(1, 9):
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

@cache_result(ttl=3600, key_prefix="schedule")
async def get_season_schedule_short_async(season: int):
    return await _run_sync(get_season_schedule_short, season)


@cache_result(ttl=600, key_prefix="dr_standings")
async def get_driver_standings_async(season: int, round_number: int | None = None) -> pd.DataFrame:
    """Асинхронно получает личный зачет (Jolpica API). Фоллбэк на OpenF1 (0 очков), если сезон не стартовал."""
    url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_number}/driverStandings.json" if round_number else f"https://api.jolpi.ca/ergast/f1/{season}/driverStandings.json"

    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    standings_lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

                    if standings_lists:
                        driver_standings = standings_lists[0].get("DriverStandings", [])
                        parsed_data = []
                        for ds in driver_standings:
                            driver = ds.get("Driver", {})
                            parsed_data.append({
                                "position": int(ds.get("position", 0)),
                                "points": float(ds.get("points", 0.0)),
                                "driverCode": driver.get("code", ""),
                                "givenName": driver.get("givenName", ""),
                                "familyName": driver.get("familyName", ""),
                                "driverId": driver.get("driverId", "")
                            })
                        return pd.DataFrame(parsed_data)
        except Exception as e:
            logger.error(f"Jolpica API error (drivers): {e}")

    # ФОЛЛБЭК: Сезон еще не начался, очков нет. Формируем нулевую таблицу из OpenF1.
    return await _get_zero_point_driver_standings()


@cache_result(ttl=600, key_prefix="con_standings")
async def get_constructor_standings_async(season: int, round_number: int | None = None) -> pd.DataFrame:
    """Асинхронно получает кубок конструкторов (Jolpica API). Фоллбэк на OpenF1 (0 очков)."""
    url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_number}/constructorStandings.json" if round_number else f"https://api.jolpi.ca/ergast/f1/{season}/constructorStandings.json"

    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    standings_lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

                    if standings_lists:
                        constructor_standings = standings_lists[0].get("ConstructorStandings", [])
                        parsed_data = []
                        for cs in constructor_standings:
                            team = cs.get("Constructor", {})
                            parsed_data.append({
                                "position": int(cs.get("position", 0)),
                                "points": float(cs.get("points", 0.0)),
                                "constructorId": team.get("constructorId", ""),
                                "constructorName": team.get("name", "")
                            })
                        return pd.DataFrame(parsed_data)
        except Exception as e:
            logger.error(f"Jolpica API error (constructors): {e}")

    # ФОЛЛБЭК: Формируем нулевую таблицу из OpenF1
    return await _get_zero_point_constructor_standings()


# ==========================================
# СКРЫТЫЕ ФУНКЦИИ ГЕНЕРАЦИИ МЕЖСЕЗОНЬЯ
# ==========================================

async def _get_zero_point_driver_standings() -> pd.DataFrame:
    """Собирает сетку пилотов из OpenF1 и выдает всем 0 очков."""
    url = "https://api.openf1.org/v1/drivers?session_key=latest"
    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(url) as response:
                if response.status != 200:
                    return pd.DataFrame()

                drivers_data = await response.json()
                seen_numbers = set()
                parsed_data = []

                for d in drivers_data:
                    driver_num = d.get('driver_number')
                    if not driver_num or driver_num in seen_numbers:
                        continue
                    seen_numbers.add(driver_num)

                    full_name = d.get('full_name', 'Unknown')
                    parts = full_name.split(' ', 1)
                    given = parts[0] if len(parts) > 0 else ''
                    family = parts[1] if len(parts) > 1 else full_name

                    parsed_data.append({
                        "position": "-",  # Прочерк, чтобы рендерер не красил плашки в золото/серебро
                        "points": 0.0,
                        "driverCode": d.get('name_acronym', '???'),
                        "givenName": given,
                        "familyName": family,
                        "driverId": str(driver_num)
                    })

                # До старта сезона сортируем пилотов по алфавиту (по фамилии)
                parsed_data.sort(key=lambda x: x['familyName'])
                return pd.DataFrame(parsed_data)
        except Exception as e:
            logger.error(f"OpenF1 Fallback Error (drivers): {e}")
            return pd.DataFrame()


async def _get_zero_point_constructor_standings() -> pd.DataFrame:
    """Собирает сетку команд из OpenF1 и выдает всем 0 очков."""
    url = "https://api.openf1.org/v1/drivers?session_key=latest"
    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(url) as response:
                if response.status != 200:
                    return pd.DataFrame()

                drivers_data = await response.json()
                teams = set()

                for d in drivers_data:
                    team_name = d.get('team_name')
                    if team_name:
                        teams.add(team_name)

                parsed_data = []
                # Сортируем команды по алфавиту
                for team in sorted(teams):
                    parsed_data.append({
                        "position": "-",  # Прочерк вместо места
                        "points": 0.0,
                        "constructorId": team.lower().replace(" ", "_"),
                        "constructorName": team
                    })

                return pd.DataFrame(parsed_data)
        except Exception as e:
            logger.error(f"OpenF1 Fallback Error (constructors): {e}")
            return pd.DataFrame()


@cache_result(ttl=300, key_prefix="race_res")
async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


@cache_result(ttl=300, key_prefix="quali_res")
async def _get_quali_async(season: int, round_number: int, limit: int = 20):
    return await _run_sync(get_qualifying_results, season, round_number, limit)


@cache_result(ttl=300, key_prefix="lat_quali")
async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20):
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


async def get_event_details_async(season: int, round_number: int):
    return await _run_sync(get_event_details, season, round_number)


# --- ПРОГРЕВ КЭША --- #

async def warmup_cache(season: int | None = None):
    if season is None:
        season = datetime.now().year

    logger.info(f"🔥 Starting cache warmup for season {season}...")

    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        logger.warning("Warmup failed: Empty schedule.")
        return

    await get_driver_standings_async(season)
    await get_constructor_standings_async(season)

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
        await asyncio.gather(
            get_race_results_async(season, last_round),
            _get_latest_quali_async(season, limit=20)
        )

    logger.info("✅ Cache warmup finished.")


# --- СРАВНЕНИЕ ПИЛОТОВ --- #
@cache_result(ttl=3600, key_prefix="compare_drivers")
async def get_drivers_comparison_async(season: int, d1: str, d2: str):
    """
    Заглушка для сравнения пилотов.
    """
    return {
        "season": season,
        "driver1": d1,
        "driver2": d2,
        "message": "Раздел в разработке"
    }

# --- РЕЗУЛЬТАТЫ ТЕСТОВ --- #
@cache_result(ttl=3600, key_prefix="testing_res")
async def get_testing_results_async(season: int, round_number: int):
    """
    Заглушка для результатов предсезонных тестов.
    Возвращает пустой DataFrame и название сессии, чтобы бот не падал.
    """
    import pandas as pd
    return pd.DataFrame(), "Тестовый день"
