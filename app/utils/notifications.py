import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from app.db import (
    db,
    get_all_users_with_favorites,
    get_last_reminded_round,
    set_last_reminded_round,
    get_last_notified_round,
    set_last_notified_round,
    get_last_notified_quali_round,
    set_last_notified_quali_round
)
from app.f1_data import (
    get_season_schedule_short_async,
    get_race_results_async,
    _get_latest_quali_async,
    get_testing_results_async
)
from app.utils.safe_send import safe_send_message

logger = logging.getLogger(__name__)
ADMIN_ID = 2099386


# --- ХЕЛПЕРЫ ОБЩИЕ ---

def format_time_left(minutes_left: int) -> str:
    if minutes_left >= 20 * 60: return "Уже завтра"
    hours = minutes_left // 60
    minutes = int(minutes_left % 60)
    parts = []
    if hours > 0: parts.append(f"{int(hours)} ч.")
    if minutes > 0: parts.append(f"{minutes} мин.")
    return f"Через {' '.join(parts)}"


def get_notification_text(race: dict, user_tz_name: str, minutes_left: int) -> str:
    """Генерирует текст для ГОНКИ."""
    event_name = race.get('event_name', 'Гран-при')
    try:
        race_utc = datetime.fromisoformat(race["race_start_utc"])
        if race_utc.tzinfo is None: race_utc = race_utc.replace(tzinfo=timezone.utc)
        user_tz = ZoneInfo(user_tz_name)
        start_time_str = race_utc.astimezone(user_tz).strftime("%H:%M")
    except:
        start_time_str = "??:??"

    return (
        f"🏎 <b>Скоро гонка!</b>\n\n"
        f"{format_time_left(minutes_left)} старт: <b>{event_name}</b> 🏁\n"
        f"📍 Трасса: {race.get('location', '')}\n"
        f"⏰ Начало в <b>{start_time_str}</b> (по вашему времени)\n"
    )


async def get_users_with_settings():
    if not db.conn: await db.connect()
    try:
        async with db.conn.execute("SELECT telegram_id, timezone, notify_before FROM users") as cursor:
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        return []


# --- ЗАДАЧА 1: АНОНСЫ (ГОНКИ И ТЕСТЫ) ---

async def check_and_send_notifications(bot: Bot):
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule: return

    now = datetime.now(timezone.utc)
    upcoming_event = []

    for r in schedule:
        if not r.get("race_start_utc"): continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
            minutes_left = (race_dt - now).total_seconds() / 60

            # Окно уведомления (от 0 до 30 часов)
            if 0 < minutes_left <= 30 * 60:
                upcoming_event.append((r, minutes_left))
        except:
            continue

    if not upcoming_event: return

    users = await get_users_with_settings()
    if not users: return

    scheduler_interval = 5
    half_window = scheduler_interval / 2 + 0.1

    sent_count = 0
    for user in users:
        try:
            tg_id = user[0]
            tz = user[1] or "Europe/Moscow"
            notify_min = user[2] or 1440

            for race, mins in upcoming_event:
                if abs(mins - notify_min) <= half_window:

                    # === ВОТ ТУТ ПРОВЕРКА НА ТЕСТЫ ===
                    if race.get("is_testing"):
                        text = (
                            f"🧪 <b>Предсезонные тесты!</b>\n\n"
                            f"Уже завтра: <b>{race.get('event_name')}</b>\n"
                            f"📍 Трасса: {race.get('location')}\n"
                            f"Не забудьте следить за результатами!"
                        )
                    else:
                        text = get_notification_text(race, tz, mins)
                    # =================================

                    if await safe_send_message(bot, tg_id, text):
                        sent_count += 1
                    await asyncio.sleep(0.05)
        except Exception:
            continue

    if sent_count > 0:
        logger.info(f"✅ Sent {sent_count} event reminders.")


# --- ЗАДАЧА 2: РЕЗУЛЬТАТЫ (ГОНКИ И ТЕСТЫ) ---

def build_results_text(race_name: str, favorites_results: list[dict]) -> str:
    lines = []
    for item in favorites_results:
        pos_str = f"P{item['pos']}"
        if item['pos'] == '1':
            pos_str = "🥇 P1"
        elif item['pos'] == '2':
            pos_str = "🥈 P2"
        elif item['pos'] == '3':
            pos_str = "🥉 P3"
        lines.append(f"<b>{item['code']}</b>: {pos_str} (+{item.get('points', 0)})")
    return f"🏁 <b>Финиш: {race_name}</b>\n\nВаши фавориты:\n" + "\n".join(lines)


async def check_and_send_results(bot: Bot):
    season = datetime.now(timezone.utc).year
    last_notified = await get_last_notified_round(season)
    schedule = await get_season_schedule_short_async(season)

    # Ищем последнюю завершенную
    now = datetime.now(timezone.utc)
    finished_event = None

    for r in schedule:
        if not r.get("race_start_utc"): continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
            # Считаем завершенным через 4 часа после старта (тесты идут долго)
            finish_offset = 9 if r.get("is_testing") else 2.5

            if now > race_dt + timedelta(hours=finish_offset):
                finished_event = r
            else:
                break
        except:
            continue

    if not finished_event: return
    round_num = finished_event["round"]

    if last_notified and last_notified >= round_num: return

    # === ЛОГИКА ДЛЯ ТЕСТОВ ===
    if finished_event.get("is_testing"):
        # Для тестов рассылаем ТОП-3 всем
        logger.info(f"🧪 Checking testing results for {finished_event['event_name']}...")
        df, day_name = await get_testing_results_async(season, round_num)

        if df.empty: return

        # Формируем текст Топ-3
        top3 = df.head(3)
        lines = []
        for i, row in top3.iterrows():
            driver = row.get('Abbreviation', '???')
            time = str(row.get('Time', '-'))
            if "days" in time: time = time.split("days")[-1].strip()
            if "." in time: time = time[:-3]

            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
            lines.append(f"{medal} <b>{driver}</b>: {time}")

        text = (
                f"🧪 <b>Итоги тестов: {day_name}</b>\n"
                f"{finished_event['event_name']}\n\n"
                + "\n".join(lines) +
                "\n\n📊 Подробности: /next_race"
        )

        # Рассылаем всем активным пользователям (или тем кто с настройками)
        users = await get_users_with_settings()
        sent_count = 0
        for user in users:
            if await safe_send_message(bot, user[0], text):
                sent_count += 1
            await asyncio.sleep(0.05)

        await set_last_notified_round(season, round_num)
        return

    # === ЛОГИКА ДЛЯ ГОНОК (Обычная) ===
    results_df = await get_race_results_async(season, round_num)
    if results_df.empty: return

    users_favorites = await get_all_users_with_favorites()
    if not users_favorites:
        await set_last_notified_round(season, round_num)
        return

    user_map = {}
    for row in users_favorites:
        tg_id, drv = row[0], row[1]
        if tg_id not in user_map: user_map[tg_id] = []
        user_map[tg_id].append(str(drv).upper())

    res_map = {}
    for _, row in results_df.iterrows():
        code = str(row.get('Abbreviation', '')).upper()
        res_map[code] = {'pos': str(row.get('Position', 'DNF')), 'points': row.get('Points', 0)}

    sent_count = 0
    for tg_id, favs in user_map.items():
        my_res = []
        for code in favs:
            if code in res_map:
                my_res.append({'code': code, **res_map[code]})

        if my_res:
            text = build_results_text(finished_event['event_name'], my_res)
            if await safe_send_message(bot, tg_id, text):
                sent_count += 1
            await asyncio.sleep(0.05)

    await set_last_notified_round(season, round_num)


# --- ЗАДАЧА 3: РЕЗУЛЬТАТЫ КВАЛИФИКАЦИИ ---

async def check_and_notify_quali(bot: Bot) -> None:
    season = datetime.now(timezone.utc).year
    data = await _get_latest_quali_async(season)
    if not data or data[0] is None: return

    round_num, results = data
    last_notified = await get_last_notified_quali_round(season)
    if last_notified is not None and last_notified >= round_num: return

    users_favorites = await get_all_users_with_favorites()
    if not users_favorites:
        await set_last_notified_quali_round(season, round_num)
        return

    user_map = {}
    for row in users_favorites:
        tg_id, code = row[0], row[1]
        if tg_id not in user_map: user_map[tg_id] = []
        user_map[tg_id].append(str(code).upper())

    quali_map = {}
    for row in results:
        code = str(row.get('driver', '')).upper()
        quali_map[code] = row

    sent_count = 0
    for tg_id, fav_drivers in user_map.items():
        lines = []
        for fav in fav_drivers:
            if fav in quali_map:
                row = quali_map[fav]
                best_time = row.get('best', '-')
                pos = row.get('position', '?')
                lines.append(f"⏱ <b>{fav}</b>: P{pos} ({best_time})")

        if lines:
            text = f"🏁 <b>Квалификация (Этап {round_num})</b>\n\n" + "\n".join(lines)
            if await safe_send_message(bot, tg_id, text):
                sent_count += 1
            await asyncio.sleep(0.05)

    await set_last_notified_quali_round(season, round_num)