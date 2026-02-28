import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot import create_bot_and_dispatcher
from app.config import get_settings
from app.db import db
from app.f1_data import init_redis_cache, warmup_cache
from app.handlers import start, races, drivers, teams, favorites, secret, settings, compare, feedback, groups
from app.middlewares.error_logging import ErrorLoggingMiddleware
from app.utils.backup import create_backup
from app.utils.notifications import (
    check_and_send_notifications,
    check_and_send_results,
    check_and_notify_quali,
    check_and_notify_voting_results,
)


# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
def setup_logging():
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "bot.log"

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    settings = get_settings()

    # 1. Подключаем БД и СОЗДАЕМ ТАБЛИЦЫ
    await db.connect()
    await db.init_tables()

    # 2. Инициализируем Redis кэш
    if settings.bot.redis_url:
        await init_redis_cache(settings.bot.redis_url)

    logger.info("Bot started, DB connected, tables initialized.")


async def on_shutdown(bot: Bot):
    await db.close()
    logger.info("Bot stopped, DB closed.")


async def main():
    bot, dp = create_bot_and_dispatcher()

    # 1. Регистрируем хуки (теперь они точно сработают!)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 2. Регистрируем мидлвари
    dp.update.outer_middleware(ErrorLoggingMiddleware())

    # 3. Регистрируем все роутеры
    dp.include_routers(
        groups.router,  # раньше start — для my_chat_member
        start.router,
        races.router,
        drivers.router,
        teams.router,
        favorites.router,
        secret.router,
        settings.settings_router,
        compare.router,
        feedback.router
    )

    # 4. Настраиваем ОДИН планировщик задач
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(create_backup, 'interval', hours=24)
    scheduler.add_job(
        check_and_send_notifications,
        "interval",
        seconds=30,
        args=[bot],
        id="notifications_job",
        replace_existing=True
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
    scheduler.add_job(
        check_and_send_results,
        "interval",
        minutes=15,
        args=[bot],
        id="results_job"
    )
    scheduler.add_job(
        check_and_notify_voting_results,
        "interval",
        minutes=60,
        args=[bot],
        id="voting_results_job",
    )
    scheduler.add_job(
        check_and_notify_quali,
        "interval",
        minutes=15,
        args=[bot],
        id="quali_results_job"
    )

    scheduler.start()

    # Запускаем прогрев кэша в фоне сразу при старте скрипта
    asyncio.create_task(warmup_cache())

    # 5. Сбрасываем старые апдейты (чтобы бот не обрабатывал клики, сделанные пока он лежал)
    await bot.delete_webhook(drop_pending_updates=True)

    # 6. Запускаем бота
    try:
        await dp.start_polling(bot)
    except TelegramBadRequest as exc:
        logger.error(f"Ошибка Telegram API: {exc}", exc_info=True)
        raise
    except KeyboardInterrupt:
        logger.info("Остановка бота пользователем")
    finally:
        # 7. Корректное закрытие всех процессов
        scheduler.shutdown(wait=False)
        try:
            await bot.session.close()
        except Exception as exc:
            logger.warning(f"Ошибка при закрытии сессии бота: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")