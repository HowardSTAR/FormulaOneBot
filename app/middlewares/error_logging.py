# app/middlewares/error_logging.py

import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import Update

# ИСПРАВЛЕНО: Импортируем get_settings вместо хардкода OWNER_TELEGRAM_ID
from app.config import get_settings


class ErrorLoggingMiddleware(BaseMiddleware):
    """
    Логирует ошибки и рассылает уведомления ВСЕМ админам из конфига.
    """

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logging.exception("Ошибка при обработке апдейта: %s", event)

            # 1. Уведомляем пользователя (если возможно)
            try:
                user_msg = None
                if event.message:
                    user_msg = event.message
                elif event.callback_query:
                    user_msg = event.callback_query.message

                if user_msg:
                    await user_msg.answer(
                        "⚠️ Произошла ошибка.\n"
                        "Администраторы уже получили отчет и скоро всё починят! 🔧"
                    )
            except Exception:
                pass

            # 2. Уведомляем АДМИНОВ
            bot: Bot = data.get("bot")
            settings = get_settings()  # Получаем настройки

            # Если бот доступен и список админов не пуст
            if bot and settings.admin_ids:
                tb_str = traceback.format_exc()
                if len(tb_str) > 3500:
                    tb_str = tb_str[-3500:] + "\n...(truncated)"

                error_text = (
                    f"🚨 <b>CRITICAL ERROR</b>\n\n"
                    f"Update ID: {event.update_id}\n"
                    f"User: {event.from_user.full_name if event.from_user else 'Unknown'} (ID: {event.from_user.id if event.from_user else '?'})\n"
                    f"Error: {str(e)}\n\n"
                    f"<pre>{tb_str}</pre>"
                )

                # Проходимся по списку админов и отправляем каждому
                for admin_id in settings.admin_ids:
                    try:
                        await bot.send_message(chat_id=admin_id, text=error_text)
                    except Exception as admin_exc:
                        logging.error(f"Не удалось отправить лог админу {admin_id}: {admin_exc}")

            return None