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
from app.handlers import start, races, drivers, teams, favorites, secret, settings, compare, feedback
from app.middlewares.error_logging import ErrorLoggingMiddleware
from app.utils.backup import create_backup
from app.utils.notifications import check_and_send_notifications, check_and_send_results

# Базовая настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
def setup_logging():
    # Создаем папку logs, если нет
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "bot.log"

    # Формат логов: Время | Уровень | Имя модуля | Сообщение
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    # 1. Логгер в файл с ротацией (макс 5 МБ, храним 3 последних файла)
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # 2. Логгер в консоль (чтобы видеть глазами при разработке)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Применяем настройки
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )

    # Убираем шум от библиотек (слишком много логов)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Вызываем настройку СРАЗУ
setup_logging()
logger = logging.getLogger(__name__)

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
        compare.router,
        feedback.router
    )

    # # Планировщик
    scheduler = AsyncIOScheduler(timezone="UTC")
    # # вместо "раз в день" делаем каждые 10 минут
    # scheduler.add_job(
    #     check_and_notify_favorites,
    #     "interval",
    #     minutes=10,
    #     args=[bot],
    #     id="favorites_notifications",
    #     replace_existing=True,
    # )
    #
    # # Напоминание за сутки до ближайшей гонки
    # scheduler.add_job(
    #     remind_next_race,
    #     "interval",
    #     minutes=15,  # можно 15 или 60 — как хочешь
    #     args=[bot],
    #     id="next_race_reminder",
    #     replace_existing=True,
    # )
    #
    # scheduler.add_job(
    #     check_and_notify_quali,
    #     "interval",
    #     minutes=5,  # можно 2–10, как тебе комфортно
    #     args=[bot],
    #     id="quali_notifications",
    #     replace_existing=True,
    # )

    scheduler.add_job(
        check_and_send_notifications,
        "interval",
        seconds=30,
        args=[bot],  # <--- ВАЖНО: передаем бота в аргументы!
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