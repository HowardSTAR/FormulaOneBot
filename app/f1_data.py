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

# --- FALLBACK КЭШ (когда Redis недоступен) --- #
_fallback_cache_dir = _project_root / "f1bot_cache"
_fallback_cache_dir.mkdir(exist_ok=True)
_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, data)


def _cache_key(key_prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    arg_str = f"{args}_{kwargs}"
    arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
    return f"{key_prefix}:{func_name}:{arg_hash}"


def _fallback_cache_get(cache_key: str) -> Any | None:
    """Читает из памяти, при промахе — из файла."""
    now = time.time()
    if cache_key in _MEMORY_CACHE:
        expires_at, data = _MEMORY_CACHE[cache_key]
        if expires_at > now:
            return data
        del _MEMORY_CACHE[cache_key]

    safe_key = hashlib.md5(cache_key.encode()).hexdigest()
    file_path = _fallback_cache_dir / f"{safe_key}.pkl"
    if file_path.exists():
        try:
            with open(file_path, "rb") as f:
                stored = pickle.load(f)
            expires_at, data = stored
            if expires_at > now:
                _MEMORY_CACHE[cache_key] = (expires_at, data)
                return data
        except Exception as e:
            logger.debug(f"Fallback cache read error: {e}")
    return None


def _fallback_cache_set(cache_key: str, data: Any, ttl: int) -> None:
    """Сохраняет в память и в файл."""
    expires_at = time.time() + ttl
    _MEMORY_CACHE[cache_key] = (expires_at, data)
    safe_key = hashlib.md5(cache_key.encode()).hexdigest()
    file_path = _fallback_cache_dir / f"{safe_key}.pkl"
    try:
        with open(file_path, "wb") as f:
            pickle.dump((expires_at, data), f)
    except Exception as e:
        logger.debug(f"Fallback cache write error: {e}")


def sort_standings_zero_last(df: pd.DataFrame, position_col: str = "position") -> pd.DataFrame:
    """
    Сортирует таблицу зачёта так, что позиции 1, 2, 3, ... идут по порядку,
    а пилоты/команды с 0 очков (позиция 0 или NaN) — в конец списка.
    """
    if df is None or df.empty or position_col not in df.columns:
        return df
    df = df.copy()
    pos = pd.to_numeric(df[position_col], errors="coerce")
    # 0 и NaN в конец: задаём ключ сортировки (0/NaN -> большое число)
    sort_key = pos.fillna(999).replace(0, 999)
    df["_sort_key"] = sort_key
    df = df.sort_values("_sort_key").drop(columns=["_sort_key"])
    return df


async def init_redis_cache(redis_url: str):
    """Инициализация Redis клиента для кэширования данных."""
    global _REDIS_CLIENT
    try:
        _REDIS_CLIENT = Redis.from_url(redis_url)
        await _REDIS_CLIENT.ping()
        logger.info("Redis cache initialized successfully.")
    except Exception as e:
        logger.warning(f"Redis unavailable, using file cache: {e}")
        _REDIS_CLIENT = None


# --- ДЕКОРАТОРЫ --- #

def cache_result(ttl: int = 300, key_prefix: str = ""):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = _cache_key(key_prefix, func.__name__, args, kwargs)

            if _REDIS_CLIENT is not None:
                try:
                    full_key = f"f1bot:cache:{cache_key}"
                    cached_data = await _REDIS_CLIENT.get(full_key)
                    if cached_data:
                        return pickle.loads(cached_data)
                except Exception as e:
                    logger.debug(f"Redis READ error: {e}")

            cached = _fallback_cache_get(cache_key)
            if cached is not None:
                return cached

            result = await func(*args, **kwargs)

            should_cache = True
            cache_ttl = ttl
            if result is None:
                should_cache = False
            elif isinstance(result, pd.DataFrame) and result.empty:
                cache_ttl = min(ttl, 60)
            elif isinstance(result, (list, tuple, dict)) and not result:
                should_cache = False

            if should_cache:
                if _REDIS_CLIENT is not None:
                    try:
                        packed = pickle.dumps(result)
                        await _REDIS_CLIENT.setex(f"f1bot:cache:{cache_key}", cache_ttl, packed)
                    except Exception as e:
                        logger.debug(f"Redis WRITE error: {e}")
                _fallback_cache_set(cache_key, result, cache_ttl)

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
            quali_dt_utc = None
            for i in range(1, 6):
                name_col = f"Session{i}"
                date_col = f"Session{i}DateUtc"
                if name_col in row and date_col in row:
                    sess_name = str(row[name_col]) if pd.notna(row[name_col]) else ""
                    if sess_name == "Race" and pd.notna(row[date_col]):
                        race_dt_utc = row[date_col].to_pydatetime()
                    if "Qualifying" in sess_name and pd.notna(row[date_col]):
                        quali_dt_utc = row[date_col].to_pydatetime()

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

            quali_start_utc = None
            if quali_dt_utc is not None:
                if quali_dt_utc.tzinfo is None:
                    quali_dt_utc = quali_dt_utc.replace(tzinfo=timezone.utc)
                quali_start_utc = quali_dt_utc.isoformat()

            races.append({
                "round": round_num,
                "event_name": event_name,
                "country": country,
                "location": location,
                "date": date_iso,
                "race_start_utc": race_start_utc,
                "quali_start_utc": quali_start_utc
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
            df = res.content[0]
            return sort_standings_zero_last(df)
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
            df = res.content[0]
            return sort_standings_zero_last(df)
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
# Бот и Mini App API вызывают одни и те же async-функции ниже:
# запросы и с бота, и с front идут через кэш (Redis или файловый), кэш общий.

@cache_result(ttl=7200, key_prefix="schedule_v2")
async def get_season_schedule_short_async(season: int):
    return await _run_sync(get_season_schedule_short, season)


@cache_result(ttl=3600, key_prefix="dr_standings_v3")
async def get_driver_standings_async(season: int, round_number: int | None = None) -> pd.DataFrame:
    """Асинхронно получает личный зачет (Jolpica API). Фоллбэк: Ergast для старых сезонов, OpenF1 для текущего."""
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
                            constructors = ds.get("Constructors", [])
                            constructor = constructors[0] if constructors else {}
                            # positionText "-" означает пилота без места; position может отсутствовать
                            pos_raw = ds.get("position") or ds.get("positionText", "0")
                            try:
                                pos = int(pos_raw) if str(pos_raw).isdigit() else 0
                            except (ValueError, TypeError):
                                pos = 0
                            parsed_data.append(
                                {
                                    "position": pos,
                                    "points": float(ds.get("points", 0.0)),
                                    "driverCode": driver.get("code", "") or (driver.get("familyName", "")[:3].upper() if driver.get("familyName") else ""),
                                    "givenName": driver.get("givenName", ""),
                                    "familyName": driver.get("familyName", ""),
                                    "driverId": driver.get("driverId", ""),
                                    "permanentNumber": str(driver.get("permanentNumber", "")) if driver.get("permanentNumber") else "",
                                    "constructorId": constructor.get("constructorId", ""),
                                    "constructorName": constructor.get("name", ""),
                                }
                            )

                        df = pd.DataFrame(parsed_data)
                        # Если Jolpica вернул слишком мало пилотов — берём из Ergast
                        if len(df) >= 5:
                            return sort_standings_zero_last(df)
                        logger.warning(f"Jolpica returned only {len(df)} drivers for {season}, falling back to Ergast")
        except Exception as e:
            logger.error(f"Jolpica API error (drivers): {e}")

    # Фоллбэк: Ergast для прошедших сезонов, OpenF1 для текущего
    if season < datetime.now().year:
        try:
            df = await _run_sync(get_driver_standings_df, season, round_number)
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Ergast fallback failed for {season}: {e}")

    return await _get_zero_point_driver_standings()


@cache_result(ttl=3600, key_prefix="con_standings_v3")
async def get_constructor_standings_async(season: int, round_number: int | None = None) -> pd.DataFrame:
    """Асинхронно получает кубок конструкторов (Jolpica API). Фоллбэк: Ergast для старых сезонов, OpenF1 для текущего."""
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
                        df = pd.DataFrame(parsed_data)
                        if len(df) >= 3:
                            return sort_standings_zero_last(df)
                        logger.warning(f"Jolpica returned only {len(df)} constructors for {season}, falling back to Ergast")
        except Exception as e:
            logger.error(f"Jolpica API error (constructors): {e}")

    if season < datetime.now().year:
        try:
            df = await _run_sync(get_constructor_standings_df, season, round_number)
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Ergast fallback failed for constructors {season}: {e}")

    return await _get_zero_point_constructor_standings()


# ==========================================
# СКРЫТЫЕ ФУНКЦИИ ГЕНЕРАЦИИ МЕЖСЕЗОНЬЯ
# ==========================================

async def _get_zero_point_driver_standings() -> pd.DataFrame:
    """Собирает сетку пилотов из OpenF1 и выдает всем 0 очков. driverId берём из Ergast по code."""
    current_year = datetime.now().year
    ergast_drivers: dict[str, str] = {}  # code -> driverId
    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(f"https://api.jolpi.ca/ergast/f1/{current_year}/drivers.json?limit=50") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for d in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                        c = d.get("code", "").upper()
                        if c:
                            ergast_drivers[c] = d.get("driverId", "")
        except Exception:
            pass

        url = "https://api.openf1.org/v1/drivers?session_key=latest"
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

                    code = d.get('name_acronym', '???')
                    driver_id = ergast_drivers.get(code.upper(), str(driver_num))

                    parsed_data.append({
                        "position": "-",
                        "points": 0.0,
                        "driverCode": code,
                        "givenName": given,
                        "familyName": family,
                        "driverId": driver_id,
                        "permanentNumber": str(driver_num),
                        "constructorId": (d.get("team_name") or "").lower().replace(" ", "_"),
                        "constructorName": d.get("team_name", ""),
                    })

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


@cache_result(ttl=86400, key_prefix="race_res")
async def get_race_results_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


@cache_result(ttl=86400, key_prefix="quali_res")
async def _get_quali_async(season: int, round_number: int, limit: int = 20):
    return await _run_sync(get_qualifying_results, season, round_number, limit)


@cache_result(ttl=3600, key_prefix="lat_quali")
async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20):
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


async def get_event_details_async(season: int, round_number: int):
    return await _run_sync(get_event_details, season, round_number)


async def get_driver_full_name_async(season: int, round_num: int, driver_code: str) -> str:
    """Возвращает полное имя пилота по коду (GivenName FamilyName) или код, если не найден."""
    code_upper = (driver_code or "").upper().strip()
    if not code_upper:
        return driver_code or "?"

    df = await get_driver_standings_async(season, round_num)
    if not df.empty and "driverCode" in df.columns:
        for row in df.itertuples(index=False):
            c = getattr(row, "driverCode", "") or ""
            if str(c).upper() == code_upper:
                given = getattr(row, "givenName", "") or ""
                family = getattr(row, "familyName", "") or ""
                return f"{given} {family}".strip() or code_upper

    results_df = await get_race_results_async(season, round_num)
    if not results_df.empty:
        for row in results_df.itertuples(index=False):
            abbr = str(getattr(row, "Abbreviation", "") or "").upper()
            if abbr == code_upper:
                given = str(getattr(row, "FirstName", "") or "")
                family = str(getattr(row, "LastName", "") or "")
                return f"{given} {family}".strip() or code_upper

    return code_upper


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


# --- КАРТОЧКА ПИЛОТА --- #
async def _resolve_driver_id(code_or_id: str, season: int) -> str | None:
    """Преобразует code (ALO) в driverId (alonso) через список пилотов сезона или общий список."""
    base = "https://api.jolpi.ca/ergast/f1"
    code_upper = code_or_id.strip().upper()
    async with aiohttp.ClientSession() as session:
        # Сначала пробуем сезон (актуальные пилоты 2026 и т.д.)
        async with session.get(f"{base}/{season}/drivers.json?limit=50") as resp:
            if resp.status == 200:
                data = await resp.json()
                for d in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                    if d.get("code", "").upper() == code_upper:
                        return d.get("driverId", code_or_id.lower())
        # Фоллбэк: общий список пилотов (для новых пилотов, которых ещё нет в сезоне)
        async with session.get(f"{base}/drivers.json?limit=500") as resp:
            if resp.status == 200:
                data = await resp.json()
                for d in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                    if d.get("code", "").upper() == code_upper:
                        return d.get("driverId", code_or_id.lower())
    return code_or_id.lower()


@cache_result(ttl=3600, key_prefix="driver_details")
async def get_driver_details_async(driver_id: str, season: int, code: str | None = None):
    """
    Получает профиль пилота, статистику сезона и карьеры из Ergast/Jolpica API.
    driver_id: ergast driverId (например alonso) или code (ALO).
    code: опционально, для разрешения когда driver_id — номер из OpenF1.
    """
    base = "https://api.jolpi.ca/ergast/f1"
    did = driver_id.strip().lower()
    resolve_code = (code or driver_id).strip().upper()
    if (len(did) == 3 and did == did.upper().lower()) or did.isdigit():
        resolved = await _resolve_driver_id(resolve_code, season)
        if resolved and not resolved.isdigit():
            did = resolved
    driver_info = None
    career_results = []

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{base}/drivers/{did}.json") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    drivers = data.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
                    if drivers:
                        driver_info = drivers[0]
        except Exception as e:
            logger.warning(f"Driver info fetch error: {e}")

        if not driver_info:
            return None

        try:
            offset = 0
            limit = 100
            while True:
                async with session.get(
                    f"{base}/drivers/{did}/results.json?limit={limit}&offset={offset}"
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    mr = data.get("MRData", {})
                    total = int(mr.get("total", 0))
                    races = mr.get("RaceTable", {}).get("Races", [])
                    for race in races:
                        for res in race.get("Results", []):
                            career_results.append({
                                "season": race.get("season"),
                                "position": res.get("position"),
                                "positionText": res.get("positionText", ""),
                                "points": float(res.get("points", 0)),
                                "grid": res.get("grid"),
                                "status": res.get("status", ""),
                                "laps": res.get("laps"),
                            })
                    offset += limit
                    if offset >= total:
                        break
        except Exception as e:
            logger.warning(f"Driver results fetch error: {e}")

        # Wikipedia bio
        bio = ""
        wiki_url = driver_info.get("url", "")
        if wiki_url and "wikipedia.org/wiki/" in wiki_url:
            try:
                title = wiki_url.split("wiki/")[-1].replace(" ", "_")
                async with session.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "format": "json",
                        "action": "query",
                        "prop": "extracts",
                        "exintro": 1,
                        "explaintext": 1,
                        "redirects": 1,
                        "titles": title,
                    },
                ) as wresp:
                    if wresp.status == 200:
                        wdata = await wresp.json()
                        pages = wdata.get("query", {}).get("pages", {})
                        for pid, p in pages.items():
                            if pid != "-1" and p.get("extract"):
                                bio = p["extract"][:2000]
                                break
            except Exception as e:
                logger.debug(f"Wikipedia fetch error: {e}")

        # Headshot from OpenF1 (optional). Предпочитаем URL без d_driver_fallback_image
        headshot_url = ""
        code_match = driver_info.get("code", "").upper()
        try:
            async with session.get("https://api.openf1.org/v1/drivers?session_key=latest") as oresp:
                if oresp.status == 200:
                    drivers_o = await oresp.json()
                    for d in drivers_o:
                        if d.get("name_acronym", "").upper() == code_match:
                            url = d.get("headshot_url") or ""
                            if url:
                                headshot_url = url
                                break
            if "d_driver_fallback_image" in headshot_url:
                async with session.get("https://api.openf1.org/v1/drivers") as oresp2:
                    if oresp2.status == 200:
                        drivers_all = await oresp2.json()
                        for d in drivers_all:
                            if d.get("name_acronym", "").upper() == code_match:
                                url = d.get("headshot_url") or ""
                                if url and "d_driver_fallback_image" not in url:
                                    headshot_url = url
                                    break
        except Exception:
            pass

    # Career stats
    gp_entered = len(career_results)
    career_points = sum(r["points"] for r in career_results)
    wins = sum(1 for r in career_results if r.get("position") == "1")
    podiums = sum(1 for r in career_results if r.get("position") in ("1", "2", "3"))
    poles = sum(1 for r in career_results if r.get("grid") == "1")
    dnfs = sum(1 for r in career_results if r.get("positionText") in ("R", "D", "W", "F", "N", "E", "EX"))

    # Season stats
    season_results = [r for r in career_results if r.get("season") == str(season)]
    season_gp = len(season_results)
    season_points = sum(r["points"] for r in season_results)
    season_wins = sum(1 for r in season_results if r.get("position") == "1")
    season_podiums = sum(1 for r in season_results if r.get("position") in ("1", "2", "3"))
    season_poles = sum(1 for r in season_results if r.get("grid") == "1")
    season_dnfs = sum(1 for r in season_results if r.get("positionText") in ("R", "D", "W", "F", "N", "E", "EX"))

    # Season position from standings
    standings_df = await get_driver_standings_async(season)
    season_pos: int | str = 0
    if not standings_df.empty and "driverCode" in standings_df.columns:
        for row in standings_df.itertuples(index=False):
            row_code = getattr(row, "driverCode", "") or (getattr(row, "familyName", "")[:3].upper() if getattr(row, "familyName", "") else "")
            if str(row_code).upper() == driver_info.get("code", "").upper():
                season_pos = getattr(row, "position", 0)
                break

    # World championships: проверяем, в каких сезонах пилот стал чемпионом
    driver_seasons = sorted(set(r.get("season") for r in career_results if r.get("season")), reverse=True)
    world_championships = await _count_driver_championships(did, driver_seasons)

    return {
        "driverId": driver_info.get("driverId"),
        "code": driver_info.get("code", ""),
        "givenName": driver_info.get("givenName", ""),
        "familyName": driver_info.get("familyName", ""),
        "permanentNumber": str(driver_info.get("permanentNumber", "")) if driver_info.get("permanentNumber") else "",
        "dateOfBirth": driver_info.get("dateOfBirth", ""),
        "nationality": driver_info.get("nationality", ""),
        "url": wiki_url,
        "bio": bio,
        "headshot_url": headshot_url,
        "season": season,
        "season_stats": {
            "position": season_pos,
            "points": season_points,
            "grand_prix_races": season_gp,
            "grand_prix_points": season_points,
            "grand_prix_wins": season_wins,
            "grand_prix_podiums": season_podiums,
            "grand_prix_poles": season_poles,
            "grand_prix_top10s": sum(1 for r in season_results if r.get("position") and r["position"].isdigit() and int(r["position"]) <= 10),
            "fastest_laps": 0,  # Ergast results don't have fast lap flag directly
            "dnfs": season_dnfs,
            "sprint_races": 0,
            "sprint_points": 0,
            "sprint_wins": 0,
            "sprint_podiums": 0,
            "sprint_poles": 0,
            "sprint_top10s": 0,
        },
        "career_stats": {
            "grand_prix_entered": gp_entered,
            "career_points": career_points,
            "highest_race_finish": _highest_finish(career_results),
            "podiums": podiums,
            "highest_grid": _highest_grid(career_results),
            "pole_positions": poles,
            "world_championships": world_championships,
            "dnfs": dnfs,
        },
    }


# Фоллбэк: известные чемпионы мира (driverId -> кол-во титулов), когда API не возвращает данные
DRIVER_CHAMPIONSHIPS_FALLBACK: dict[str, int] = {
    "hamilton": 7,
    "schumacher": 7,
    "fangio": 5,
    "prost": 4,
    "vettel": 4,
    "piquet": 3,
    "senna": 3,
    "lauda": 3,
    "brabham": 3,
    "stewart": 3,
    "fittipaldi": 2,
    "hakkinen": 2,
    "alonso": 2,
    "raikkonen": 1,
    "button": 1,
    "rosberg": 1,
    "verstappen": 4,  # по состоянию на 2024
}


async def _count_driver_championships(driver_id: str, seasons: list[str]) -> int:
    """Считает чемпионства пилота по итогам сезонов (position=1 в driverStandings)."""
    if not seasons:
        return 0
    base = "https://api.jolpi.ca/ergast/f1"
    count = 0
    async with aiohttp.ClientSession() as session:
        for yr in seasons:
            try:
                # limit=1 может вернуть первый раунд; запрашиваем все раунды и берём последний
                async with session.get(f"{base}/{yr}/driverStandings.json?limit=100") as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
                    if not lists:
                        continue
                    # Берём последний раунд (финальная таблица)
                    last_list = lists[-1]
                    standings = last_list.get("DriverStandings", [])
                    for ds in standings:
                        if str(ds.get("position", "")) == "1":
                            champ_id = ds.get("Driver", {}).get("driverId", "")
                            if champ_id and champ_id.lower() == driver_id.lower():
                                count += 1
                            break
            except Exception:
                continue
    # Фоллбэк: если API вернул 0, но пилот — известный чемпион
    if count == 0 and driver_id:
        fallback = DRIVER_CHAMPIONSHIPS_FALLBACK.get(driver_id.lower())
        if fallback is not None:
            return fallback
    return count


def _highest_finish(results: list) -> dict:
    """Возвращает {'position': 1, 'count': 5} для лучшего финиша."""
    positions = [int(r["position"]) for r in results if r.get("position") and str(r["position"]).isdigit()]
    if not positions:
        return {"position": "-", "count": 0}
    best = min(positions)
    count = sum(1 for r in results if r.get("position") == str(best))
    return {"position": best, "count": count}


def _highest_grid(results: list) -> dict:
    """Возвращает {'position': 1, 'count': 2} для лучшей позиции на старте."""
    grids = [int(r["grid"]) for r in results if r.get("grid") and str(r["grid"]).isdigit()]
    if not grids:
        return {"position": "-", "count": 0}
    best = min(grids)
    count = sum(1 for r in results if r.get("grid") == str(best))
    return {"position": best, "count": count}


# ISO 3 country_code (OpenF1) -> nationality строка для флагов (Ergast-совместимый формат)
COUNTRY_CODE_TO_NATIONALITY: dict[str, str] = {
    "GBR": "British",
    "NED": "Dutch",
    "FRA": "French",
    "ESP": "Spanish",
    "AUS": "Australian",
    "MON": "Monegasque",
    "MEX": "Mexican",
    "CAN": "Canadian",
    "JPN": "Japanese",
    "GER": "German",
    "ITA": "Italian",
    "USA": "American",
    "SUI": "Swiss",
    "DEN": "Danish",
    "THA": "Thai",
    "FIN": "Finnish",
    "CHN": "Chinese",
    "BRA": "Brazilian",
    "AUT": "Austrian",
    "BEL": "Belgian",
    "POL": "Polish",
    "RUS": "Russian",
    "SWE": "Swedish",
    "IRL": "Irish",
    "POR": "Portuguese",
    "HUN": "Hungarian",
    "ZAF": "South African",
    "IND": "Indian",
    "ARG": "Argentine",
    "NZL": "New Zealander",
}

# Маппинг OpenF1/альтернативных ID команд на Ergast constructorId
CONSTRUCTOR_ID_MAP = {
    "haas_f1_team": "haas",
    "red_bull_racing": "red_bull",
    "racing_bulls": "rb",
    "rb_f1_team": "rb",
    "alphatauri": "rb",  # Racing Bulls — преемник AlphaTauri
    "scuderia_ferrari": "ferrari",
    "scuderia_ferrari_f1": "ferrari",
    "alpine_f1_team": "alpine",
    "mercedes_amg": "mercedes",
    "mercedes_amg_f1": "mercedes",
}


async def _get_constructor_drivers_fallback(
    session: aiohttp.ClientSession,
    cid: str,
    season: int,
    constructor_info: dict | None,
) -> list:
    """Фоллбэк: пилоты из driver standings или OpenF1, когда Ergast не вернул данных."""
    ergast_base = "https://api.jolpi.ca/ergast/f1"
    # 1. Пробуем driver standings за сезон (если есть данные)
    try:
        async with session.get(f"{ergast_base}/{season}/driverStandings.json?limit=50") as resp:
            if resp.status == 200:
                data = await resp.json()
                lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
                if lists:
                    result = []
                    # Берём последний раунд (финальная таблица)
                    last_list = lists[-1]
                    for ds in last_list.get("DriverStandings", []):
                        for c in ds.get("Constructors", []):
                            if c.get("constructorId", "").lower() == cid:
                                dr = ds.get("Driver", {})
                                result.append({
                                    "driverId": dr.get("driverId", ""),
                                    "code": dr.get("code", ""),
                                    "givenName": dr.get("givenName", ""),
                                    "familyName": dr.get("familyName", ""),
                                    "permanentNumber": str(dr.get("permanentNumber", "")) if dr.get("permanentNumber") else "",
                                    "nationality": dr.get("nationality", ""),
                                })
                                break
                    if result:
                        return result
    except Exception:
        pass

    # 2. OpenF1: ТОЛЬКО для текущего/будущего сезона (session_key=latest = нынешний состав)
    current_year = datetime.now().year
    if season < current_year:
        return []  # Не подставлять пилотов нынешнего сезона за прошлые годы

    cid_to_openf1 = {
        "alpine": ["alpine"],
        "haas": ["haas", "haas f1 team"],
        "aston_martin": ["aston martin"],
        "ferrari": ["ferrari"],
        "mercedes": ["mercedes"],
        "mclaren": ["mclaren"],
        "red_bull": ["red bull", "red bull racing"],
        "rb": ["rb", "racing bulls", "rb f1 team", "alphatauri"],
        "williams": ["williams"],
        "audi": ["audi"],
        "cadillac": ["cadillac"],
    }
    openf1_names = cid_to_openf1.get(cid, [])
    if constructor_info and constructor_info.get("name"):
        cname = constructor_info.get("name", "").lower()
        if cname and cname not in openf1_names:
            openf1_names = openf1_names + [cname]

    try:
        async with session.get("https://api.openf1.org/v1/drivers?session_key=latest") as resp:
            if resp.status != 200:
                return []
            drivers_o = await resp.json()
            # Резолв code -> driverId и nationality из Ergast для корректных ссылок и флагов
            code_to_driver_id: dict[str, str] = {}
            code_to_nationality: dict[str, str] = {}
            try:
                async with session.get(f"{ergast_base}/{season}/drivers.json?limit=50") as eresp:
                    if eresp.status == 200:
                        edata = await eresp.json()
                        for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                            c = (dr.get("code") or "").upper()
                            if c:
                                code_to_driver_id[c] = dr.get("driverId", "")
                                code_to_nationality[c] = dr.get("nationality", "")
                # Фоллбэк: общий список пилотов (для новых, кого ещё нет в сезоне)
                async with session.get(f"{ergast_base}/drivers.json?limit=500") as eresp:
                    if eresp.status == 200:
                        edata = await eresp.json()
                        for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                            c = (dr.get("code") or "").upper()
                            if c and c not in code_to_nationality:
                                code_to_driver_id.setdefault(c, dr.get("driverId", ""))
                                code_to_nationality[c] = dr.get("nationality", "")
            except Exception:
                pass

            result = []
            for d in drivers_o:
                team = (d.get("team_name") or "").lower()
                if not team:
                    continue
                matched = any(t in team or team in t for t in openf1_names) or any(
                    t.replace(" ", "") in team.replace(" ", "") for t in openf1_names
                )
                if not matched:
                    continue
                code = d.get("name_acronym", "") or ""
                driver_id = code_to_driver_id.get(code.upper(), code.lower()) if code else ""
                nationality = code_to_nationality.get(code.upper(), "") if code else ""
                full = d.get("full_name", "Unknown")
                parts = full.split(" ", 1)
                given = parts[0] if parts else ""
                family = parts[1] if len(parts) > 1 else full
                result.append({
                    "driverId": driver_id or code.lower(),
                    "code": code,
                    "givenName": given,
                    "familyName": family,
                    "permanentNumber": str(d.get("driver_number", "")),
                    "nationality": nationality,
                    "headshot_url": d.get("headshot_url", "") or "",
                })
            # Убираем дубли по driver_number (один пилот — одна запись)
            by_num = {}
            for r in result:
                key = r.get("permanentNumber") or r.get("code")
                if key and key not in by_num:
                    by_num[key] = r
            return list(by_num.values()) if by_num else result
    except Exception:
        pass
    return []


# --- КАРТОЧКА КОНСТРУКТОРА --- #
@cache_result(ttl=3600, key_prefix="constructor_details_v6")
async def get_constructor_details_async(constructor_id: str, season: int):
    """Профиль команды: название, лого, статистика сезона и карьеры, биография."""
    base = "https://api.jolpi.ca/ergast/f1"
    cid = constructor_id.strip().lower().replace(" ", "_")
    cid = CONSTRUCTOR_ID_MAP.get(cid, cid)
    constructor_info = None
    career_results: list = []
    season_drivers: list = []

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{base}/constructors/{cid}.json") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    constructors = data.get("MRData", {}).get("ConstructorTable", {}).get("Constructors", [])
                    if constructors:
                        constructor_info = constructors[0]
        except Exception as e:
            logger.warning(f"Constructor info fetch error: {e}")

        if not constructor_info:
            return None

        try:
            offset = 0
            limit = 100
            while True:
                async with session.get(
                    f"{base}/constructors/{cid}/results.json?limit={limit}&offset={offset}"
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    mr = data.get("MRData", {})
                    total = int(mr.get("total", 0))
                    races = mr.get("RaceTable", {}).get("Races", [])
                    for race in races:
                        for res in race.get("Results", []):
                            career_results.append({
                                "season": race.get("season"),
                                "position": res.get("position"),
                                "positionText": res.get("positionText", ""),
                                "points": float(res.get("points", 0)),
                                "grid": res.get("grid"),
                            })
                    offset += limit
                    if offset >= total:
                        break
        except Exception as e:
            logger.warning(f"Constructor results fetch error: {e}")

        # Пилоты команды в этом сезоне
        season_drivers = []
        try:
            async with session.get(f"{base}/{season}/constructors/{cid}/drivers.json?limit=10") as dresp:
                if dresp.status == 200:
                    ddata = await dresp.json()
                    for d in ddata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                        nat = d.get("nationality") or ""
                        season_drivers.append({
                            "driverId": d.get("driverId"),
                            "code": d.get("code", ""),
                            "givenName": d.get("givenName", ""),
                            "familyName": d.get("familyName", ""),
                            "permanentNumber": str(d.get("permanentNumber", "")) if d.get("permanentNumber") else "",
                            "nationality": str(nat).strip() if nat else "",
                        })
        except Exception:
            pass

        # Фоллбэк: если Ergast не вернул пилотов (например, будущий сезон), берём из driver standings или OpenF1
        if not season_drivers:
            season_drivers = await _get_constructor_drivers_fallback(session, cid, season, constructor_info)

        # Headshots и nationality из OpenF1: session_key=latest, затем /v1/drivers для недостающих
        def _fill_headshots_and_nationality(drivers_o: list, overwrite_headshot: bool = False) -> None:
            for sd in season_drivers:
                code = sd.get("code", "").upper()
                for d in drivers_o:
                    if d.get("name_acronym", "").upper() == code:
                        url = d.get("headshot_url") or ""
                        if url and (overwrite_headshot or not sd.get("headshot_url")):
                            sd["headshot_url"] = url
                        if not sd.get("nationality"):
                            cc = (d.get("country_code") or "").upper()
                            if cc and cc in COUNTRY_CODE_TO_NATIONALITY:
                                sd["nationality"] = COUNTRY_CODE_TO_NATIONALITY[cc]
                        break

        if season_drivers:
            try:
                async with session.get("https://api.openf1.org/v1/drivers?session_key=latest") as oresp:
                    if oresp.status == 200:
                        drivers_o = await oresp.json()
                        _fill_headshots_and_nationality(drivers_o, overwrite_headshot=False)
                # Fallback: /v1/drivers для пилотов без headshot или nationality
                missing = any(
                    not sd.get("headshot_url") or not sd.get("nationality")
                    for sd in season_drivers
                )
                if missing:
                    try:
                        async with session.get("https://api.openf1.org/v1/drivers") as oresp2:
                            if oresp2.status == 200:
                                drivers_all = await oresp2.json()
                                _fill_headshots_and_nationality(drivers_all, overwrite_headshot=False)
                    except Exception:
                        pass
                for sd in season_drivers:
                    if "headshot_url" not in sd:
                        sd["headshot_url"] = ""
                # Нормализация: nationality всегда строка, fallback из Ergast если пусто
                missing_nat = [sd for sd in season_drivers if not (sd.get("nationality") or "").strip()]
                if missing_nat:
                    try:
                        async with session.get(f"{base}/drivers.json?limit=500") as eresp:
                            if eresp.status == 200:
                                edata = await eresp.json()
                                code_to_nat = {}
                                for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                                    c = (dr.get("code") or "").upper()
                                    n = dr.get("nationality") or ""
                                    if c and n:
                                        code_to_nat[c] = str(n).strip()
                                for sd in missing_nat:
                                    n = code_to_nat.get((sd.get("code") or "").upper(), "")
                                    sd["nationality"] = n
                    except Exception:
                        pass
                for sd in season_drivers:
                    sd["nationality"] = (sd.get("nationality") or "").strip() or ""
            except Exception:
                for sd in season_drivers:
                    sd["headshot_url"] = sd.get("headshot_url", "")

        # Финальная проверка nationality (fallback из Ergast drivers, если пусто)
        for sd in season_drivers:
            sd["nationality"] = (sd.get("nationality") or "").strip() or ""
        missing_nat = [sd for sd in season_drivers if not sd.get("nationality")]
        if missing_nat:
            try:
                async with session.get(f"{base}/drivers.json?limit=500") as eresp:
                    if eresp.status == 200:
                        edata = await eresp.json()
                        code_to_nat = {}
                        for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                            c = (dr.get("code") or "").upper()
                            n = (dr.get("nationality") or "").strip()
                            if c and n:
                                code_to_nat[c] = n
                        for sd in missing_nat:
                            sd["nationality"] = code_to_nat.get((sd.get("code") or "").upper(), "")
            except Exception:
                pass

        wiki_url = constructor_info.get("url", "")
        bio = ""
        if wiki_url and "wikipedia.org/wiki/" in wiki_url:
            try:
                title = wiki_url.split("wiki/")[-1].replace(" ", "_")
                async with session.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "format": "json",
                        "action": "query",
                        "prop": "extracts",
                        "exintro": 1,
                        "explaintext": 1,
                        "redirects": 1,
                        "titles": title,
                    },
                ) as wresp:
                    if wresp.status == 200:
                        wdata = await wresp.json()
                        pages = wdata.get("query", {}).get("pages", {})
                        for pid, p in pages.items():
                            if pid != "-1" and p.get("extract"):
                                bio = p["extract"][:2000]
                                break
            except Exception:
                pass

    season_results = [r for r in career_results if r.get("season") == str(season)]
    gp_entered = len(career_results)
    career_points = sum(r["points"] for r in career_results)
    wins = sum(1 for r in career_results if r.get("position") == "1")
    podiums = sum(1 for r in career_results if r.get("position") in ("1", "2", "3"))
    poles = sum(1 for r in career_results if r.get("grid") == "1")

    standings_df = await get_constructor_standings_async(season)
    season_pos: int | str = 0
    if not standings_df.empty:
        for row in standings_df.itertuples(index=False):
            row_cid = getattr(row, "constructorId", "")
            if str(row_cid).lower() == cid:
                season_pos = getattr(row, "position", 0)
                break

    constructor_seasons = sorted(set(r.get("season") for r in career_results if r.get("season")), reverse=True)
    world_championships = await _count_constructor_championships(cid, constructor_seasons)

    return {
        "constructorId": constructor_info.get("constructorId"),
        "name": constructor_info.get("name", ""),
        "nationality": constructor_info.get("nationality", ""),
        "url": wiki_url,
        "bio": bio,
        "drivers": season_drivers,
        "season": season,
        "season_stats": {
            "position": season_pos,
            "points": sum(r["points"] for r in season_results),
            "grand_prix_races": len(season_results),
            "grand_prix_wins": sum(1 for r in season_results if r.get("position") == "1"),
            "grand_prix_podiums": sum(1 for r in season_results if r.get("position") in ("1", "2", "3")),
            "grand_prix_poles": sum(1 for r in season_results if r.get("grid") == "1"),
        },
        "career_stats": {
            "grand_prix_entered": gp_entered,
            "career_points": career_points,
            "highest_race_finish": _highest_finish(career_results),
            "podiums": podiums,
            "pole_positions": poles,
            "world_championships": world_championships,
        },
    }


# Фоллбэк: известные чемпионы конструкторов (constructorId -> титулы)
CONSTRUCTOR_CHAMPIONSHIPS_FALLBACK: dict[str, int] = {
    "ferrari": 16,
    "williams": 9,
    "mclaren": 8,
    "mercedes": 8,
    "lotus": 7,
    "red_bull": 6,
    "cooper": 2,
    "brawn": 1,
    "benetton": 1,
    "renault": 2,
    "tyrrell": 1,
}


async def _count_constructor_championships(constructor_id: str, seasons: list[str]) -> int:
    """Считает чемпионства команды в кубке конструкторов."""
    if not seasons:
        return 0
    base = "https://api.jolpi.ca/ergast/f1"
    count = 0
    async with aiohttp.ClientSession() as session:
        for yr in seasons:
            try:
                async with session.get(f"{base}/{yr}/constructorStandings.json?limit=100") as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
                    if not lists:
                        continue
                    last_list = lists[-1]
                    standings = last_list.get("ConstructorStandings", [])
                    for cs in standings:
                        if str(cs.get("position", "")) == "1":
                            champ_id = cs.get("Constructor", {}).get("constructorId", "")
                            if champ_id and champ_id.lower() == constructor_id.lower():
                                count += 1
                            break
            except Exception:
                continue
    if count == 0 and constructor_id:
        fallback = CONSTRUCTOR_CHAMPIONSHIPS_FALLBACK.get(constructor_id.lower())
        if fallback is not None:
            return fallback
    return count


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
