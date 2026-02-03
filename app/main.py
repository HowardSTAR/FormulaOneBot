import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot import create_bot_and_dispatcher
from app.config import get_settings
from app.db import db
from app.f1_data import init_redis_cache, warmup_cache
from app.handlers import secret, start, races, drivers, teams, favorites, settings, compare
from app.middlewares.error_logging import ErrorLoggingMiddleware
from app.utils.backup import create_backup
from app.utils.notifications import check_and_notify_favorites, remind_next_race, check_and_notify_quali

# Базовая настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def on_startup(bot: Bot):
    settings = get_settings()

    # 1. Подключаем БД (из предыдущего шага)
    await db.connect()
    await db.init_tables()

    # 2. Инициализируем Redis кэш для FastF1
    if settings.bot.redis_url:
        await init_redis_cache(settings.bot.redis_url)

    # 3. Запускаем прогрев в фоне (чтобы бот сразу ответил на /start, а кэш грелся параллельно)
    asyncio.create_task(warmup_cache())

    # ... здесь может быть запуск шедулера уведомлений ...
    logging.info("Bot started, DB connected.")


async def on_shutdown(bot: Bot):
    # Закрываем соединение аккуратно
    await db.close()
    logging.info("Bot stopped, DB closed.")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot, dp = create_bot_and_dispatcher()

    # Регистрируем хуки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    scheduler = AsyncIOScheduler()

    scheduler.add_job(create_backup, 'interval', hours=24)
    scheduler.start()

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
        # compare.router,
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
        warmup_cache,
        "interval",
        hours=1,
        max_instances=1,
        coalesce=True,
        id="warmup_sessions",
        replace_existing=True,
    )
    scheduler.start()

    asyncio.create_task(warmup_cache())

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

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")