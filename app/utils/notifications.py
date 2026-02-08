import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot

from app.db import (
    get_all_users_with_favorites,
    get_last_reminded_round,
    set_last_reminded_round,
)
from app.f1_data import get_season_schedule_short_async
from app.utils.safe_send import safe_send_message

logger = logging.getLogger(__name__)
ADMIN_ID = 2099386


# --- ХЕЛПЕРЫ ---

def get_next_race_to_notify(schedule: list[dict]) -> Optional[dict]:
    """Ищет гонку, которая начнется через ~24 часа."""
    now = datetime.now(timezone.utc)

    # ЛОГ: Показываем текущее время сервера, чтобы проверить часовой пояс
    logger.info(f"Checking races at {now} UTC")

    for r in schedule:
        try:
            if not r.get("race_start_utc"): continue

            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None:
                race_dt = race_dt.replace(tzinfo=timezone.utc)

            diff = race_dt - now
            hours_left = diff.total_seconds() / 3600

            # ЛОГ: Раскомментируйте, если хотите видеть часы до каждой гонки
            logger.info(f"Race {r['event_name']}: {hours_left:.1f} hours left")

            # Условие уведомления (за сутки, проверяем интервал)
            if 23 <= hours_left <= 10000000:
                return r
        except Exception:
            continue
    return None


def build_notification_text(race: dict) -> str:
    """Генерирует стандартный текст уведомления."""
    flag = "🏁"
    return (
        f"🏎️ <b>Напоминание!</b>\n\n"
        f"Уже завтра состоится гонка: <b>{race.get('event_name', 'Гран-при')}</b> {flag}!\n"
        f"📍 Трасса: {race.get('location', '')}\n"
        f"⏰ Не пропустите!"
    )


# --- ОСНОВНАЯ ФУНКЦИЯ РАССЫЛКИ ---

async def check_and_send_notifications(bot: Bot):
    season = datetime.now(timezone.utc).year

    # ЛОГ: Начало проверки
    logger.info(f"🔍 Starting scheduled check for season {season}...")

    schedule = await get_season_schedule_short_async(season)

    if not schedule:
        logger.warning(f"⚠️ Schedule is empty for season {season}!")
        return

    # 1. Ищем гонку
    target_race = get_next_race_to_notify(schedule)

    if not target_race:
        # ВАЖНО: Если гонки нет, мы просто тихо выходим.
        # Можно добавить лог уровня DEBUG, чтобы не спамить в INFO
        logger.info("💤 No upcoming races in the notification window (23-25h).")
        return

    round_num = target_race["round"]
    race_name = target_race.get('event_name', 'Unknown GP')

    # 2. Проверка дублей
    last_reminded = await get_last_reminded_round(season)
    if last_reminded == round_num:
        logger.info(f"⏭️ Skipping notification for {race_name} (Round {round_num}): already reminded.")
        return

    # 3. Генерируем текст
    text = build_notification_text(target_race)

    # 4. Получаем пользователей
    try:
        users = await get_all_users_with_favorites()
    except Exception as e:
        logger.error(f"❌ DB Error: {e}")
        return

    logger.info(f"📢 FOUND RACE: {race_name}! Starting notification for {len(users)} users.")

    if not users:
        logger.warning("⚠️ No users found in database to notify.")
        await set_last_reminded_round(season, round_num)
        return

    # 5. Рассылка
    success_count = 0
    fail_count = 0

    # Уведомляем админа о старте
    await safe_send_message(bot, ADMIN_ID, f"🚀 Старт рассылки: {race_name}! Получателей: {len(users)}")

    for user_row in users:
        try:
            tg_id = user_row[0]  # user_row = (telegram_id, db_id)

            if await safe_send_message(bot, tg_id, text):
                success_count += 1
            else:
                fail_count += 1

            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1

    # 6. Записываем в БД
    await set_last_reminded_round(season, round_num)

    logger.info(f"✅ Notification finished. Success: {success_count}, Fail: {fail_count}")

    # 7. Отчет админу
    await safe_send_message(bot, ADMIN_ID,
                            f"📊 <b>Рассылка завершена</b>\n"
                            f"Гонка: {race_name}\n"
                            f"✅ Успешно: {success_count} | 🚫 Ошибок: {fail_count}"
                            )