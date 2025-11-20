import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update


class ErrorLoggingMiddleware(BaseMiddleware):
    """
    Глобальный middleware для логирования всех необработанных ошибок.

    Ничего не отправляет пользователю, только пишет лог и пробрасывает
    исключение дальше (чтобы aiogram тоже показал стек).
    """

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logging.exception("Необработанная ошибка при обработке апдейта: %r", event)
            # важно: пробрасываем дальше, чтобы стек был виден в консоли
            raise
