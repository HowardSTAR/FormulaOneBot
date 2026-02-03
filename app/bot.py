from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage  # <-- Импорт
from redis.asyncio import Redis  # <-- Импорт драйвера

from app.config import get_settings


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    settings = get_settings()

    bot = Bot(
        token=settings.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Инициализируем Redis
    # redis_url берется из твоего конфига (обычно redis://localhost:6379/0)
    redis = Redis.from_url(settings.bot.redis_url)

    # Используем RedisStorage вместо MemoryStorage
    storage = RedisStorage(redis=redis)

    dp = Dispatcher(storage=storage)

    # Можно прокинуть redis в workflow_data, чтобы использовать в хендлерах
    dp["redis"] = redis

    return bot, dp