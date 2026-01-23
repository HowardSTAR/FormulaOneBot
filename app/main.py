import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot import create_bot_and_dispatcher
from app.db import init_db
from app.f1_data import warmup_current_season_sessions
from app.handlers import secret, start, races, drivers, teams, favorites, settings, compare
from app.middlewares.error_logging import ErrorLoggingMiddleware
from app.utils.backup import create_backup
from app.utils.notifications import check_and_notify_favorites, remind_next_race, check_and_notify_quali

# Базовая настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scheduler = AsyncIOScheduler()

    scheduler.add_job(create_backup, 'interval', hours=24)
    scheduler.start()

    await init_db()

    bot, dp = create_bot_and_dispatcher()
    dp.update.outer_middleware(ErrorLoggingMiddleware())

    # Регистрируем все роутеры
    dp.include_routers(
        start.router,
        races.router,
        drivers.router,
        teams.router,
        favorites.router,
        secret.router,
        settings.settings_router,
        # TODO сделать нормальное сравнение
        compare.router,
    )

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="UTC")
    # вместо "раз в день" делаем каждые 10 минут
    scheduler.add_job(
        check_and_notify_favorites,
        "interval",
        minutes=10,
        args=[bot],
        id="favorites_notifications",
        replace_existing=True,
    )

    # Напоминание за сутки до ближайшей гонки
    scheduler.add_job(
        remind_next_race,
        "interval",
        minutes=15,  # можно 15 или 60 — как хочешь
        args=[bot],
        id="next_race_reminder",
        replace_existing=True,
    )

    scheduler.add_job(
        check_and_notify_quali,
        "interval",
        minutes=5,  # можно 2–10, как тебе комфортно
        args=[bot],
        id="quali_notifications",
        replace_existing=True,
    )

    scheduler.add_job(
        warmup_current_season_sessions,
        "interval",
        hours=1,
        max_instances=1,
        coalesce=True,
        id="warmup_sessions",
        replace_existing=True,
    )
    scheduler.start()

    asyncio.create_task(warmup_current_season_sessions())

    try:
        await dp.start_polling(bot)
    except TelegramBadRequest as exc:
        logging.error(f"Ошибка Telegram API: {exc}", exc_info=True)
        raise
    except KeyboardInterrupt:
        logging.info("Остановка бота пользователем")
    finally:
        # Корректное закрытие планировщика и бота
        scheduler.shutdown(wait=False)
        try:
            await bot.session.close()
        except Exception as exc:
            logging.warning(f"Ошибка при закрытии сессии бота: {exc}")

    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")