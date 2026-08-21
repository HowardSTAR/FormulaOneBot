"""
Обработчики для групповых чатов: добавление/удаление бота, команды без избранного.
"""
import logging

from aiogram import Bot, Router, F
from aiogram.enums import ChatType
from aiogram.filters import Command, ChatMemberUpdatedFilter
from aiogram.filters.chat_member_updated import JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import ChatMemberUpdated, Message

from app.db import add_group_chat, remove_group_chat

logger = logging.getLogger(__name__)
router = Router()


# Только группы и супергруппы
GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def _is_group(chat_type: ChatType) -> bool:
    return chat_type in GROUP_TYPES


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added_to_group(event: ChatMemberUpdated, bot: Bot):
    """Бот добавлен в группу — сохраняем chat_id для рассылки уведомлений."""
    if not _is_group(event.chat.type):
        return
    chat_id = event.chat.id
    await add_group_chat(chat_id)
    logger.info(f"Bot added to group {chat_id}, subscribed to notifications.")
    await bot.send_message(
        chat_id,
        "🏎 <b>TurboTears</b> в чате!\n\n"
        "Используйте команды:\n"
        "• <code>/drivers</code> — личный зачёт\n"
        "• <code>/teams</code> — кубок конструкторов\n"
        "• <code>/next_race</code> — следующая гонка\n"
        "• <code>/races</code> — календарь сезона\n\n"
        "Уведомления о квалификации и гонках приходят автоматически.",
        parse_mode="HTML",
    )


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_removed_from_group(event: ChatMemberUpdated):
    """Бот удалён из группы — убираем из рассылки."""
    if not _is_group(event.chat.type):
        return
    chat_id = event.chat.id
    await remove_group_chat(chat_id)
    logger.info(f"Bot removed from group {chat_id}, unsubscribed.")


@router.message(Command("f1"), F.chat.type.in_(GROUP_TYPES))
async def cmd_f1_help_group(message: Message):
    """Справка по командам бота в группе."""
    await message.answer(
        "🏎 <b>Команды TurboTears</b>\n\n"
        "<code>/drivers</code> [год] — личный зачёт пилотов\n"
        "<code>/teams</code> [год] — кубок конструкторов\n"
        "<code>/next_race</code> — следующая гонка\n"
        "<code>/races</code> [год] — календарь сезона\n\n"
        "Уведомления о квалификации и гонках приходят автоматически.",
        parse_mode="HTML",
    )
