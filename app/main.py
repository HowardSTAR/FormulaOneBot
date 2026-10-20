import asyncio
import logging
import os
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.bot import create_bot_and_dispatcher
from app.config import get_settings
from app.db import db
from app.f1_data import init_redis_cache, close_redis_cache
from app.handlers import account_link, menu, start, races, drivers, teams, favorites, secret, settings, compare, feedback, groups, insights, telegram_features, guest
from app.middlewares.error_logging import ErrorLoggingMiddleware


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
_instance = uuid.uuid4().hex
_heartbeat = None


async def on_startup(bot: Bot):
    global _heartbeat
    settings = get_settings()

    # 1. Подключаем БД и СОЗДАЕМ ТАБЛИЦЫ
    await db.initialize()

    mini_app_url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if mini_app_url:
        if not mini_app_url.startswith("https://"):
            raise RuntimeError("MINI_APP_URL must use HTTPS for Telegram Mini Apps")
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть TurboTears",
                web_app=WebAppInfo(url=mini_app_url),
            )
        )
        logging.getLogger(__name__).info("Telegram Mini App menu configured: %s", mini_app_url)

    # 2. Инициализируем Redis кэш
    if settings.bot.redis_url:
        await init_redis_cache(settings.bot.redis_url)

    logger.info("Bot started, DB connected, tables initialized.")
    from app.services.operations import component, heartbeat
    await component('bot', _instance, starting=True)
    _heartbeat = asyncio.create_task(heartbeat('bot', _instance))


async def on_shutdown(bot: Bot):
    if _heartbeat is not None:
        _heartbeat.cancel()
        await asyncio.gather(_heartbeat, return_exceptions=True)
        from app.services.operations import component
        await component('bot', _instance, stopping=True)
    try:
        await db.close()
    finally:
        await close_redis_cache()
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
        telegram_features.router,
        guest.router,
        groups.router,  # раньше start — для my_chat_member
        account_link.router,
        menu.router,  # navigation must win over year/feedback text-input states
        insights.router,
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
        try:
            await bot.session.close()
        except Exception as exc:
            logger.warning(f"Ошибка при закрытии сессии бота: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
