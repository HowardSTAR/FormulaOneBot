import html
import os

from aiogram import Bot

from app.db import db
from app.utils.safe_send import safe_send_message


async def send_admin_feedback(
    sender_name: str,
    sender_contact: str,
    message: str,
    telegram_id: int | None = None,
) -> int:
    admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    if not admin_id_raw.lstrip("-").isdigit():
        raise RuntimeError("ADMIN_TELEGRAM_ID не настроен")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не настроен")

    name = " ".join(sender_name.split())
    contact = " ".join(sender_contact.split())
    body = message.strip()
    if not 2 <= len(name) <= 80:
        raise ValueError("Имя должно содержать от 2 до 80 символов")
    if not 2 <= len(contact) <= 120:
        raise ValueError("Контакт должен содержать от 2 до 120 символов")
    if not 5 <= len(body) <= 3000:
        raise ValueError("Сообщение должно содержать от 5 до 3000 символов")

    if not db.conn:
        await db.connect()
    async with db.write_lock:
        cursor = await db.conn.execute(
            """
            INSERT INTO admin_feedback_messages(
                telegram_id, sender_name, sender_contact, message, delivered
            ) VALUES(?, ?, ?, ?, 0)
            """,
            (telegram_id, name, contact, body),
        )
        feedback_id = int(cursor.lastrowid)
        await db.conn.commit()

    telegram_line = f"\n<b>Telegram ID:</b> <code>{telegram_id}</code>" if telegram_id else ""
    text = (
        "📨 <b>Обратная связь с F1Hub</b>\n\n"
        f"<b>Имя:</b> {html.escape(name)}\n"
        f"<b>Контакт:</b> {html.escape(contact)}"
        f"{telegram_line}\n\n"
        f"<b>Сообщение:</b>\n{html.escape(body)}"
    )

    bot = Bot(token=token)
    try:
        delivered = await safe_send_message(bot, int(admin_id_raw), text, parse_mode="HTML")
    finally:
        await bot.session.close()
    if not delivered:
        raise RuntimeError("Telegram не подтвердил доставку сообщения администратору")

    async with db.write_lock:
        await db.conn.execute(
            "UPDATE admin_feedback_messages SET delivered=1 WHERE id=?",
            (feedback_id,),
        )
        await db.conn.commit()
    return feedback_id
