# app/auth.py

from typing import Annotated

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
        # raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data header")

        # --- ВРЕМЕННЫЙ ОБХОД ДЛЯ ТЕСТОВ В БРАУЗЕРЕ ---
        return 2099386

    settings = get_settings()

    try:
        # 1. Проверяем валидность подписи (подделаны данные или нет)
        is_valid = check_webapp_signature(settings.bot.token, x_telegram_init_data)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid WebApp signature")

        # 2. Парсим данные
        web_app_data: WebAppInitData = safe_parse_webapp_init_data(
            token=settings.bot.token,
            init_data=x_telegram_init_data
        )

        # 3. Достаем ID пользователя
        return web_app_data.user.id

    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")