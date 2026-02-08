import logging
from aiogram import Router, types
from aiogram.filters import Command
from datetime import datetime, timezone

from app.f1_data import get_season_schedule_short_async
from app.utils.notifications import check_and_send_notifications

# Настройка логгера
logger = logging.getLogger(__name__)
router = Router()

# Список ID админов
ADMINS = [2099386]  # Ваш ID


@router.message(Command("test_notify"))
async def cmd_test_notify(message: types.Message):
    """
    Тестирует формат уведомления.
    Отправляет пример уведомления о ближайшей гонке (или фейковой) только админу.
    """
    if message.from_user.id not in ADMINS:
        return

    await message.answer("🔄 Генерирую тестовое уведомление...")

    try:
        season = datetime.now().year
        schedule = await get_season_schedule_short_async(season)

        # 1. Ищем ближайшую будущую гонку для примера
        target_race = None
        now = datetime.now().date()

        # Сначала ищем в будущем
        for r in schedule:
            if r.get("date"):
                try:
                    r_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
                    if r_date >= now:
                        target_race = r
                        break
                except:
                    pass

        # Если сезон кончился, берем последнюю гонку сезона для теста
        if not target_race and schedule:
            target_race = schedule[-1]

        if not target_race:
            await message.answer("❌ Не удалось найти гонки для теста.")
            return

        # 2. Формируем ТЕКСТ (точно такой же, как в notifications.py)
        flag = "🏁"
        event_name = target_race.get('event_name', 'Гран-при')
        location = target_race.get('location', 'Трасса')

        text = (
            f"🏎️ <b>Напоминание!</b>\n\n"
            f"Уже завтра состоится гонка: <b>{event_name}</b> {flag}!\n"
            f"📍 Трасса: {location}\n"
            f"⏰ Не пропустите!"
        )

        # 3. Отправляем текст
        await message.answer(text)
        await message.answer("✅ Тест завершен. Это точная копия текста рассылки.")

    except Exception as e:
        logger.exception("Test notify failed")
        await message.answer(f"❌ Ошибка при тесте: {e}")


@router.message(Command("force_notify_all"))
async def cmd_force_notify_all(message: types.Message, bot: types.Bot):
    """
    ОПАСНО: Принудительный запуск массовой рассылки всем пользователям.
    Только если вы уверены, что хотите это сделать прямо сейчас.
    """
    if message.from_user.id not in ADMINS:
        return

    await message.answer("🚀 Запускаю принудительную проверку и рассылку...")

    # Вызываем реальную функцию рассылки
    await check_and_send_notifications(bot)

    await message.answer("🏁 Процесс рассылки запущен (см. логи и отчет).")