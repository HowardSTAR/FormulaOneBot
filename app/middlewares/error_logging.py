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
            # 1. Получаем информацию о пользователе и событии
            user_id = "unknown"
            if isinstance(event, Update):
                if event.message:
                    user_id = event.message.from_user.username
                elif event.callback_query:
                    user_id = event.callback_query.from_user.username

            # 2. Логируем полную ошибку в файл (с Traceback)
            error_msg = f"CRITICAL ERROR handling update {event.update_id if isinstance(event, Update) else '?'} from user {user_id}: {e}"
            logger.exception(error_msg)

            # 3. Отправляем уведомление админу (Вам)
            bot: Bot = data.get("bot")
            if bot and ADMIN_ID:
                try:
                    # Формируем короткий отчет (последние 3 строки ошибки, чтобы не спамить полотном)
                    tb_list = traceback.format_exception(type(e), e, e.__traceback__)
                    short_tb = "".join(tb_list[-3:])

                    text = (
                        f"🚨 <b>BOT CRITICAL ERROR!</b>\n\n"
                        f"👤 User: @{user_id}\n"
                        f"💀 Error: {str(e)}\n\n"
                        f"<pre>{short_tb}</pre>"
                    )

                    # Отправляем в фоновом режиме (без await, чтобы не блочить, если safe_send умеет fire-and-forget,
                    # но safe_send асинхронный, поэтому await нужен)
                    await safe_send_message(bot, ADMIN_ID, text)

                except Exception as send_err:
                    # Если даже админу отправить не удалось — пишем в лог, но не падаем
                    logger.error(f"Failed to send error notification to admin: {send_err}")

            # Важно: Возвращаем None, чтобы апдейт считался обработанным (хоть и с ошибкой)
            return None