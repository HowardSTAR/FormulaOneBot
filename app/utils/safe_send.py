import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest
from aiogram.types import Message


logger = logging.getLogger(__name__)


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


async def safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """
    Безопасная отправка сообщения с обработкой ошибок и FloodWait.
    Возвращает True, если отправлено успешно.
    """
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning(f"User {chat_id} blocked the bot. Removing from DB recommended.")
        # TODO: Можно добавить логику удаления юзера из БД здесь
        return False
    except TelegramRetryAfter as e:
        logger.warning(f"FloodWait: Sleeping {e.retry_after} seconds for user {chat_id}...")
        await asyncio.sleep(e.retry_after)
        return await safe_send_message(bot, chat_id, text, **kwargs) # Рекурсивная попытка
    except TelegramBadRequest as e:
        logger.error(f"Bad Request for user {chat_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
        return False