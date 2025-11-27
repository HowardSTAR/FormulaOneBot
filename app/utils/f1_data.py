import asyncio
import functools
import logging
import pathlib
from datetime import date as _date, timezone, timedelta, datetime, date
from functools import partial
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
    Синхронно получаем результаты квалификации через FastF1.

    Если данных ещё нет (SessionNotAvailableError или пустой session.results),
    возвращаем пустой список, НИЧЕГО не бросаем наружу.
    """
    logging.info("[QUALI] Загружаю квалификацию season=%s, round=%s", season, round_number)

    try:
        session = fastf1.get_session(season, round_number, "Q")
    except Exception as exc:  # noqa: BLE001
        logging.exception(
            "[QUALI] Не удалось создать сессию FastF1 (season=%s, round=%s): %s",
            season, round_number, exc,
        )
        return []

    try:
        # без телеметрии, чтобы не тянуть тонну лишних данных
        session.load(
            telemetry=False,
            laps=False,
            weather=False,
            messages=False,
        )
    except SessionNotAvailableError as exc:
        logging.info(
            "[QUALI] Данных по квалификации нет (SessionNotAvailableError) "
            "season=%s, round=%s: %s",
            season, round_number, exc,
        )
        return []
    except Exception as exc:  # noqa: BLE001
        logging.exception(
            "[QUALI] Ошибка при загрузке сессии квалификации season=%s, round=%s: %s",
            season, round_number, exc,
        )
        return []

    results = getattr(session, "results", None)
    if results is None or results.empty:
        logging.info(
            "[QUALI] В session.results нет данных (season=%s, round=%s)",
            season, round_number,
        )
        return []

    # сортируем по позиции и собираем в удобный список словарей
    df = results
    if "Position" in df.columns:
        df = df.sort_values("Position")

    rows: list[dict] = []
    for _, row in df.head(limit).iterrows():
        pos = row.get("Position")
        if pos is None:
            continue

        try:
            pos_int = int(pos)
        except (TypeError, ValueError):
            continue

        code = row.get("Abbreviation") or row.get("DriverNumber") or "?"
        team = row.get("TeamName") or ""

        # лучшая попытка: Q3 > Q2 > Q1
        best_lap = row.get("Q3") or row.get("Q2") or row.get("Q1") or ""

        rows.append(
            {
                "position": pos_int,
                "driver": str(code),
                "team": str(team),
                "best": str(best_lap) if best_lap else "",
            }
        )

    logging.info(
        "[QUALI] Успешно получили %s результатов квалификации (season=%s, round=%s)",
        len(rows), season, round_number,
    )
    return rows


async def _get_quali_async(season: int, round_number: int, limit: int = 20) -> list[dict]:
    """
    Асинхронная обёртка над get_qualifying_results, чтобы не блокировать event-loop.
    """
    loop = asyncio.get_running_loop()
    func = functools.partial(get_qualifying_results, season, round_number, limit)
    return await loop.run_in_executor(None, func)


def get_latest_quali_results(season: int, max_round: int | None = None, limit: int = 20) -> tuple[int | None, list[dict]]:
    """
    Найти последнюю квалификацию сезона, по которой есть результаты.

    Возвращает (round_number, results). Если данных нет — (None, []).

    max_round — необязательный верхний предел по номеру этапа
    (например, чтобы не искать дальше будущих этапов).
    """
    log = logging.getLogger(__name__)

    schedule = get_season_schedule_short(season)
    if not schedule:
        return None, []

    # Все этапы сезона
    rounds = sorted({r["round"] for r in schedule})
    # Ограничиваем сверху, если нужно
    if max_round is not None:
        rounds = [rn for rn in rounds if rn <= max_round]

    # Сначала смотрим только завершившиеся этапы (по дате гонки)
    today = _date.today()
    completed_rounds: list[int] = []
    for rn in rounds:
        try:
            item = next(r for r in schedule if r["round"] == rn)
        except StopIteration:
            continue

        try:
            race_date = _date.fromisoformat(item["date"])
        except Exception:  # noqa: BLE001
            race_date = today

        if race_date <= today:
            completed_rounds.append(rn)

    # Ищем с конца (последняя прошедшая квалификация)
    for rn in sorted(completed_rounds, reverse=True):
        try:
            res = get_qualifying_results(season, rn, limit=limit)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "[QUALI] Не удалось загрузить квалификацию season=%s round=%s: %s",
                season,
                rn,
                exc,
            )
            continue

        if res:
            return rn, res

    return None, []


async def _get_latest_quali_async(season: int, max_round: int | None = None, limit: int = 20) -> tuple[int | None, list[dict]]:
    """
    Ищем ПОСЛЕДНЮЮ прошедшую квалификацию в сезоне.

    max_round — верхняя граница по номеру этапа (например, если нажали
    кнопку на конкретном этапе — не лезем дальше него).

    Возвращает (round_number, results_list) или (None, []).
    """
    schedule = get_season_schedule_short(season)
    if not schedule:
        logging.info("[QUALI] Нет расписания для сезона %s", season)
        return None, []

    today = date.today()

    # Берём только этапы:
    #  - дата <= сегодня (уже прошли)
    #  - номер <= max_round (если ограничение указано)
    candidates = []
    for r in schedule:
        rnd = r["round"]
        if max_round is not None and rnd > max_round:
            continue

        try:
            race_date = date.fromisoformat(r["date"])
        except Exception:  # noqa: BLE001
            continue

        if race_date > today:
            continue

        candidates.append(r)

    if not candidates:
        logging.info(
            "[QUALI] Нет прошедших этапов для поиска квалификации "
            "(season=%s, max_round=%s)",
            season, max_round,
        )
        return None, []

    # Идём от последнего к первому
    candidates.sort(key=lambda r: r["round"], reverse=True)

    for r in candidates:
        rnd = r["round"]
        logging.info(
            "[QUALI] Пробую взять квалификацию для season=%s, round=%s",
            season, rnd,
        )
        results = await _get_quali_async(season, rnd, limit=limit)
        if results:
            logging.info(
                "[QUALI] Нашли квалификацию для season=%s, round=%s (записей=%s)",
                season, rnd, len(results),
            )
            return rnd, results

    logging.info(
        "[QUALI] Не нашли ни одной квалификации с данными (season=%s, max_round=%s)",
        season, max_round,
    )
    return None, []


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
