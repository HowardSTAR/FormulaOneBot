"""Private group views and cancellation. No mutations or public personal fallback."""
import asyncio
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, EphemeralMessageParameters, Message

from app.db import db
from app.services.prediction_service import get_personal_prediction_review
from app.services.prediction_social import list_leagues
from app.utils.activity_status import stop_activity
from app.utils.safe_send import safe_answer_callback
from app.utils.telegram_presentation import review_card, send_card

router = Router(name="telegram_features")


@router.callback_query(F.data.startswith("activity:stop:"))
async def cancel_activity(callback: CallbackQuery):
    stopped = stop_activity(callback.bot.id, callback)
    await safe_answer_callback(callback, "Останавливаю загрузку…" if stopped else "Загрузка уже завершена.")


async def linked_user_id(telegram_id):
    if not db.conn:
        await db.connect()
    row = await (await db.conn.execute(
        "SELECT id FROM users WHERE telegram_id=? AND archived_at IS NULL", (telegram_id,)
    )).fetchone()
    return row["id"] if row else None


@router.callback_query(F.data.startswith("personal:"))
async def personal_view(callback: CallbackQuery):
    match = re.fullmatch(r"personal:(review|leagues):(\d{4}):(\d{1,2})", callback.data or "")
    if not match or not isinstance(callback.message, Message) or callback.message.chat.type not in {"private", "group", "supergroup"}:
        await safe_answer_callback(callback, "Откройте итоги этапа снова.")
        return
    kind, season, round_num = match.group(1), int(match.group(2)), int(match.group(3))
    if not 1950 <= season <= 2100 or not 1 <= round_num <= 30 or callback.from_user.is_bot:
        await safe_answer_callback(callback, "Некорректный этап.")
        return
    private = callback.message.chat.type == "private"
    if private and callback.message.chat.id != callback.from_user.id:
        return
    # Callback-triggered ephemeral replies have a 15-second Telegram deadline.
    # Fail closed: never fall back to a public message containing personal data.
    ephemeral = None if private else EphemeralMessageParameters(
        receiver_user_id=callback.from_user.id, callback_query_id=callback.id,
        replace_callback_query_message=not bool(callback.message.ephemeral_message_id),
    )
    kwargs = {"protect_content": True, "ephemeral_message_parameters": ephemeral,
              "message_thread_id": callback.message.message_thread_id, "request_timeout": 3}
    try:
        # Include the callback acknowledgement in the deadline, not just loading.
        async with asyncio.timeout(12):
            await safe_answer_callback(callback, request_timeout=2)
            uid = await linked_user_id(callback.from_user.id)
            text, card = "Сначала войдите в F1Hub через Telegram и сохраните прогноз.", None
            if uid is not None and kind == "review":
                review = await get_personal_prediction_review(uid, season, round_num)
                if review:
                    card, text = review_card(review)
                else:
                    text = "У вас нет сохранённого прогноза на этот этап."
            elif uid is not None:
                from html import escape
                leagues = await list_leagues(uid)
                text = "<b>Мои лиги</b>\n" + ("\n".join(escape(item["name"][:100]) for item in leagues[:20]) or "Вы пока не вступили в лигу.")
                if len(leagues) > 20:
                    text += "\n\nВсе лиги доступны в Mini App → Прогнозы → Лиги друзей."
            if card:
                await send_card(callback.bot, callback.message.chat.id, card, text, **kwargs)
            else:
                await callback.bot.send_message(chat_id=callback.message.chat.id, text=text, parse_mode="HTML", **kwargs)
    except (TimeoutError, TelegramAPIError):
        await safe_answer_callback(callback, "Не удалось открыть личный ответ. Попробуйте в личном чате с ботом.", show_alert=True, request_timeout=2)
