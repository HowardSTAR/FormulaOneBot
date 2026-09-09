import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update

from app.services.error_alerts import report_error, priority_for
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
            priority = priority_for(e)
            # 1. Получаем информацию о пользователе и чате
            chat_id = None

            if isinstance(event, Update):
                if event.message:
                    chat_id = event.message.chat.id
                elif event.callback_query:
                    # Если это callback, сообщение может быть старым, но чат тот же
                    if event.callback_query.message:
                        chat_id = event.callback_query.message.chat.id

            # 2. Логируем ошибку в файл
            logger.log(logging.CRITICAL if priority == "blocking" else logging.ERROR if priority in ("medium", "critical") else logging.WARNING,
                       "Bot update failed: priority=%s type=%s", priority, type(e).__name__, exc_info=True)

            bot: Bot = data.get("bot")

            # 3. Уведомление АДМИНУ
            await report_error(e, bot=bot, priority=priority)

            # 4. Уведомление ПОЛЬЗОВАТЕЛЮ (Новая часть)
            if bot and chat_id and priority != "minimal":
                try:
                    text_user = (
                        "😔 <b>Произошла ошибка.</b>\n\n"
                        "Не удалось выполнить запрос. Попробуйте немного позже."
                    )
                    await safe_send_message(bot, chat_id, text_user)
                except Exception:
                    # Если не удалось отправить сообщение пользователю (например, бан), просто игнорируем
                    pass

            return None
