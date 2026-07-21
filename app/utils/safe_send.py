import asyncio
import logging
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InputMediaPhoto


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


async def safe_send_photo(bot: Bot, chat_id: int, photo, caption: str = "", **kwargs) -> bool:
    """Безопасная отправка фото (BytesIO, bytes или file_id)."""
    try:
        normalized_photo = photo
        if isinstance(photo, BytesIO):
            normalized_photo = BufferedInputFile(photo.getvalue(), filename="f1hub-results.png")
        elif isinstance(photo, (bytes, bytearray, memoryview)):
            normalized_photo = BufferedInputFile(bytes(photo), filename="f1hub-results.png")
        await bot.send_photo(chat_id=chat_id, photo=normalized_photo, caption=caption or None, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning(f"User {chat_id} blocked the bot.")
        return False
    except TelegramRetryAfter as e:
        logger.warning(f"FloodWait: Sleeping {e.retry_after} seconds for user {chat_id}...")
        await asyncio.sleep(e.retry_after)
        return await safe_send_photo(bot, chat_id, photo, caption, **kwargs)
    except TelegramBadRequest as e:
        logger.error(f"Bad Request for user {chat_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending photo to {chat_id}: {e}")
        return False


async def safe_send_media_group(
    bot: Bot,
    chat_id: int,
    media: Sequence[InputMediaPhoto],
    retries: int = 3,
    **kwargs,
) -> bool:
    """Отправляет Telegram-альбом с ограниченными повторами при FloodWait/сетевой ошибке."""
    if not 2 <= len(media) <= 10:
        logger.error("Media group for %s must contain 2..10 items, got %s", chat_id, len(media))
        return False

    for attempt in range(1, retries + 1):
        try:
            await bot.send_media_group(chat_id=chat_id, media=list(media), **kwargs)
            return True
        except TelegramForbiddenError:
            logger.warning("User %s blocked the bot.", chat_id)
            return False
        except TelegramRetryAfter as exc:
            if attempt == retries:
                logger.error("FloodWait retries exhausted for media group to %s", chat_id)
                return False
            await asyncio.sleep(float(exc.retry_after) + 0.25)
        except TelegramNetworkError as exc:
            if attempt == retries:
                logger.error("Network retries exhausted for media group to %s: %s", chat_id, exc)
                return False
            await asyncio.sleep(float(attempt))
        except TelegramBadRequest as exc:
            logger.error("Bad media group request for %s: %s", chat_id, exc)
            return False
        except Exception as exc:
            logger.exception("Unexpected media group error for %s: %s", chat_id, exc)
            return False

    return False


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


async def safe_answer_callback(callback: CallbackQuery, *args, **kwargs) -> bool:
    """
    Безопасный ответ на callback_query.
    Игнорирует устаревшие/инвалидные query (TelegramBadRequest), чтобы не падали хендлеры.
    """
    try:
        await callback.answer(*args, **kwargs)
        return True
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            logger.warning("Skipped stale callback answer: %s", e)
            return False
        logger.error("Bad callback answer request: %s", e)
        return False
    except TelegramNetworkError as e:
        logger.warning("Network error while answering callback: %s", e)
        return False
    except Exception as e:
        logger.exception("Unexpected callback.answer error: %s", e)
        return False
