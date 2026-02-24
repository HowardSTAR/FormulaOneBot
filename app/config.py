import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    token: str
    redis_url: str  # <-- Новое поле


@dataclass
class Settings:
    bot: BotConfig
    admin_ids: List[int]


def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в .env файле")

    app_version = os.getenv("APP_VERSION", "0.0.0-local")

    # По умолчанию используем локальный Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    admin_ids_str = os.getenv("ADMIN_IDS", "")
    admin_ids = []
    if admin_ids_str:
        admin_ids = [
            int(x.strip())
            for x in admin_ids_str.split(",")
            if x.strip().isdigit()
        ]

    return Settings(
        bot=BotConfig(token=token, redis_url=redis_url),
        admin_ids=admin_ids,
        version=app_version
    )