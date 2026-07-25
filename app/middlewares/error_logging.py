import logging
import traceback
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import TelegramObject, Update

from app.admin_config import get_primary_admin_telegram_id
from app.utils.safe_send import safe_send_message
from app.db import db
from app.services.activity_service import record_telegram_activity

logger = logging.getLogger(__name__)

class ErrorLoggingMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        try:
            telegram_user = getattr(event, "from_user", None)
            if telegram_user is None and isinstance(event, Update):
                nested_event = event.message or event.callback_query or event.inline_query
                telegram_user = getattr(nested_event, "from_user", None)
            if telegram_user is not None:
                await record_telegram_activity(
                    db,
                    int(telegram_user.id),
                    display_name=" ".join(
                        part for part in [telegram_user.first_name, telegram_user.last_name] if part
                    ),
                    telegram_username=telegram_user.username,
                )
            return await handler(event, data)
        except Exception as e:
            if isinstance(e, TelegramBadRequest):
                msg = str(e).lower()
                if "query is too old" in msg or "query id is invalid" in msg:
                    logger.warning("Ignored stale callback query error: %s", e)
                    return None
            # 1. Получаем информацию о пользователе и чате
            user_id = "unknown"
            chat_id = None

            if isinstance(event, Update):
                if event.message:
                    user_id = event.message.from_user.username
                    chat_id = event.message.chat.id
                elif event.callback_query:
                    user_id = event.callback_query.from_user.username
                    # Если это callback, сообщение может быть старым, но чат тот же
                    if event.callback_query.message:
                        chat_id = event.callback_query.message.chat.id

            # 2. Логируем ошибку в файл
            logger.exception(
                f"CRITICAL ERROR handling update {event.update_id if isinstance(event, Update) else '?'} from user {user_id}")

            bot: Bot = data.get("bot")
            admin_id = get_primary_admin_telegram_id()

            # 3. Уведомление АДМИНУ
            if bot and admin_id:
                try:
                    tb_list = traceback.format_exception(type(e), e, e.__traceback__)
                    short_tb = "".join(tb_list[-3:])

                    text_admin = (
                        f"🚨 <b>BOT CRITICAL ERROR!</b>\n\n"
                        f"👤 User: @{user_id}\n"
                        f"💀 Error: {str(e)}\n\n"
                        f"<pre>{short_tb}</pre>"
                    )
                    await safe_send_message(bot, admin_id, text_admin)
                except Exception as send_err:
                    logger.error(f"Failed to send error notification to admin: {send_err}")

            # 4. Уведомление ПОЛЬЗОВАТЕЛЮ (Новая часть)
            if bot and chat_id:
                try:
                    text_user = (
                        "😔 <b>Произошла ошибка.</b>\n\n"
                        "Я уже отправил автоматический отчет администратору.\n"
                        "Мы скоро всё починим!"
                    )
                    await safe_send_message(bot, chat_id, text_user)
                except Exception:
                    # Если не удалось отправить сообщение пользователю (например, бан), просто игнорируем
                    pass

            return None
