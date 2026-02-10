import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from app.db import (
    db,  # Прямой доступ для настроек
    get_all_users_with_favorites,
    get_last_reminded_round,
    set_last_reminded_round,
    get_last_notified_round,  # Нужно убедиться, что эти функции есть в db.py
    set_last_notified_round
)
from app.f1_data import get_season_schedule_short_async, get_race_results_async
from app.utils.safe_send import safe_send_message

logger = logging.getLogger(__name__)
ADMIN_ID = 2099386


# --- ХЕЛПЕРЫ ДЛЯ АНОНСОВ (PRE-RACE) ---

def format_time_left(minutes_left: int) -> str:
    """Формирует строку 'Через X ч. Y мин.'."""
    if minutes_left >= 20 * 60: return "Уже завтра"
    hours = minutes_left // 60
    minutes = int(minutes_left % 60)
    parts = []
    if hours > 0: parts.append(f"{int(hours)} ч.")
    if minutes > 0: parts.append(f"{minutes} мин.")
    return f"Через {' '.join(parts)}"


def get_notification_text(race: dict, user_tz_name: str, minutes_left: int) -> str:
    """Текст анонса перед гонкой."""
    event_name = race.get('event_name', 'Гран-при')
    try:
        race_utc = datetime.fromisoformat(race["race_start_utc"])
        if race_utc.tzinfo is None: race_utc = race_utc.replace(tzinfo=timezone.utc)
        user_tz = ZoneInfo(user_tz_name)
        start_time_str = race_utc.astimezone(user_tz).strftime("%H:%M")
    except:
        start_time_str = "??:??"

    return (
        f"🏎️ <b>Скоро гонка!</b>\n\n"
        f"{format_time_left(minutes_left)} старт: <b>{event_name}</b> 🏁\n"
        f"📍 Трасса: {race.get('location', '')}\n"
        f"⏰ Начало в <b>{start_time_str}</b> (по вашему времени)\n"
    )


async def get_users_with_settings():
    """Получает настройки времени уведомлений (для анонсов)."""
    if not db.conn: await db.connect()
    try:
        async with db.conn.execute("SELECT telegram_id, timezone, notify_before FROM users") as cursor:
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        return []


# --- ХЕЛПЕРЫ ДЛЯ РЕЗУЛЬТАТОВ (POST-RACE) ---

def format_position_emoji(pos_text) -> str:
    """Добавляет эмодзи к позиции."""
    try:
        pos = int(pos_text)
        if pos == 1: return "🥇 P1"
        if pos == 2: return "🥈 P2"
        if pos == 3: return "🥉 P3"
        return f"🏎 P{pos}"
    except:
        return f"❌ {pos_text}"  # DNF и т.д.


def build_results_text(race_name: str, favorites_results: list[dict]) -> str:
    """
    Строит текст с результатами ТОЛЬКО для избранных пилотов пользователя.
    favorites_results: [{'code': 'VER', 'pos': '1', 'points': 25}, ...]
    """
    lines = []
    for item in favorites_results:
        pos_str = format_position_emoji(item['pos'])
        lines.append(f"<b>{item['code']}</b>: {pos_str} (+{item.get('points', 0)})")

    results_block = "\n".join(lines)

    return (
        f"🏁 <b>Финиш: {race_name}</b>\n\n"
        f"Ваши фавориты:\n"
        f"{results_block}\n\n"
        f"📊 Подробности: /drivers"
    )


# --- ЗАДАЧА 1: АНОНСЫ (PRE-RACE) ---

async def check_and_send_notifications(bot: Bot):
    """Проверяет, скоро ли гонка, и шлет анонсы."""
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule: return

    now = datetime.now(timezone.utc)
    upcoming_races = []

    for r in schedule:
        if not r.get("race_start_utc"): continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
            minutes_left = (race_dt - now).total_seconds() / 60
            if 0 < minutes_left <= 30 * 60:  # Окно 30 часов
                upcoming_races.append((r, minutes_left))
        except:
            continue

    if not upcoming_races: return

    users = await get_users_with_settings()
    if not users: return

    # Интервал проверки шедулера (настройте в main.py, например 5 мин)
    scheduler_interval = 5
    half_window = scheduler_interval / 2 + 0.1

    sent_count = 0
    for user in users:
        try:
            tg_id = user[0]  # telegram_id
            tz = user[1] or "Europe/Moscow"
            notify_min = user[2] or 1440

            for race, mins in upcoming_races:
                if abs(mins - notify_min) <= half_window:
                    text = get_notification_text(race, tz, mins)
                    if await safe_send_message(bot, tg_id, text):
                        sent_count += 1
                    await asyncio.sleep(0.05)
        except Exception:
            continue

    if sent_count > 0:
        logger.info(f"✅ Sent {sent_count} race reminders.")


# --- ЗАДАЧА 2: РЕЗУЛЬТАТЫ (POST-RACE) ---

async def check_and_send_results(bot: Bot):
    """
    Проверяет прошедшие гонки. Если появились результаты и мы о них еще не писали
    — рассылает уведомления тем, у кого эти пилоты в избранном.
    """
    season = datetime.now(timezone.utc).year

    # 1. Проверяем, какую гонку мы обрабатывали последней
    last_notified_round = await get_last_notified_round(season)

    # 2. Ищем ПОСЛЕДНЮЮ ЗАВЕРШЕННУЮ гонку в календаре
    schedule = await get_season_schedule_short_async(season)
    now = datetime.now(timezone.utc)

    finished_race = None
    for r in schedule:
        if not r.get("race_start_utc"): continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)

            # ВАЖНО: Проверяем, что гонка реально закончилась (прошло 2 часа после старта)
            if now > race_dt + timedelta(hours=2):
                finished_race = r  # Запоминаем как кандидата
            else:
                # Если мы дошли до будущей гонки - прерываем цикл, дальше тоже будущее
                break
        except:
            continue

    if not finished_race:
        return  # Гонок еще не было

    round_num = finished_race["round"]

    # Если мы уже рассылали результаты этой гонки — выходим
    if last_notified_round and last_notified_round >= round_num:
        return

    # 3. Пробуем скачать результаты
    logger.info(f"🏁 Checking results for Round {round_num} ({finished_race['event_name']})...")

    results_df = await get_race_results_async(season, round_num)

    if results_df.empty:
        # Результатов еще нет в API (нормально, ждем следующего цикла)
        return

    # 4. Результаты есть! Готовим рассылку.
    logger.info(f"✅ Results found! Preparing notifications...")

    # Получаем избранное всех пользователей: [(tg_id, 'VER'), (tg_id, 'HAM'), ...]
    # Или словарь {tg_id: ['VER', 'HAM']}
    # Функция get_all_users_with_favorites возвращает список всех записей (user_id, driver_code)
    # Нам нужно сгруппировать их

    users_favorites = await get_all_users_with_favorites()  # [(tg_id, driver_code), ...]

    if not users_favorites:
        await set_last_notified_round(season, round_num)
        return

    # Группируем: {12345: ['VER', 'HAM'], 67890: ['LEC']}
    user_map = {}
    for row in users_favorites:
        # Предполагаем row = (telegram_id, driver_code) или объект
        # Адаптируйте индексы под ваш SQL запрос в db.py!
        tg_id = row[0]
        drv_code = row[1]

        if tg_id not in user_map: user_map[tg_id] = []
        user_map[tg_id].append(drv_code)

    sent_count = 0

    # Нормализуем DataFrame для поиска (Driver code -> Position)
    # Создаем словарь: {'VER': {'pos': '1', 'points': 25}, 'HAM': ...}
    race_res_map = {}
    for _, row in results_df.iterrows():
        # FastF1 использует Abbreviation
        code = str(row.get('Abbreviation', '')).upper()
        pos = str(row.get('Position', 'DNF'))
        pts = row.get('Points', 0)

        race_res_map[code] = {'pos': pos, 'points': pts}

    # 5. Рассылаем
    for tg_id, favorites in user_map.items():
        # Собираем результаты конкретно для этого юзера
        my_results = []
        for fav_code in favorites:
            # Ищем фаворита в результатах гонки
            # Иногда код в базе (Lec) отличается от API (LEC). Делаем upper()
            fav_code = str(fav_code).upper()

            if fav_code in race_res_map:
                res = race_res_map[fav_code]
                my_results.append({
                    'code': fav_code,
                    'pos': res['pos'],
                    'points': res['points']
                })

        if my_results:
            # Есть о чем сообщить!
            text = build_results_text(finished_race['event_name'], my_results)
            if await safe_send_message(bot, tg_id, text):
                sent_count += 1
            await asyncio.sleep(0.05)

    # 6. Фиксируем, что результаты отправлены
    await set_last_notified_round(season, round_num)

    await safe_send_message(bot, ADMIN_ID,
                            f"📊 <b>Результаты разосланы!</b>\n"
                            f"Гонка: {finished_race['event_name']}\n"
                            f"Получателей: {sent_count}"
                            )