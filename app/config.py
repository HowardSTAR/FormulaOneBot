import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

@dataclass
class BotConfig:
    token: str

@dataclass
class Settings:
    bot: BotConfig
    admin_ids: List[int]  # Добавили поле для списка админов

def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в .env файле")

    # Читаем строку "123,456" и превращаем в список чисел [123, 456]
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    admin_ids = []
    if admin_ids_str:
        # Разбиваем по запятой, убираем пробелы и проверяем, что это цифры
        admin_ids = [
            int(x.strip())
            for x in admin_ids_str.split(",")
            if x.strip().isdigit()
        ]

    return Settings(
        bot=BotConfig(token=token),
        admin_ids=admin_ids
    )