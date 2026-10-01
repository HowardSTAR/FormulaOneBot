"""Private-chat navigation. Reuses existing actions with the actual clicker's identity."""
import asyncio
from importlib import import_module

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.utils.bot_menu import MAIN_BUTTONS, SECTIONS, WEB_DESTINATIONS, main_keyboard, section_keyboard
from app.utils.mini_app_links import destination_buttons
from app.utils.safe_send import safe_answer_callback
from app.services.prediction_service import get_prediction_context, parse_utc
from app.utils.telegram_presentation import disabled_button
from app.utils.time_tools import telegram_time
from datetime import datetime, timezone

ACTION_HANDLERS = {
    "next": ("races", "next_race_btn", False),
    "calendar": ("races", "btn_races_ask_year", True),
    "recap": ("insights", "recap", False),
    "drivers": ("drivers", "btn_drivers_ask_year", True),
    "teams": ("teams", "btn_teams_ask_year", True),
    "compare": ("compare", "cmd_compare", True),
    "history": ("insights", "history", False),
    "guide": ("insights", "choose_driver", False),
    "community": ("start", "community_button", False),
    "favorites": ("favorites", "cmd_favorites", False),
    "settings": ("settings", "cmd_settings", True),
    "feedback": ("feedback", "cmd_feedback", True),
}


async def section_content(bot, section: str):
    heading, hint, _ = SECTIONS[section]
    web = None
    if section in WEB_DESTINATIONS:
        try:
            web = await asyncio.wait_for(destination_buttons(bot, WEB_DESTINATIONS[section]), timeout=5)
        except asyncio.TimeoutError:
            pass
        if web is None:
            hint += "\n\nКнопки Mini App временно недоступны. Попробуйте позже."
    if section == "predictions":
        try:
            context = await asyncio.wait_for(get_prediction_context(), timeout=5)
        except Exception:
            context = {"status": "unavailable"}
        now = datetime.now(timezone.utc)
        opens, deadline = parse_utc(context.get("opens_at_utc")), parse_utc(context.get("deadline_utc"))
        status = None
        if context.get("is_open"):
            hint += "\n\nПриём открыт. Закрытие: " + telegram_time(deadline)
            if web:
                web.inline_keyboard[0][0].style = "primary"
        elif opens and now < opens:
            status = "Приём ещё не открыт"
            hint += "\n\nПрогнозы откроются: " + telegram_time(opens)
        elif deadline and now >= deadline:
            status = "Приём завершён"
            hint += "\n\nВыбор изменить нельзя. Сохранённый прогноз доступен для просмотра."
        else:
            status = "Сроки уточняются"
            hint += "\n\nРасписание приёма пока не подтверждено."
        if web and status:
            web.inline_keyboard.insert(0, [disabled_button(status)])
    return f"<b>{heading}</b>\n\n{hint}", section_keyboard(section, web)


async def open_main_menu(message: Message, state: FSMContext):
    await state.clear()
    heading, hint, _ = SECTIONS["home"]
    await message.answer(f"<b>{heading}</b>\n\n{hint}", reply_markup=main_keyboard(), parse_mode="HTML")


async def open_section(message: Message, state: FSMContext):
    await state.clear()
    from app.utils.activity_status import ActivityStatus
    async with ActivityStatus(message, "Открываю раздел…"):
        text, keyboard = await section_content(message.bot, MAIN_BUTTONS[message.text])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Выберите раздел внизу.", reply_markup=main_keyboard())


async def navigate(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await safe_answer_callback(callback, "Откройте меню в личном чате с ботом.")
        return
    parts = (callback.data or "").split(":")
    valid = len(parts) == 3 and parts[0] == "nav" and (
        (parts[1] == "section" and parts[2] in SECTIONS)
        or (parts[1] == "action" and parts[2] in ACTION_HANDLERS)
    )
    if not valid:
        await safe_answer_callback(callback, "Пункт меню устарел. Откройте меню снова.")
        return
    # Stop Telegram's spinner before waiting for a data source or Mini App URL.
    await safe_answer_callback(callback)
    if parts[1:] == ["section", "home"]:
        # editMessageText accepts only inline markup: send the reply keyboard
        # again so returning home also restores a lost/hidden client keyboard.
        await open_main_menu(callback.message, state)
        return
    await state.clear()
    if parts[1] == "section":
        text, keyboard = await section_content(callback.bot, parts[2])
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return
    module, name, needs_state = ACTION_HANDLERS[parts[2]]
    action = getattr(import_module(f"app.handlers.{module}"), name)
    # callback.message is authored by the BOT. Never read its sender as the user.
    message = callback.message.model_copy(update={"from_user": callback.from_user, "text": None, "entities": None}).as_(callback.bot)
    if needs_state:
        await action(message, state)
    else:
        await action(message)


def create_router():
    navigation = Router(name="compact_menu")
    navigation.message.register(open_main_menu, Command("menu"), F.chat.type == "private")
    navigation.message.register(cancel_action, Command("cancel"), F.chat.type == "private")
    navigation.message.register(open_section, F.text.in_(MAIN_BUTTONS), F.chat.type == "private")
    navigation.callback_query.register(navigate, F.data.startswith("nav:"))
    return navigation


router = create_router()
