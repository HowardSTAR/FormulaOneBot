import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass
class BotConfig:
    token: str

@dataclass
class Settings:
    bot: BotConfig

def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в .env файле")
    return Settings(bot=BotConfig(token=token))