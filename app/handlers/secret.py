import logging
from datetime import datetime, timezone
from aiogram import Router, types
from aiogram.filters import Command

from app.f1_data import get_season_schedule_short_async
from app.db import get_all_users_with_favorites
# Импортируем наши новые хелперы
from app.utils.notifications import build_notification_text, check_and_send_notifications

logger = logging.getLogger(__name__)
router = Router()

ADMINS = [2099386]


@router.message(Command("check_broadcast"))
async def cmd_check_broadcast(message: types.Message):
    """
    Проверяет состояние базы и формат рассылки (Dry Run).
    Не отправляет ничего пользователям!
    """
    if message.from_user.id not in ADMINS:
        return

    status_msg = await message.answer("🕵️‍♂️ Анализирую базу данных и расписание...")

    # 1. Проверка пользователей
    try:
        users = await get_all_users_with_favorites()
        users_count = len(users)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка подключения к БД: {e}")
        return

    # 2. Проверка расписания и генерация текста
    season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)

    # Ищем БЛИЖАЙШУЮ гонку (любую будущую), просто чтобы показать пример текста
    example_race = None
    now = datetime.now().date()
    for r in schedule:
        if r.get("date"):
            try:
                if datetime.strptime(r["date"], "%Y-%m-%d").date() >= now:
                    example_race = r
                    break
            except:
                pass

    # Если сезон закончился
    if not example_race and schedule:
        example_race = schedule[-1]

    if example_race:
        # Генерируем текст той же функцией, что и реальная рассылка!
        preview_text = build_notification_text(example_race)
    else:
        preview_text = "❌ Гонки не найдены."

    # 3. Отправляем отчет админу
    report = (
        f"📊 <b>Диагностика рассылки:</b>\n\n"
        f"👥 <b>Пользователей в базе:</b> {users_count}\n"
        f"<i>(Столько сообщений будет отправлено при массовой рассылке)</i>\n\n"
        f"📝 <b>Пример текста (для ближайшей гонки):</b>\n"
        f"👇👇👇\n\n"
        f"{preview_text}"
    )

    await status_msg.delete()
    await message.answer(report)


@router.message(Command("force_notify_all"))
async def cmd_force_notify(message: types.Message, bot):
    """Настоящая рассылка (ОПАСНО!)"""
    if message.from_user.id not in ADMINS: return
    await message.answer("🚀 Запускаю боевую рассылку...")
    await check_and_send_notifications(bot)