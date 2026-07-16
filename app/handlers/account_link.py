"""Telegram handlers for website account linking."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db import db, get_or_create_user
from app.services.account_link_service import AccountLinkService, LinkConflict, LinkError

router = Router()


def _service() -> AccountLinkService:
    return AccountLinkService(db)


def _confirmation_keyboard(hint: str, conflict: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if conflict:
        rows.extend(
            [
                [InlineKeyboardButton(text="Сохранить профиль сайта", callback_data=f"link:web:{hint}")],
                [InlineKeyboardButton(text="Сохранить профиль Telegram", callback_data=f"link:telegram:{hint}")],
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text="Подтвердить привязку", callback_data=f"link:web:{hint}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"link:cancel:{hint}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart(deep_link=True))
async def start_account_link(message: Message, command: CommandObject) -> None:
    args = command.args or ""
    if not args.startswith("link_") or not message.from_user:
        return
    token = args.removeprefix("link_")
    try:
        await get_or_create_user(message.from_user.id)
        details = await _service().inspect_web_link(token, message.from_user.id)
    except LinkError as exc:
        await message.answer(f"Ссылка привязки недействительна: {exc}")
        return
    web_email = details["web_user"].get("email") or "аккаунт сайта"
    conflict_note = (
        "\n\nУ вас уже есть отдельный Telegram-профиль с данными. Выберите, какой профиль считать основным. "
        "Избранное, голоса и настройки второго профиля будут перенесены."
        if details["conflict"] else ""
    )
    await message.answer(
        f"Привязать Telegram к {web_email}?{conflict_note}",
        reply_markup=_confirmation_keyboard(token[-16:], details["conflict"]),
    )


@router.message(Command("link"))
async def create_or_consume_link_code(message: Message, command: CommandObject) -> None:
    if not message.from_user:
        return
    try:
        await get_or_create_user(message.from_user.id)
        generated = await _service().create_bot_code(message.from_user.id)
        await message.answer(
            "Введите этот код в форме привязки на сайте:\n\n"
            f"<code>{generated['code']}</code>\n\nКод действует 5 минут."
        )
    except LinkConflict:
        await message.answer(
            "Оба аккаунта содержат данные. Используйте ссылку с сайта, чтобы выбрать основной профиль."
        )
    except LinkError as exc:
        await message.answer(f"Не удалось выполнить привязку: {exc}")


@router.callback_query(F.data.regexp(r"^link:(web|telegram|cancel):[A-Za-z0-9_-]{16}$"))
async def account_link_callback(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    if not callback.message:
        await callback.answer("Сообщение больше недоступно", show_alert=True)
        return
    _, action, hint = callback.data.split(":", 2)
    try:
        if action == "cancel":
            await _service().cancel_by_hint(hint, callback.from_user.id)
            await callback.message.edit_text("Привязка отменена.")
        else:
            strategy = "keep_web" if action == "web" else "keep_telegram"
            result = await _service().approve_by_hint(hint, callback.from_user.id, strategy)
            await callback.message.edit_text(
                "Аккаунты успешно связаны. "
                f"Основной профиль: #{result['user']['id']}."
            )
        await callback.answer()
    except LinkError as exc:
        await callback.answer(str(exc), show_alert=True)
