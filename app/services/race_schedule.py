"""Shared next-race presentation for the web and Telegram adapters."""
import asyncio
from datetime import datetime, date, timezone, timedelta

from app.db import get_user_settings
from app.f1_data import get_season_schedule_short_async, get_season_schedule_short
from app.utils.time_tools import format_race_time


def _parse_utc_iso(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except (ValueError, TypeError):
        return None


async def build_next_race_payload(season: int | None = None, user_id: int | None = None) -> dict:
    """
    Возвращает инфу о ближайшей гонке.
    Добавляет поле fmt_date для сайта.
    """
    if season is None:
        season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"status": "no_schedule", "season": season}

    now_utc = datetime.now(timezone.utc)

    def _race_anchor_utc(race: dict) -> datetime | None:
        race_start = _parse_utc_iso(race.get("race_start_utc"))
        if race_start is not None:
            return race_start
        try:
            race_day = date.fromisoformat(str(race.get("date") or ""))
            return datetime.combine(race_day, datetime.max.time(), tzinfo=timezone.utc)
        except Exception:
            return None

    def _select_future_races(items: list[dict]) -> list[dict]:
        # Считаем этап "актуальным", если старт гонки ещё впереди
        # или завершился совсем недавно (буфер 6 часов).
        grace_window_start = now_utc - timedelta(hours=6)
        schedule_sorted = sorted(items, key=lambda x: int(x.get("round", 0) or 0))
        result: list[dict] = []
        for race in schedule_sorted:
            anchor = _race_anchor_utc(race)
            if anchor is not None and anchor >= grace_window_start:
                result.append(race)
        return result

    future_races = _select_future_races(schedule)

    # Защита от "застывшего" кеша расписания: если внезапно "сезон завершен",
    # пробуем один раз взять свежее расписание напрямую (без async-cache).
    if not future_races and season >= now_utc.year:
        fresh_schedule = await asyncio.to_thread(get_season_schedule_short, season)
        if fresh_schedule:
            future_races = _select_future_races(fresh_schedule)

    if not future_races:
        return {"status": "season_finished", "season": season}

    r = future_races[0]
    race_start_utc_str = r.get("race_start_utc")

    local_str = None
    utc_str = None

    if race_start_utc_str:
        user_tz = "Europe/Moscow"
        if user_id:
            s = await get_user_settings(user_id)
            user_tz = s.get("timezone", "Europe/Moscow")

        # Для БОТА: Красивая строка с месяцем (8 марта...)
        local_str = format_race_time(race_start_utc_str, user_tz)
        try:
            utc_dt = datetime.fromisoformat(race_start_utc_str)
            utc_str = utc_dt.strftime("%d.%m.%Y %H:%M UTC")
        except:
            utc_str = race_start_utc_str

    return {
        "status": "ok", "season": season, "round": r["round"],
        "event_name": r["event_name"], "country": r["country"], "location": r["location"],
        "date": r["date"], "utc": utc_str,
        "race_start_utc": race_start_utc_str,
        "is_cancelled": bool(r.get("is_cancelled", False)),
        "local": local_str,  # Оставляем для бота
        "fmt_date": r.get("local")
    }
