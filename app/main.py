import asyncio
import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot import create_bot_and_dispatcher
from app.db import init_db
from app.f1_data import warmup_current_season_sessions
from app.handlers.drivers import router as drivers_router
from app.handlers.favorites import router as favorites_router
from app.handlers.races import router as races_router
from app.handlers.start import router as start_router
from app.handlers.teams import router as teams_router
from app.middlewares.error_logging import ErrorLoggingMiddleware
from app.notifications import check_and_notify_favorites, remind_next_race, check_and_notify_quali

# Базовая настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    await init_db()

    bot, dp = create_bot_and_dispatcher()

    dp.update.outer_middleware(ErrorLoggingMiddleware())

    # Регистрируем все роутеры
    dp.include_router(start_router)
    dp.include_router(races_router)
    dp.include_router(drivers_router)
    dp.include_router(teams_router)
    dp.include_router(favorites_router)

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
        print(f"Ошибка Telegram API: {exc}")
    except KeyboardInterrupt:
        print("Остановка бота пользователем")

if __name__ == "__main__":
    asyncio.run(main())