import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Message


async def safe_answer(
    message: Message,
    text: str,
    retries: int = 3,
    delay: float = 1.0,
    **kwargs,
):
    """
    Безопасная отправка message.answer с ретраями при TelegramNetworkError.

    retries — сколько всего попыток.
    delay — пауза между попытками в секундах.
    **kwargs — всё, что ты обычно передаёшь в message.answer(...).
    """
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            return await message.answer(text, **kwargs)
        except TelegramNetworkError as exc:
            last_exc = exc
            logging.warning(
                "TelegramNetworkError при отправке сообщения (попытка %s/%s, chat_id=%s): %s",
                attempt,
                retries,
                message.chat.id,
                exc
            )
            if attempt == retries:
                logging.error(
                    "Не удалось отправить сообщение пользователю %s после %s попыток: %s",
                    message.chat.id,
                    retries,
                    exc
                )
                return None

            await asyncio.sleep(delay)

    return None
