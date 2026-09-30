"""Real aiogram routing, with a local transport: no Telegram or production DB calls."""
import asyncio
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User

from app.handlers import insights, menu, start
from app.utils.bot_menu import MAIN_BUTTONS, SECTIONS, WEB_DESTINATIONS, main_keyboard, section_keyboard

ACTOR = User(id=777, is_bot=False, first_name="Participant")
BOT_AUTHOR = User(id=123456, is_bot=True, first_name="F1Hub")


class LocalSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=getattr(method, "message_id", None) or len(self.methods),
                           date=datetime.now(timezone.utc), chat=Chat(id=method.chat_id, type="private"),
                           from_user=BOT_AUTHOR, text=method.text,
                           reply_markup=method.reply_markup if isinstance(method.reply_markup, InlineKeyboardMarkup) else None).as_(bot)
        return True

    async def stream_content(self, url, **kwargs):
        yield b""


@pytest.fixture
def navigation(monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://example.test/?source=telegram")
    monkeypatch.setattr(menu, "get_prediction_context", AsyncMock(return_value={"status": "unavailable"}))
    session = LocalSession()
    bot = Bot("123456:LOCAL_TEST", session=session)
    dispatcher = Dispatcher()
    dispatcher.include_router(menu.create_router())
    state = dispatcher.fsm.get_context(bot=bot, chat_id=ACTOR.id, user_id=ACTOR.id)
    return bot, dispatcher, state, session


def user_message(bot, text):
    return Message(message_id=10, date=datetime.now(timezone.utc),
                   chat=Chat(id=ACTOR.id, type="private"), from_user=ACTOR, text=text).as_(bot)


def clicked(bot, data, *, private=True):
    message = Message(message_id=20, date=datetime.now(timezone.utc), from_user=BOT_AUTHOR,
                      chat=Chat(id=ACTOR.id if private else -100123, type="private" if private else "supergroup"),
                      text="Menu").as_(bot)
    return CallbackQuery(id="test", from_user=ACTOR, chat_instance="test", message=message, data=data).as_(bot)


def test_keyboard_is_two_rows_and_all_old_actions_are_reachable():
    keyboard = main_keyboard()
    assert [len(row) for row in keyboard.keyboard] == [2, 2]
    assert [button.text for row in keyboard.keyboard for button in row] == list(MAIN_BUTTONS)
    assert keyboard.resize_keyboard and not keyboard.one_time_keyboard
    seen, pending, actions = set(), list(MAIN_BUTTONS.values()), set()
    while pending:
        section = pending.pop()
        if section in seen:
            continue
        seen.add(section)
        keyboard = section_keyboard(section)
        for row in keyboard.inline_keyboard if keyboard else []:
            assert len(row) <= 2
            for button in row:
                assert len(button.callback_data.encode()) <= 64
                _, kind, target = button.callback_data.split(":")
                if kind == "section": pending.append(target)
                else: actions.add(target)
    assert seen == set(SECTIONS)
    assert actions == set(menu.ACTION_HANDLERS)  # none of the twelve old buttons was lost
    assert not any("admin" in path for buttons in WEB_DESTINATIONS.values() for _, path, _ in buttons)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", list(MAIN_BUTTONS))
async def test_main_buttons_escape_year_or_feedback_input(navigation, label):
    bot, dispatcher, state, session = navigation
    fallback = Router()
    waiting_handler = AsyncMock()
    async def waiting_message(message):
        await waiting_handler(message)
    fallback.message.register(waiting_message)
    dispatcher.include_router(fallback)
    await state.set_state("FeedbackState:waiting_for_message")
    await state.update_data(year=1997, feedback="not sent")
    await dispatcher.feed_update(bot, Update(update_id=1, message=user_message(bot, label)))
    waiting_handler.assert_not_awaited()
    assert await state.get_state() is None and await state.get_data() == {}
    assert any(isinstance(method, SendMessage) for method in session.methods)


@pytest.mark.asyncio
async def test_submenus_edit_the_same_message_and_have_back_navigation(navigation):
    bot, dispatcher, state, session = navigation
    await state.set_state("DriversYearState:year")
    for index, section in enumerate(("stats", "guides", "sections", "home")):
        await dispatcher.feed_update(bot, Update(update_id=index, callback_query=clicked(bot, f"nav:section:{section}")))
        assert isinstance(session.methods[-2], AnswerCallbackQuery)
        result = session.methods[-1]
        assert isinstance(result, EditMessageText) and result.message_id == 20
        if section != "home":
            assert result.reply_markup.inline_keyboard[-1][0].text.startswith("←")
    assert await state.get_state() is None
    assert not any(isinstance(method, SendMessage) for method in session.methods)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", list(menu.ACTION_HANDLERS))
async def test_callbacks_reuse_actions_with_clicker_not_bot_identity(navigation, monkeypatch, action):
    bot, dispatcher, state, session = navigation
    module, function, needs_state = menu.ACTION_HANDLERS[action]
    async def handle(message, *args):
        assert isinstance(session.methods[0], AnswerCallbackQuery)
        assert message.from_user.id == ACTOR.id != BOT_AUTHOR.id
        assert message.chat.id == ACTOR.id and message.bot is bot
        assert message.text is None  # a menu title cannot become an input/command
        assert await state.get_state() is None
        if needs_state:
            assert len(args) == 1 and args[0].key == state.key
        else:
            assert args == ()
    handler = AsyncMock(side_effect=handle)
    monkeypatch.setattr(import_module(f"app.handlers.{module}"), function, handler)
    await state.set_state("OldState:year")
    await dispatcher.feed_update(bot, Update(update_id=1, callback_query=clicked(bot, f"nav:action:{action}")))
    handler.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/menu", "/cancel"])
async def test_restore_menu_clears_pending_input_without_sending_feedback(navigation, command):
    bot, dispatcher, state, session = navigation
    await state.set_state("FeedbackState:waiting_for_message")
    await dispatcher.feed_update(bot, Update(update_id=1, message=user_message(bot, command)))
    result = session.methods[-1]
    assert isinstance(result, SendMessage)
    assert result.chat_id == ACTOR.id
    assert len(result.reply_markup.keyboard) == 2
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_driver_year_input_still_works_after_opening_from_submenu(navigation, monkeypatch):
    from app.handlers import drivers
    bot, dispatcher, state, session = navigation
    legacy = Router()
    legacy.message.register(drivers.drivers_year_from_text, drivers.DriversYearState.year)
    dispatcher.include_router(legacy)
    send = AsyncMock()
    monkeypatch.setattr(drivers, "_send_drivers_for_year", send)
    await dispatcher.feed_update(bot, Update(update_id=1, callback_query=clicked(bot, "nav:action:drivers")))
    assert await state.get_state() == drivers.DriversYearState.year.state
    assert "год" in session.methods[-1].text
    await dispatcher.feed_update(bot, Update(update_id=2, message=user_message(bot, "1997")))
    assert send.await_args.args[1] == 1997
    assert send.await_args.kwargs == {"telegram_id": ACTOR.id}
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_start_is_one_short_message_and_does_not_change_preferences(navigation, monkeypatch):
    bot, _, state, session = navigation
    create_user = AsyncMock(return_value=1)
    monkeypatch.setattr(start, "get_or_create_user", create_user)
    await state.set_state("OldState:year")
    await start.cmd_start(user_message(bot, "/start"), state)
    create_user.assert_awaited_once_with(ACTOR.id)
    assert len(session.methods) == 1
    assert len(session.methods[0].text) < 450
    assert len(session.methods[0].reply_markup.keyboard) == 2
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_group_start_has_no_private_keyboard_or_account_changes(navigation, monkeypatch):
    bot, _, state, session = navigation
    create_user = AsyncMock()
    monkeypatch.setattr(start, "get_or_create_user", create_user)
    message = user_message(bot, "/start").model_copy(update={"chat": Chat(id=-100123, type="supergroup")})
    await start.cmd_start(message, state)
    create_user.assert_not_awaited()
    assert session.methods[-1].reply_markup is None and "/f1" in session.methods[-1].text


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["nav:action:unknown", "nav:section:unknown", "nav:action:settings:other", "nav:"])
async def test_unknown_menu_callback_is_safe_and_does_not_clear_input(navigation, data):
    bot, dispatcher, state, session = navigation
    await state.set_state("OldState:year")
    await dispatcher.feed_update(bot, Update(update_id=1, callback_query=clicked(bot, data)))
    assert len(session.methods) == 1 and isinstance(session.methods[0], AnswerCallbackQuery)
    assert await state.get_state() == "OldState:year"


@pytest.mark.asyncio
async def test_group_callbacks_cannot_open_personal_actions(navigation):
    bot, dispatcher, state, session = navigation
    await dispatcher.feed_update(bot, Update(update_id=1, callback_query=clicked(bot, "nav:action:settings", private=False)))
    assert len(session.methods) == 1 and isinstance(session.methods[0], AnswerCallbackQuery)
    assert "личном чате" in session.methods[0].text


@pytest.mark.asyncio
async def test_miniapp_buttons_keep_exact_destinations_and_timeout_has_a_back_button(navigation, monkeypatch):
    bot, _, _, _ = navigation
    text, markup = await menu.section_content(bot, "predictions")
    assert markup.inline_keyboard[0][0].disabled is not None
    assert [button.web_app.url for row in markup.inline_keyboard for button in row if button.web_app] == [
        "https://example.test/predictions?source=telegram&tab=form",
        "https://example.test/predictions?source=telegram&tab=leaderboard",
        "https://example.test/predictions?source=telegram&tab=leagues",
    ]
    monkeypatch.setattr(menu, "destination_buttons", AsyncMock(side_effect=asyncio.TimeoutError()))
    text, markup = await menu.section_content(bot, "predictions")
    assert "временно недоступны" in text
    assert markup.inline_keyboard[-1][0].callback_data == "nav:section:home"
    monkeypatch.setattr(menu, "destination_buttons", AsyncMock(return_value=None))
    assert "временно недоступны" in (await menu.section_content(bot, "games"))[0]


@pytest.mark.asyncio
async def test_all_drivers_remain_available_in_small_editable_pages(navigation, monkeypatch):
    bot, _, _, session = navigation
    roster = pd.DataFrame([{"givenName": f"Pilot {i}", "familyName": "Family", "driverCode": f"D{i:02}"} for i in range(22)])
    monkeypatch.setattr(insights, "get_driver_standings_async", AsyncMock(return_value=roster))
    seen = []
    for page in range(4):
        await insights._driver_picker(clicked(bot, "x").message, page, edit=page > 0)
        result = session.methods[-1]
        assert isinstance(result, SendMessage if page == 0 else EditMessageText)
        rows = result.reply_markup.inline_keyboard
        pilots = [button for row in rows for button in row if (button.callback_data or "").startswith("insights:driver:")]
        assert len(pilots) <= 6 and len(rows) <= 5
        seen.extend(button.text for button in pilots)
        assert f"Страница {page + 1} из 4" in result.text
        assert rows[-1][0].callback_data == "nav:section:guides"
    assert len(seen) == len(set(seen)) == 22


@pytest.mark.asyncio
async def test_driver_page_acknowledges_before_loading_and_rejects_invalid_input(navigation, monkeypatch):
    bot, _, _, session = navigation
    picker = AsyncMock()
    monkeypatch.setattr(insights, "_driver_picker", picker)
    await insights.driver_page_callback(clicked(bot, "insights:drivers:page:1"))
    assert isinstance(session.methods[0], AnswerCallbackQuery)
    assert picker.await_args.args[1] == 1 and picker.await_args.kwargs == {"edit": True}
    picker.reset_mock()
    await insights.driver_page_callback(clicked(bot, "insights:drivers:page:bad"))
    picker.assert_not_awaited()
