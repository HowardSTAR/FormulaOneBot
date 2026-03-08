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


QUALI_CACHE_TTL = 14 * 24 * 3600  # 14 дней — до следующей квалификации с запасом
QUALI_CACHE_KEY = "f1bot:quali_results_v2"  # v2: с поддержкой lap_duration (секунды) из OpenF1


async def get_cached_quali_results(season: int) -> dict | None:
    """Сохраняемые результаты последней квалификации (до следующей квалы)."""
    import json
    key = f"{QUALI_CACHE_KEY}:{season}"
    if _REDIS_CLIENT is not None:
        try:
            raw = await _REDIS_CLIENT.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"Redis quali cache read: {e}")
    try:
        path = _fallback_cache_dir / f"quali_results_v2_{season}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"File quali cache read: {e}")
    return None


async def set_cached_quali_results(season: int, payload: dict) -> None:
    """Сохранить результаты квалификации до следующей квалы."""
    import json
    key = f"{QUALI_CACHE_KEY}:{season}"
    raw = json.dumps(payload, ensure_ascii=False)
    if _REDIS_CLIENT is not None:
        try:
            await _REDIS_CLIENT.setex(key, QUALI_CACHE_TTL, raw)
        except Exception as e:
            logger.debug(f"Redis quali cache write: {e}")
    try:
        path = _fallback_cache_dir / f"quali_results_v2_{season}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    except Exception as e:
        logger.debug(f"File quali cache write: {e}")


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


def get_qualifying_results(season: int, round_number: int, limit: int = 100) -> list[dict]:
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
            best_seconds_list = []
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
                best_sec = pd.to_timedelta(best_time).total_seconds() if best_time is not None and pd.notna(best_time) else None
                if best_sec is not None:
                    best_seconds_list.append(best_sec)

                results.append({
                    "position": pos_int,
                    "driver": code,
                    "name": name,
                    "best": best_str,
                    "best_seconds": best_sec,
                })

            min_sec = min(best_seconds_list) if best_seconds_list else None
            for r in results:
                bs = r.pop("best_seconds", None)
                if bs is None or min_sec is None:
                    r["gap"] = "—"
                elif bs <= min_sec:
                    r["gap"] = r["best"]
                else:
                    r["gap"] = f"+{bs - min_sec:.3f}"

            results.sort(key=lambda r: r["position"])
            return results[:limit]

        except Exception as e:
            logger.error(f"Quali load error {season}/{round_number}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
    return []


def get_latest_quali_results(season: int, max_round: int | None = None, limit: int = 100):
    schedule = get_season_schedule_short(season)
    if not schedule:
        return None, []

    now = datetime.now(timezone.utc)
    passed_rounds = []

    for r in schedule:
        try:
            # Квалификация считается прошедшей, если её старт уже был (не только по дате гонки)
            quali_utc = r.get("quali_start_utc")
            if quali_utc:
                quali_dt = datetime.fromisoformat(quali_utc)
                if quali_dt.tzinfo is None:
                    quali_dt = quali_dt.replace(tzinfo=timezone.utc)
                if now > quali_dt:
                    passed_rounds.append(r["round"])
            else:
                r_date = _date.fromisoformat(r["date"])
                if r_date <= now.date():
                    passed_rounds.append(r["round"])
        except Exception:
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


# --- OPENF1: LIVE TIMING (результаты сразу после сессии) --- #
# Используем /position для моментальных результатов без ожидания официальных протоколов FIA.

OPENF1_BASE = "https://api.openf1.org/v1"


async def _openf1_get(path: str, **params) -> list | None:
    """GET запрос к OpenF1 API. Возвращает список записей или None при ошибке."""
    url = f"{OPENF1_BASE}/{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as e:
        logger.debug(f"OpenF1 {path} error: {e}")
        return None


async def _openf1_get_latest_session() -> dict | None:
    """Текущая/последняя сессия (session_key=latest)."""
    data = await _openf1_get("sessions", session_key="latest")
    if not data or not isinstance(data, list):
        return None
    return data[0] if data else None


def _openf1_position_final_from_rows(rows: list) -> list[dict]:
    """Из сырых записей position берём последнюю позицию по времени для каждого пилота."""
    from collections import defaultdict
    by_driver: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for row in rows:
        dn = row.get("driver_number")
        pos = row.get("position")
        dt = row.get("date")
        if dn is not None and pos is not None and dt:
            by_driver[dn].append((dt, pos))
    result = []
    for driver_number, pairs in by_driver.items():
        pairs.sort(key=lambda x: x[0], reverse=True)
        result.append({"driver_number": driver_number, "position": pairs[0][1]})
    result.sort(key=lambda x: x["position"])
    return result


async def _openf1_get_position_final(session_key: int) -> list[dict]:
    """Финальные позиции в сессии (последнее известное положение по времени)."""
    rows = await _openf1_get("position", session_key=session_key)
    if not rows:
        return []
    return _openf1_position_final_from_rows(rows)


# Минимальный статический маппинг только как последний резерв (OpenF1 и standings могут быть пусты)
_DRIVER_NUMBER_TO_CODE_FALLBACK: dict[int, str] = {
    1: "VER", 44: "HAM", 4: "NOR", 81: "PIA", 16: "LEC", 55: "SAI",
}


async def _openf1_get_drivers_for_session(session_key: int) -> dict[int, dict]:
    """driver_number -> {code (name_acronym), name (full_name/last_name)}. Дополняет из /drivers без session."""
    out: dict[int, dict] = {}

    def _add(d: dict) -> None:
        num = d.get("driver_number")
        if num is None or num in out:
            return
        code = (d.get("name_acronym") or "").strip() or (d.get("last_name") or "")[:3].upper()
        name = (d.get("full_name") or d.get("last_name") or "").strip()
        out[num] = {
            "code": code or _DRIVER_NUMBER_TO_CODE_FALLBACK.get(num, "?"),
            "name": name or (code or _DRIVER_NUMBER_TO_CODE_FALLBACK.get(num, "?")),
        }

    data = await _openf1_get("drivers", session_key=session_key)
    if data:
        for d in data:
            _add(d)

    extra = await _openf1_get("drivers")
    if extra:
        for d in extra:
            num = d.get("driver_number")
            if num is not None and (num not in out or out[num].get("code") == "?"):
                _add(d)

    return out


def _openf1_match_round_from_schedule(schedule: list, session_date_start: str, location: str) -> int | None:
    """По дате и локации сессии находим round в нашем расписании."""
    if not schedule or not session_date_start:
        return None
    try:
        session_date = session_date_start[:10]
    except Exception:
        return None
    location_clean = (location or "").strip().lower()
    for r in schedule:
        if (r.get("date") or "") == session_date:
            loc = (r.get("location") or "").strip().lower()
            if loc and location_clean and (loc in location_clean or location_clean in loc):
                return r.get("round")
            if not location_clean or not loc:
                return r.get("round")
    return None


def _format_quali_time_ms(ms: float | None) -> str:
    """Форматирует время круга из миллисекунд в M:SS.mmm."""
    if ms is None or ms <= 0:
        return "—"
    try:
        sec = ms / 1000.0
        m = int(sec // 60)
        s = sec % 60
        return f"{m}:{s:06.3f}" if m > 0 else f"{s:.3f}"
    except Exception:
        return "—"


def _lap_duration_to_ms(row: dict) -> float | None:
    """Из записи /laps извлекает длительность круга в миллисекундах. OpenF1 отдаёт lap_duration в секундах."""
    raw_ms = row.get("lap_duration_ms") or row.get("duration_ms")
    if raw_ms is not None:
        try:
            return float(raw_ms)
        except (TypeError, ValueError):
            pass
    sec = row.get("lap_duration")
    if sec is not None:
        try:
            return float(sec) * 1000.0
        except (TypeError, ValueError):
            pass
    return None


async def _openf1_get_best_lap_per_driver(session_key: int) -> dict[int, float]:
    """Для сессии возвращает driver_number -> лучший lap_duration в мс (минимум)."""
    laps = await _openf1_get("laps", session_key=session_key)
    if not laps:
        return {}
    best: dict[int, float] = {}
    for row in laps:
        if row.get("is_pit_out_lap") is True:
            continue
        dn = row.get("driver_number")
        if dn is None:
            continue
        duration_ms = _lap_duration_to_ms(row)
        if duration_ms is not None and duration_ms > 0:
            if dn not in best or duration_ms < best[dn]:
                best[dn] = duration_ms
    return best


async def openf1_get_quali_results_live(season: int, limit: int = 100) -> tuple[int | None, list[dict]]:
    """
    Результаты квалификации из OpenF1 (моментально после сессии).
    Возвращает (round_num, list[{position, driver, name, best}]).
    best берётся из /laps (минимальный lap_duration_ms по пилоту).
    """
    session = await _openf1_get_latest_session()
    if not session or (session.get("session_type") or "").strip() != "Qualifying":
        return None, []
    session_key = session.get("session_key")
    if session_key is None:
        return None, []
    positions = await _openf1_get_position_final(session_key)
    drivers_map = await _openf1_get_drivers_for_session(session_key)
    best_laps = await _openf1_get_best_lap_per_driver(session_key)
    schedule = await get_season_schedule_short_async(season)
    round_num = _openf1_match_round_from_schedule(
        schedule or [],
        session.get("date_start") or "",
        session.get("location") or "",
    )
    valid_ms = [best_laps.get(p.get("driver_number")) for p in positions if best_laps.get(p.get("driver_number"))]
    min_ms = min(valid_ms) if valid_ms else None
    results = []
    for p in positions[:limit]:
        dn = p.get("driver_number")
        info = drivers_map.get(dn, {})
        best_ms = best_laps.get(dn) if dn is not None else None
        best_str = _format_quali_time_ms(best_ms) if best_ms else "—"
        if best_ms is None or min_ms is None:
            gap_str = "—"
        elif best_ms <= min_ms:
            gap_str = best_str
        else:
            gap_str = f"+{(best_ms - min_ms) / 1000:.3f}"
        results.append({
            "position": int(p.get("position", 0)),
            "driver": info.get("code", "?"),
            "name": info.get("name", "?"),
            "best": best_str,
            "gap": gap_str,
        })
    return round_num, results


async def openf1_get_quali_for_round(season: int, round_num: int, limit: int = 100) -> tuple[int | None, list[dict]]:
    """
    Результаты квалификации из OpenF1 для конкретного этапа (по расписанию).
    Нужно, когда session_key=latest — не Qualifying (например, уже гонка).
    """
    schedule = await get_season_schedule_short_async(season)
    event = next((r for r in (schedule or []) if r.get("round") == round_num), None)
    if not event:
        return None, []
    quali_date = None
    if event.get("quali_start_utc"):
        try:
            quali_date = (event["quali_start_utc"])[:10]
        except Exception:
            pass
    if not quali_date:
        quali_date = event.get("date") or ""
    if not quali_date:
        return None, []
    sessions = await _openf1_get("sessions", year=season)
    if not sessions:
        return None, []
    session_key = None
    for s in sessions:
        if (s.get("session_type") or "").strip() != "Qualifying":
            continue
        if (s.get("date_start") or "")[:10] == quali_date:
            session_key = s.get("session_key")
            break
    if session_key is None:
        return None, []
    positions = await _openf1_get_position_final(session_key)
    drivers_map = await _openf1_get_drivers_for_session(session_key)
    best_laps = await _openf1_get_best_lap_per_driver(session_key)
    valid_ms = [best_laps.get(p.get("driver_number")) for p in positions if best_laps.get(p.get("driver_number"))]
    min_ms = min(valid_ms) if valid_ms else None
    results = []
    for p in positions[:limit]:
        dn = p.get("driver_number")
        info = drivers_map.get(dn, {})
        best_ms = best_laps.get(dn) if dn is not None else None
        best_str = _format_quali_time_ms(best_ms) if best_ms else "—"
        if best_ms is None or min_ms is None:
            gap_str = "—"
        elif best_ms <= min_ms:
            gap_str = best_str
        else:
            gap_str = f"+{(best_ms - min_ms) / 1000:.3f}"
        results.append({
            "position": int(p.get("position", 0)),
            "driver": info.get("code", "?"),
            "name": info.get("name", "?"),
            "best": best_str,
            "gap": gap_str,
        })
    return round_num, results


async def get_quali_for_round_async(season: int, round_num: int, limit: int = 100) -> tuple[int | None, list[dict]]:
    """Результаты квалификации для конкретного этапа: OpenF1, при отсутствии — FastF1. Возвращает (round_num, results)."""
    r, results = await openf1_get_quali_for_round(season, round_num, limit=limit)
    if results:
        return (r if r is not None else round_num), results
    fastf1_list = await _get_quali_async(season, round_num, limit)
    return round_num, fastf1_list if fastf1_list else []


async def _get_driver_number_to_info_from_standings(season: int, round_num: int | None) -> dict[int, dict]:
    """driver_number (int) -> {code, name}. Источник: standings (Jolpica/Ergast)."""
    df = await get_driver_standings_async(season, round_num)
    out: dict[int, dict] = {}
    if df.empty or "permanentNumber" not in df.columns:
        return out
    for _, row in df.iterrows():
        pn = getattr(row, "permanentNumber", "") or ""
        try:
            num = int(pn)
        except (ValueError, TypeError):
            continue
        code = (getattr(row, "driverCode", "") or "").strip() or "?"
        given = (getattr(row, "givenName", "") or "").strip()
        family = (getattr(row, "familyName", "") or "").strip()
        name = f"{given} {family}".strip() or code
        out[num] = {"code": code, "name": name}
    return out


async def openf1_get_race_results_live(season: int, round_num: int | None = None) -> pd.DataFrame | None:
    """
    Результаты гонки из OpenF1. Если round_num задан — ищем сессию Race по расписанию.
    Иначе session_key=latest (если тип Race). Возвращает DataFrame в формате, похожем на FastF1 (Position, Abbreviation, FirstName, LastName, Points).
    """
    schedule = await get_season_schedule_short_async(season)
    schedule_list = schedule or []
    session_key = None
    used_latest_session = None
    if round_num is not None:
        event = next((r for r in schedule_list if r.get("round") == round_num), None)
        if event:
            race_date = event.get("date")
            if race_date:
                sessions = await _openf1_get("sessions", year=season)
                if sessions:
                    for s in sessions:
                        if (s.get("session_type") or "").strip() != "Race":
                            continue
                        ds = (s.get("date_start") or "")[:10]
                        if ds == race_date:
                            session_key = s.get("session_key")
                            break
    if session_key is None:
        used_latest_session = await _openf1_get_latest_session()
        if used_latest_session and (used_latest_session.get("session_type") or "").strip() == "Race":
            session_key = used_latest_session.get("session_key")
    if session_key is None:
        return None

    effective_round = round_num
    if effective_round is None and used_latest_session:
        effective_round = _openf1_match_round_from_schedule(
            schedule_list,
            used_latest_session.get("date_start") or "",
            used_latest_session.get("location_country") or used_latest_session.get("location") or "",
        )

    positions = await _openf1_get_position_final(session_key)
    drivers_map = await _openf1_get_drivers_for_session(session_key)
    standings_map = await _get_driver_number_to_info_from_standings(season, effective_round)

    rows = []
    for p in positions:
        dn = p.get("driver_number")
        info = drivers_map.get(dn, {})
        st = standings_map.get(dn, {}) if dn is not None else {}
        code = (info.get("code") or st.get("code") or "").strip()
        code = code or (_DRIVER_NUMBER_TO_CODE_FALLBACK.get(dn, "?") if dn is not None else "?")
        name = (info.get("name") or st.get("name") or "").strip() or code
        # Если name — это только код (2–4 заглавные буквы без пробела), не дублируем в FirstName+LastName
        is_code_only = len(name) <= 4 and name.isalpha() and name.isupper() and " " not in name
        if is_code_only:
            first, last = "", name
        else:
            parts = str(name).split(" ", 1)
            first = parts[0] if len(parts) > 0 else ""
            last = parts[1] if len(parts) > 1 else name
        rows.append({
            "Position": int(p.get("position", 0)),
            "Abbreviation": code,
            "FirstName": first,
            "LastName": last,
            "Points": 0,
        })
    return pd.DataFrame(rows) if rows else None


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

    # Фоллбэк: Ergast для прошедших сезонов
    if season < datetime.now().year:
        try:
            df = await _run_sync(get_driver_standings_df, season, round_number)
            if not df.empty:
                return df
        except Exception as e:
            logger.warning(f"Ergast fallback failed for {season}: {e}")

    # Текущий сезон: список пилотов 2026 из Ergast (составы уже есть до первой гонки)
    if season == datetime.now().year and round_number is None:
        df = await _get_drivers_list_ergast(season)
        if not df.empty:
            return sort_standings_zero_last(df)

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

    # Текущий сезон: список команд 2026 из Ergast
    if season == datetime.now().year and round_number is None:
        df = await _get_constructors_list_ergast(season)
        if not df.empty:
            return sort_standings_zero_last(df)

    return await _get_zero_point_constructor_standings()


# ==========================================
# СКРЫТЫЕ ФУНКЦИИ ГЕНЕРАЦИИ МЕЖСЕЗОНЬЯ
# ==========================================

async def _get_drivers_list_ergast(season: int) -> pd.DataFrame:
    """Список пилотов сезона из Ergast (без очков). Для избранного/составов до первой гонки."""
    async with aiohttp.ClientSession() as session:
        for base in _ERGAST_BASES:
            try:
                data = await _fetch_json(session, f"{base}/{season}/drivers.json?limit=50")
                if not data:
                    continue
                drivers = data.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
                if not drivers:
                    continue
                parsed = []
                for i, d in enumerate(drivers, 1):
                    code = (d.get("code") or "").strip() or (d.get("familyName", "")[:3].upper() if d.get("familyName") else "?")
                    parsed.append({
                        "position": i,
                        "points": 0.0,
                        "driverCode": code,
                        "givenName": d.get("givenName", ""),
                        "familyName": d.get("familyName", ""),
                        "driverId": d.get("driverId", ""),
                        "permanentNumber": str(d.get("permanentNumber", "")) if d.get("permanentNumber") else "",
                        "constructorId": "",
                        "constructorName": "",
                    })
                return pd.DataFrame(parsed)
            except Exception as e:
                logger.debug(f"Ergast drivers list {season}: {e}")
    return pd.DataFrame()


async def _get_constructors_list_ergast(season: int) -> pd.DataFrame:
    """Список команд сезона из Ergast. Для избранного до первой гонки."""
    async with aiohttp.ClientSession() as session:
        for base in _ERGAST_BASES:
            try:
                data = await _fetch_json(session, f"{base}/{season}/constructors.json?limit=30")
                if not data:
                    continue
                constructors = data.get("MRData", {}).get("ConstructorTable", {}).get("Constructors", [])
                if not constructors:
                    continue
                parsed = []
                for i, c in enumerate(constructors, 1):
                    parsed.append({
                        "position": i,
                        "points": 0.0,
                        "constructorId": c.get("constructorId", ""),
                        "constructorName": c.get("name", ""),
                    })
                return pd.DataFrame(parsed)
            except Exception as e:
                logger.debug(f"Ergast constructors list {season}: {e}")
    return pd.DataFrame()


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
async def _get_race_results_fastf1_async(season: int, round_number: int):
    return await _run_sync(get_race_results_df, season, round_number)


async def get_race_results_async(season: int, round_number: int):
    """Результаты гонки: сначала OpenF1 (live), при отсутствии — FastF1."""
    df = await openf1_get_race_results_live(season, round_number)
    if df is not None and not df.empty:
        return df
    return await _get_race_results_fastf1_async(season, round_number)


@cache_result(ttl=86400, key_prefix="quali_res")
async def _get_quali_async(season: int, round_number: int, limit: int = 100):
    return await _run_sync(get_qualifying_results, season, round_number, limit)


@cache_result(ttl=3600, key_prefix="lat_quali")
async def _get_latest_quali_fastf1_async(season: int, max_round: int | None = None, limit: int = 100):
    return await _run_sync(get_latest_quali_results, season, max_round, limit)


async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 100):
    """Результаты квалификации: OpenF1 (latest или по этапу), при отсутствии — FastF1."""
    round_num, results = await openf1_get_quali_results_live(season, limit=limit)
    if results and (max_round is None or (round_num is not None and round_num <= max_round)):
        return round_num, results
    # Когда session_key=latest не Qualifying — пробуем последний этап с прошедшей квалификацией
    schedule = await get_season_schedule_short_async(season)
    now = datetime.now(timezone.utc)
    passed_quali_rounds = []
    for r in (schedule or []):
        try:
            qutc = r.get("quali_start_utc")
            if qutc:
                qdt = datetime.fromisoformat(qutc)
                if qdt.tzinfo is None:
                    qdt = qdt.replace(tzinfo=timezone.utc)
                if now > qdt and (max_round is None or r["round"] <= max_round):
                    passed_quali_rounds.append(r["round"])
        except Exception:
            continue
    last_quali_round = max(passed_quali_rounds) if passed_quali_rounds else None
    if last_quali_round is not None:
        round_num, results = await openf1_get_quali_for_round(season, last_quali_round, limit=limit)
        if results:
            return round_num, results
    return await _get_latest_quali_fastf1_async(season, max_round, limit)


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
            _get_latest_quali_async(season, limit=100)
        )

    logger.info("✅ Cache warmup finished.")


# --- КАРТОЧКА ПИЛОТА --- #
async def _resolve_driver_id(code_or_id: str, season: int) -> str | None:
    """Преобразует code (ALO) в driverId (alonso) через список пилотов сезона или общий список."""
    code_upper = code_or_id.strip().upper()
    async with aiohttp.ClientSession() as session:
        for base in _ERGAST_BASES:
            try:
                data = await _fetch_json(session, f"{base}/{season}/drivers.json?limit=50")
                if data:
                    for d in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                        if d.get("code", "").upper() == code_upper:
                            return d.get("driverId", code_or_id.lower())
                data = await _fetch_json(session, f"{base}/drivers.json?limit=500")
                if data:
                    for d in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                        if d.get("code", "").upper() == code_upper:
                            return d.get("driverId", code_or_id.lower())
                break
            except Exception:
                continue
    return code_or_id.lower()


async def _fetch_driver_season_results(session: aiohttp.ClientSession, did: str, season: int) -> list:
    """Загружает результаты пилота за конкретный сезон."""
    for base in _ERGAST_BASES:
        try:
            resp_data = await _fetch_json(session, f"{base}/{season}/drivers/{did}/results.json?limit=100")
            if resp_data:
                results = []
                for race in resp_data.get("MRData", {}).get("RaceTable", {}).get("Races", []):
                    for res in race.get("Results", []):
                        results.append({
                            "season": race.get("season"),
                            "position": res.get("position"),
                            "positionText": res.get("positionText", ""),
                            "points": float(res.get("points", 0)),
                            "grid": res.get("grid"),
                            "status": res.get("status", ""),
                            "laps": res.get("laps"),
                        })
                if results:
                    return results
        except Exception:
            continue
    return []


async def _fetch_driver_career_results(session: aiohttp.ClientSession, did: str) -> list:
    """Загружает все результаты карьеры пилота."""
    for base in _ERGAST_BASES:
        try:
            offset = 0
            limit = 1000
            career = []
            while True:
                resp_data = await _fetch_json(session, f"{base}/drivers/{did}/results.json?limit={limit}&offset={offset}")
                if not resp_data:
                    break
                mr = resp_data.get("MRData", {})
                total = int(mr.get("total", 0))
                for race in mr.get("RaceTable", {}).get("Races", []):
                    for res in race.get("Results", []):
                        career.append({
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
            if career:
                return career
        except Exception:
            continue
    return []


async def _fetch_wiki_bio(session: aiohttp.ClientSession, wiki_url: str) -> str:
    """Загружает биографию из Wikipedia."""
    if not wiki_url or "wikipedia.org/wiki/" not in wiki_url:
        return ""
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
            timeout=aiohttp.ClientTimeout(total=10),
        ) as wresp:
            if wresp.status == 200:
                wdata = await wresp.json()
                pages = wdata.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    if pid != "-1" and p.get("extract"):
                        return p["extract"][:2000]
    except Exception:
        pass
    return ""


async def _fetch_driver_headshot(session: aiohttp.ClientSession, code_match: str, season: int) -> str:
    """Загружает URL headshot из OpenF1. Пропускает старые сезоны (до 2023)."""
    if not code_match or season < 2023:
        return ""
    try:
        async with session.get(
            "https://api.openf1.org/v1/drivers?session_key=latest",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as oresp:
            if oresp.status == 200:
                for d in await oresp.json():
                    if d.get("name_acronym", "").upper() == code_match:
                        url = d.get("headshot_url") or ""
                        if url:
                            return url
        async with session.get(
            "https://api.openf1.org/v1/drivers",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as oresp2:
            if oresp2.status == 200:
                for d in await oresp2.json():
                    if d.get("name_acronym", "").upper() == code_match:
                        url = d.get("headshot_url") or ""
                        if url:
                            return url
    except Exception:
        pass
    return ""


@cache_result(ttl=3600, key_prefix="driver_details_v3")
async def get_driver_details_async(driver_id: str, season: int, code: str | None = None):
    """
    Получает профиль пилота, статистику сезона и карьеры из Ergast/Jolpica API.
    driver_id: ergast driverId (например alonso) или code (ALO).
    code: опционально, для разрешения когда driver_id — номер из OpenF1.
    """
    did = driver_id.strip().lower()
    resolve_code = (code or driver_id).strip().upper()
    if (len(did) == 3 and did == did.upper().lower()) or did.isdigit():
        resolved = await _resolve_driver_id(resolve_code, season)
        if resolved and not resolved.isdigit():
            did = resolved

    async with aiohttp.ClientSession() as session:
        # 1. Информация о пилоте (обязательно первым — нужны wiki_url, code)
        data = await _try_bases(session, f"/drivers/{did}.json")
        driver_info = None
        if data:
            drivers = data.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
            if drivers:
                driver_info = drivers[0]
        if not driver_info:
            return None

        wiki_url = driver_info.get("url", "")
        code_match = driver_info.get("code", "").upper()

        # 2. Параллельная загрузка: сезон, карьера, биография, headshot, standings
        (
            season_results,
            career_results,
            bio,
            headshot_url,
            standings_df,
        ) = await asyncio.gather(
            _fetch_driver_season_results(session, did, season),
            _fetch_driver_career_results(session, did),
            _fetch_wiki_bio(session, wiki_url),
            _fetch_driver_headshot(session, code_match, season),
            get_driver_standings_async(season),
        )

    # Если season_results пусто, но career_results загружен — извлечём
    if not season_results and career_results:
        season_results = [r for r in career_results if r.get("season") == str(season)]

    # Career stats
    gp_entered = len(career_results)
    career_points = sum(r["points"] for r in career_results)
    wins = sum(1 for r in career_results if r.get("position") == "1")
    podiums = sum(1 for r in career_results if r.get("position") in ("1", "2", "3"))
    poles = sum(1 for r in career_results if r.get("grid") == "1")
    dnfs = sum(1 for r in career_results if r.get("positionText") in ("R", "D", "W", "F", "N", "E", "EX"))

    # Season stats
    season_gp = len(season_results)
    season_points = sum(r["points"] for r in season_results)
    season_wins = sum(1 for r in season_results if r.get("position") == "1")
    season_podiums = sum(1 for r in season_results if r.get("position") in ("1", "2", "3"))
    season_poles = sum(1 for r in season_results if r.get("grid") == "1")
    season_dnfs = sum(1 for r in season_results if r.get("positionText") in ("R", "D", "W", "F", "N", "E", "EX"))

    # Season position from standings
    season_pos: int | str = 0
    if not standings_df.empty and "driverCode" in standings_df.columns:
        for row in standings_df.itertuples(index=False):
            row_code = getattr(row, "driverCode", "") or (getattr(row, "familyName", "")[:3].upper() if getattr(row, "familyName", "") else "")
            if str(row_code).upper() == driver_info.get("code", "").upper():
                season_pos = getattr(row, "position", 0)
                break

    # World championships
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
            "fastest_laps": 0,
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
    count = 0
    async with aiohttp.ClientSession() as session:
        for yr in seasons:
            for base in _ERGAST_BASES:
                try:
                    async with session.get(f"{base}/{yr}/driverStandings.json?limit=100") as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
                        if not lists:
                            continue
                        last_list = lists[-1]
                        standings = last_list.get("DriverStandings", [])
                        for ds in standings:
                            if str(ds.get("position", "")) == "1":
                                champ_id = ds.get("Driver", {}).get("driverId", "")
                                if champ_id and champ_id.lower() == driver_id.lower():
                                    count += 1
                                break
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
    "alfa_romeo": "alfa",
    "alfaromeo": "alfa",
    "sauber": "sauber",
    "stake_f1_team": "sauber",
    "stake_f1_team_kick_sauber": "sauber",
    "kick_sauber": "sauber",
    "williams_racing": "williams",
}


async def _get_constructor_drivers_fallback(
    session: aiohttp.ClientSession,
    cid: str,
    season: int,
    constructor_info: dict | None,
) -> list:
    """Фоллбэк: пилоты из driver standings или OpenF1, когда Ergast не вернул данных."""
    # 1. Пробуем driver standings за сезон (если есть данные)
    for ergast_base in _ERGAST_BASES:
        try:
            async with session.get(f"{ergast_base}/{season}/driverStandings.json?limit=50") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
                    if lists:
                        result = []
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

    # 2. Из результатов гонок
    for ergast_base in _ERGAST_BASES:
        try:
            async with session.get(f"{ergast_base}/{season}/constructors/{cid}/results.json?limit=100") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                    seen_driver_ids = set()
                    result = []
                    for race in races:
                        for res in race.get("Results", []):
                            dr = res.get("Driver", {})
                            did = dr.get("driverId", "")
                            if did and did not in seen_driver_ids:
                                seen_driver_ids.add(did)
                                nat = dr.get("nationality") or ""
                                result.append({
                                    "driverId": did,
                                    "code": dr.get("code", ""),
                                    "givenName": dr.get("givenName", ""),
                                    "familyName": dr.get("familyName", ""),
                                    "permanentNumber": str(dr.get("permanentNumber", "")) if dr.get("permanentNumber") else "",
                                    "nationality": str(nat).strip() if nat else "",
                                })
                    if result:
                        return result
        except Exception:
            pass

    # 3. OpenF1: ТОЛЬКО для текущего/будущего сезона (session_key=latest = нынешний состав)
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
            # Резолв code -> driverId и nationality из Ergast (пробуем обе базы)
            code_to_driver_id: dict[str, str] = {}
            code_to_nationality: dict[str, str] = {}
            for ergast_base in _ERGAST_BASES:
                try:
                    async with session.get(f"{ergast_base}/{season}/drivers.json?limit=50") as eresp:
                        if eresp.status == 200:
                            edata = await eresp.json()
                            for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                                c = (dr.get("code") or "").upper()
                                if c:
                                    code_to_driver_id[c] = dr.get("driverId", "")
                                    code_to_nationality[c] = dr.get("nationality", "")
                    async with session.get(f"{ergast_base}/drivers.json?limit=500") as eresp:
                        if eresp.status == 200:
                            edata = await eresp.json()
                            for dr in edata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                                c = (dr.get("code") or "").upper()
                                if c and c not in code_to_nationality:
                                    code_to_driver_id.setdefault(c, dr.get("driverId", ""))
                                    code_to_nationality[c] = dr.get("nationality", "")
                    break
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


# Ergast-подобные API (пробуем по очереди при сбоях)
_ERGAST_BASES = [
    "https://api.jolpi.ca/ergast/f1",
    "https://ergast.com/api/f1",
]


async def _fetch_json(session: aiohttp.ClientSession, url: str, timeout: float = 30.0) -> dict | None:
    """Запрос JSON с таймаутом. Возвращает None при ошибке."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logger.debug(f"Fetch failed for {url[:60]}...: {e}")
    return None


async def _try_bases(session: aiohttp.ClientSession, path: str) -> dict | None:
    """Пробует запрос к каждому API-base по очереди."""
    for base in _ERGAST_BASES:
        data = await _fetch_json(session, f"{base}{path}")
        if data:
            return data
    return None


# --- Вспомогательные загрузчики для конструкторов --- #

async def _fetch_constructor_season_results(session: aiohttp.ClientSession, cid: str, season: int) -> tuple[list, int]:
    """Загружает результаты конструктора за сезон. Возвращает (results, race_count)."""
    for base in _ERGAST_BASES:
        try:
            resp_data = await _fetch_json(session, f"{base}/{season}/constructors/{cid}/results.json?limit=100")
            if resp_data:
                races = resp_data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                results = []
                for race in races:
                    for res in race.get("Results", []):
                        results.append({
                            "season": race.get("season"),
                            "position": res.get("position"),
                            "positionText": res.get("positionText", ""),
                            "points": float(res.get("points", 0)),
                            "grid": res.get("grid"),
                        })
                if results:
                    return results, len(races)
        except Exception:
            continue
    return [], 0


async def _fetch_constructor_career_results(session: aiohttp.ClientSession, cid: str) -> list:
    """Загружает все результаты карьеры конструктора."""
    for base in _ERGAST_BASES:
        try:
            offset = 0
            limit = 1000
            career = []
            while True:
                resp_data = await _fetch_json(session, f"{base}/constructors/{cid}/results.json?limit={limit}&offset={offset}")
                if not resp_data:
                    break
                mr = resp_data.get("MRData", {})
                total = int(mr.get("total", 0))
                for race in mr.get("RaceTable", {}).get("Races", []):
                    for res in race.get("Results", []):
                        career.append({
                            "season": race.get("season"),
                            "position": res.get("position"),
                            "positionText": res.get("positionText", ""),
                            "points": float(res.get("points", 0)),
                            "grid": res.get("grid"),
                        })
                offset += limit
                if offset >= total:
                    break
            if career:
                return career
        except Exception:
            continue
    return []


async def _fetch_constructor_drivers(session: aiohttp.ClientSession, cid: str, season: int, constructor_info: dict) -> list:
    """Загружает пилотов конструктора за сезон с fallback."""
    drivers = []
    for base in _ERGAST_BASES:
        ddata = await _fetch_json(session, f"{base}/{season}/constructors/{cid}/drivers.json")
        if ddata:
            for d in ddata.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                nat = d.get("nationality") or ""
                drivers.append({
                    "driverId": d.get("driverId"),
                    "code": d.get("code", ""),
                    "givenName": d.get("givenName", ""),
                    "familyName": d.get("familyName", ""),
                    "permanentNumber": str(d.get("permanentNumber", "")) if d.get("permanentNumber") else "",
                    "nationality": str(nat).strip() if nat else "",
                })
            break
    if not drivers:
        drivers = await _get_constructor_drivers_fallback(session, cid, season, constructor_info)
    return drivers


async def _fill_drivers_headshots(session: aiohttp.ClientSession, season_drivers: list, season: int) -> None:
    """Дополняет пилотов headshot и nationality из OpenF1 (только для сезонов >= 2023)."""
    if not season_drivers or season < 2023:
        for sd in season_drivers:
            sd.setdefault("headshot_url", "")
        return

    def _apply(drivers_o: list) -> None:
        for sd in season_drivers:
            code = sd.get("code", "").upper()
            for d in drivers_o:
                if d.get("name_acronym", "").upper() == code:
                    url = d.get("headshot_url") or ""
                    if url and not sd.get("headshot_url"):
                        sd["headshot_url"] = url
                    if not sd.get("nationality"):
                        cc = (d.get("country_code") or "").upper()
                        if cc and cc in COUNTRY_CODE_TO_NATIONALITY:
                            sd["nationality"] = COUNTRY_CODE_TO_NATIONALITY[cc]
                    break

    try:
        async with session.get(
            "https://api.openf1.org/v1/drivers?session_key=latest",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as oresp:
            if oresp.status == 200:
                _apply(await oresp.json())
        missing = any(not sd.get("headshot_url") or not sd.get("nationality") for sd in season_drivers)
        if missing:
            async with session.get(
                "https://api.openf1.org/v1/drivers",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as oresp2:
                if oresp2.status == 200:
                    _apply(await oresp2.json())
    except Exception:
        pass

    # Nationality fallback из Ergast
    missing_nat = [sd for sd in season_drivers if not (sd.get("nationality") or "").strip()]
    if missing_nat:
        for base in _ERGAST_BASES:
            try:
                data = await _fetch_json(session, f"{base}/drivers.json?limit=500")
                if data:
                    code_to_nat = {}
                    for dr in data.get("MRData", {}).get("DriverTable", {}).get("Drivers", []):
                        c = (dr.get("code") or "").upper()
                        n = (dr.get("nationality") or "").strip()
                        if c and n:
                            code_to_nat[c] = n
                    for sd in missing_nat:
                        sd["nationality"] = code_to_nat.get((sd.get("code") or "").upper(), "")
                    break
            except Exception:
                continue

    for sd in season_drivers:
        sd.setdefault("headshot_url", "")
        sd["nationality"] = (sd.get("nationality") or "").strip()


# --- КАРТОЧКА КОНСТРУКТОРА --- #
@cache_result(ttl=3600, key_prefix="constructor_details_v11")
async def get_constructor_details_async(constructor_id: str, season: int):
    """Профиль команды: название, лого, статистика сезона и карьеры, биография."""
    cid = constructor_id.strip().lower().replace(" ", "_")
    cid = CONSTRUCTOR_ID_MAP.get(cid, cid)

    async with aiohttp.ClientSession() as session:
        # 1. Конструктор (обязательно первым)
        data = await _try_bases(session, f"/constructors/{cid}.json")
        constructor_info = None
        if data:
            constructors = data.get("MRData", {}).get("ConstructorTable", {}).get("Constructors", [])
            if constructors:
                constructor_info = constructors[0]
        if not constructor_info:
            return None

        wiki_url = constructor_info.get("url", "")

        # 2. Параллельная загрузка: сезон, карьера, пилоты, биография, standings
        (
            (season_results, season_race_count),
            career_results,
            season_drivers,
            bio,
            standings_df,
        ) = await asyncio.gather(
            _fetch_constructor_season_results(session, cid, season),
            _fetch_constructor_career_results(session, cid),
            _fetch_constructor_drivers(session, cid, season, constructor_info),
            _fetch_wiki_bio(session, wiki_url),
            get_constructor_standings_async(season),
        )

        # Если season_results пусто — извлечём из career_results
        if not season_results and career_results:
            season_results = [r for r in career_results if r.get("season") == str(season)]

        # 3. Дополнение headshot/nationality (зависит от season_drivers)
        await _fill_drivers_headshots(session, season_drivers, season)

    # Career stats
    gp_entered = len(career_results)
    career_points = sum(r["points"] for r in career_results)
    podiums = sum(1 for r in career_results if r.get("position") in ("1", "2", "3"))
    poles = sum(1 for r in career_results if r.get("grid") == "1")

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
            "grand_prix_races": season_race_count if season_race_count else len(season_results),
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
