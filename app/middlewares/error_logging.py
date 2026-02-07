import logging
import traceback
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update

from app.utils.safe_send import safe_send_message

logger = logging.getLogger(__name__)


# ID администратора для уведомлений о падениях
ADMIN_ID = 2099386


class ErrorLoggingMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
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

            # 3. Уведомление АДМИНУ
            if bot and ADMIN_ID:
                try:
                    tb_list = traceback.format_exception(type(e), e, e.__traceback__)
                    short_tb = "".join(tb_list[-3:])

                    text_admin = (
                        f"🚨 <b>BOT CRITICAL ERROR!</b>\n\n"
                        f"👤 User: @{user_id}\n"
                        f"💀 Error: {str(e)}\n\n"
                        f"<pre>{short_tb}</pre>"
                    )
                    await safe_send_message(bot, ADMIN_ID, text_admin)
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