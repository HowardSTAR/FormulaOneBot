# app/auth.py

from typing import Annotated
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException
from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data, WebAppInitData

from app.config import get_settings


async def get_current_user_id(
        x_telegram_init_data: Annotated[str | None, Header()] = None
) -> int:
    """
    FastAPI Dependency.
    Принимает заголовок X-Telegram-Init-Data, проверяет подпись
    и возвращает ID пользователя.
    """
    if not x_telegram_init_data:
        # Если заголовка нет — значит, запрос не из Телеграма или хакер
        raise HTTPException(status_code=401, detail="Откройте приложение через Telegram или войдите в аккаунт на сайте")

    settings = get_settings()

    try:
        if len(x_telegram_init_data) > 16384:
            raise ValueError("Oversized initData")
        pairs = parse_qsl(x_telegram_init_data, max_num_fields=64)
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("Duplicate initData fields")
        # 1. Проверяем валидность подписи (подделаны данные или нет)
        is_valid = check_webapp_signature(settings.bot.token, x_telegram_init_data)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Не удалось подтвердить вход через Telegram. Переоткройте приложение")

        # 2. Парсим данные
        web_app_data: WebAppInitData = safe_parse_webapp_init_data(
            token=settings.bot.token,
            init_data=x_telegram_init_data
        )

        # A valid signature alone permits indefinite replay of captured data.
        age = time.time() - web_app_data.auth_date.timestamp()
        if age < -30 or age >= 3600 or web_app_data.user is None or web_app_data.user.id <= 0:
            raise ValueError("Expired or invalid initData")

        # 3. Достаем ID пользователя
        return web_app_data.user.id

    except Exception:
        raise HTTPException(status_code=401, detail="Не удалось подтвердить вход через Telegram. Переоткройте приложение")


async def get_optional_user_id(
        x_telegram_init_data: Annotated[str | None, Header()] = None
) -> int | None:
    """Опциональная аутентификация для публичного read-only режима сайта."""
    if not x_telegram_init_data:
        return None
    try:
        return await get_current_user_id(x_telegram_init_data)
    except HTTPException:
        return None
