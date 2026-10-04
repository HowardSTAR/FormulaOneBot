"""Bot API 10.3 integration with a local transport; no Telegram/network/working DB."""
import asyncio
from io import BytesIO
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendMessage, SendRichMessage, SendMessageDraft, SendPhoto, DeleteMessage, EditMessageText, SendChatAction, AnswerGuestQuery, AnswerCallbackQuery, GetMe
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.handlers import compare, guest, menu, telegram_features
from app.utils.activity_status import ActivityStatus, _active_statuses, stop_activity
from app.utils.telegram_presentation import race_card, race_fallback, review_card, send_card
from app.utils.time_tools import telegram_time

ACTOR = User(id=777, is_bot=False, first_name="Pilot")
BOT_USER = User(id=123456, is_bot=True, first_name="F1Hub", username="F1HubTestBot")


class LocalSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, (SendMessage, SendRichMessage, SendPhoto)):
            return Message(message_id=len(self.methods), date=datetime.now(timezone.utc),
                           chat=Chat(id=method.chat_id, type="private" if method.chat_id > 0 else "supergroup"),
                           from_user=BOT_USER, text=getattr(method, "text", None)).as_(bot)
        return True

    async def stream_content(self, url, **kwargs):
        yield b""


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("TELEGRAM_RICH_MESSAGES", "1")
    monkeypatch.setenv("TELEGRAM_GUEST_MODE", "1")
    session = LocalSession()
    bot = Bot("123456:LOCAL_TEST", session=session)
    return bot, session


def message(bot, text="Test", *, group=False):
    return Message(message_id=20, date=datetime.now(timezone.utc), from_user=BOT_USER,
                   chat=Chat(id=-100123 if group else ACTOR.id, type="supergroup" if group else "private"), text=text).as_(bot)


def callback(bot, data="personal:review:2026:15", *, group=False):
    return CallbackQuery(id="private-request", from_user=ACTOR, chat_instance="test",
                         message=message(bot, group=group), data=data).as_(bot)


def loading_callback(bot, session):
    sent = next(m for m in session.methods if isinstance(m, SendMessage) and m.text.startswith("⏳"))
    status = message(bot).model_copy(update={"message_id": session.methods.index(sent) + 1,
                                             "reply_markup": sent.reply_markup})
    return callback(bot, sent.reply_markup.inline_keyboard[0][0].callback_data).model_copy(update={"message": status}).as_(bot)


def review():
    return {"event_name": "Test <GP>", "points": 2, "max_points": 4, "items": [
        {"key": "first_retirement_driver", "label": "Первый сход", "predicted": "BOT", "actual": ["BOT", "NOR"],
         "status": "exact", "points": 2, "maximum": 2, "reason": "Первая группа схода: +2."},
        {"key": "fastest_lap_driver", "label": "Лучший круг", "predicted": "RUS", "actual": None,
         "status": "unavailable", "points": 0, "maximum": 0, "reason": "Факт ещё не установлен."},
        {"key": "safety_car", "label": "SC", "predicted": 1, "actual": 0,
         "status": "miss", "points": 0, "maximum": 2, "reason": "Нет совпадения."},
    ]}


def test_cards_are_compact_and_full_classification_is_collapsed():
    rows = [{"pos": i, "driver": f"Pilot {i}", "points": 25 if i == 1 else 0} for i in range(1, 23)]
    card = race_card("Test GP", 2026, 15, rows, {"items": [{"title": "Story", "text": "Verified fact"}]})
    tables = [b for b in card.blocks if b.type == "table"]
    assert len(tables[0].cells) == 6 and tables[0].is_compact
    details = next(b for b in card.blocks if b.type == "details")
    assert not details.is_open and len(details.blocks[0].cells) == 23
    assert "Pilot 22" in race_fallback("Test GP", 2026, 15, rows, {"items": []})


def test_race_image_replaces_tables_and_keeps_recap_and_news(local):
    from aiogram.types import BufferedInputFile
    bot, session = local
    rows = [{"pos": i, "driver": f"Pilot {i}", "points": 25 if i == 1 else 0} for i in range(1, 23)]
    recap = {"items": [{"title": "Winner", "text": "Verified points"}],
             "chronicle": [{"title": "Lap 9: Safety car"}],
             "news": [{"title": "Race report", "url": "https://example.com/report", "publisher": "Source"}]}
    card = race_card("Test GP", 2026, 16, rows, recap, photo=BufferedInputFile(b"png-test", filename="results.png"))
    assert [b.type for b in card.blocks].count("photo") == 1
    assert not any(b.type in {"table", "details"} for b in card.blocks)
    blocks = [b.text for b in card.blocks if hasattr(b, "text")]
    assert "Winner" in blocks and "Verified points" in blocks and "Lap 9: Safety car" in blocks
    assert any(isinstance(text, list) and text[0].url == "https://example.com/report" for text in blocks)
    files = {}
    payload = session.prepare_value(card, bot=bot, files=files)
    assert len(files) == 1 and next(iter(files.values())).data == b"png-test"
    assert "attach://" in payload


def test_review_keeps_unknown_data_and_multiple_first_retirements_distinct():
    card, fallback = review_card(review())
    data = card.model_dump_json()
    assert "BOT, NOR" in data and "Нет данных" in data and "Ожидаем данные" in data
    assert "&lt;GP&gt;" in fallback and "Test <GP>" not in fallback
    assert not next(b for b in card.blocks if b.type == "details").is_open
    assert "2/4" in fallback and "Да" in fallback and "Нет" in fallback


def test_native_time_is_utc_based_and_has_an_absolute_fallback():
    a = telegram_time("2026-10-08T12:00:00Z", "Europe/Moscow")
    b = telegram_time("2026-10-08T15:00:00+03:00", "Europe/Moscow")
    assert a == b and 'format="wDt"' in a and "15:00" in a
    assert 'format="r"' in telegram_time("2026-10-08T12:00:00Z", relative=True)
    assert telegram_time("<bad>") == "&lt;bad&gt;"
    assert "уточняется" in telegram_time(None)


@pytest.mark.asyncio
async def test_button_colors_follow_action_semantics_without_coloring_cancel():
    from app.handlers.account_link import _confirmation_keyboard
    from app.handlers.settings import get_notify_keyboard
    from app.handlers.favorites import ask_clear_drivers
    confirmation = _confirmation_keyboard("hint", conflict=False).inline_keyboard
    assert confirmation[0][0].style == "success" and confirmation[-1][0].style is None
    intervals = [b for row in get_notify_keyboard(60).inline_keyboard for b in row]
    assert next(b for b in intervals if b.callback_data == "set_not:60").style == "success"
    assert all(b.style is None for b in intervals if b.callback_data.startswith("set_not:") and b.callback_data != "set_not:60")
    assert next(b for b in intervals if b.callback_data == "back_to_settings").style == "primary"
    edit = AsyncMock()
    await ask_clear_drivers(SimpleNamespace(message=SimpleNamespace(edit_text=edit)))
    actions = edit.await_args.kwargs["reply_markup"].inline_keyboard[0]
    assert actions[0].style == "danger" and actions[1].style is None


@pytest.mark.asyncio
async def test_rich_fallback_keeps_personal_receiver_and_does_not_retry_ambiguous_send():
    card, text = review_card(review())
    method = SendRichMessage(chat_id=-1, rich_message=card)
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=TelegramBadRequest(method=method, message="rich message is not supported")), send_message=AsyncMock())
    receiver = {"receiver_user_id": 777, "callback_query_id": "q"}
    await send_card(bot, -1, card, text, ephemeral_message_parameters=receiver, protect_content=True)
    assert bot.send_message.await_args.kwargs["ephemeral_message_parameters"] == receiver
    assert bot.send_message.await_args.kwargs["protect_content"]
    bot.send_message.reset_mock()
    bot.send_rich_message.side_effect = TelegramNetworkError(method=method, message="timeout")
    with pytest.raises(TelegramNetworkError):
        await send_card(bot, -1, card, text)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [False, True])
async def test_real_dispatcher_binds_review_to_clicker_not_message_author(local, monkeypatch, group):
    bot, session = local
    lookup, load = AsyncMock(return_value=42), AsyncMock(return_value=review())
    monkeypatch.setattr(telegram_features, "linked_user_id", lookup)
    monkeypatch.setattr(telegram_features, "get_personal_prediction_review", load)
    dispatcher, router = Dispatcher(), Router()
    router.callback_query.register(telegram_features.personal_view, F.data.startswith("personal:"))
    dispatcher.include_router(router)
    await dispatcher.feed_update(bot, Update(update_id=1, callback_query=callback(bot, group=group)))
    lookup.assert_awaited_once_with(ACTOR.id)
    load.assert_awaited_once_with(42, 2026, 15)
    sent = session.methods[-1]
    assert isinstance(sent, SendRichMessage) and sent.protect_content
    if group:
        assert sent.chat_id == -100123
        assert sent.ephemeral_message_parameters.receiver_user_id == ACTOR.id
        assert sent.ephemeral_message_parameters.callback_query_id == "private-request"
        assert sent.ephemeral_message_parameters.replace_callback_query_message
    else:
        assert sent.chat_id == ACTOR.id and sent.ephemeral_message_parameters is None
    assert not any(m.__api_method__.startswith("edit") for m in session.methods)


@pytest.mark.asyncio
async def test_rejected_ephemeral_message_never_becomes_public(local, monkeypatch):
    bot, session = local
    monkeypatch.setattr(telegram_features, "linked_user_id", AsyncMock(return_value=42))
    monkeypatch.setattr(telegram_features, "get_personal_prediction_review", AsyncMock(return_value=review()))
    send = AsyncMock(side_effect=TelegramBadRequest(method=SendMessage(chat_id=-1, text="test"), message="callback expired"))
    monkeypatch.setattr(bot, "send_rich_message", send)
    await telegram_features.personal_view(callback(bot, group=True))
    assert not any(isinstance(m, SendMessage) for m in session.methods)
    assert send.await_args.kwargs["ephemeral_message_parameters"].receiver_user_id == ACTOR.id


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["personal:review:2026:15:42", "personal:review:2026:99", "personal:admin:2026:15"])
async def test_forged_personal_callbacks_are_rejected(local, monkeypatch, data):
    lookup = AsyncMock()
    monkeypatch.setattr(telegram_features, "linked_user_id", lookup)
    await telegram_features.personal_view(callback(local[0], data, group=True))
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_archived_user_is_not_created_or_reactivated(temp_db_path, monkeypatch):
    from app.db import Database
    database = Database(temp_db_path)
    await database.connect()
    try:
        await database.init_tables()
        await database.conn.execute("INSERT INTO users(telegram_id, archived_at) VALUES(777,'archived')")
        await database.conn.commit()
        monkeypatch.setattr(telegram_features, "db", database)
        assert await telegram_features.linked_user_id(777) is None
        assert await telegram_features.linked_user_id(888) is None
        assert (await (await database.conn.execute("SELECT COUNT(*) FROM users")).fetchone())[0] == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_league_response_does_not_expose_invitation_tokens(local, monkeypatch):
    bot, session = local
    monkeypatch.setattr(telegram_features, "linked_user_id", AsyncMock(return_value=42))
    monkeypatch.setattr(telegram_features, "list_leagues", AsyncMock(return_value=[{"name": "Friends <league>", "invite_token": "SECRET"}]))
    await telegram_features.personal_view(callback(bot, "personal:leagues:2026:15", group=True))
    sent = session.methods[-1]
    assert isinstance(sent, SendMessage) and "SECRET" not in sent.text and "&lt;league&gt;" in sent.text
    assert sent.ephemeral_message_parameters.receiver_user_id == 777


@pytest.mark.asyncio
async def test_loading_stop_cancels_work_only_for_matching_bot_chat_actor_and_message(local):
    bot, session = local
    entered, child_cancelled = asyncio.Event(), asyncio.Event()
    after = []
    async def child():
        try:
            await asyncio.sleep(60)
        finally:
            child_cancelled.set()
    async def work():
        async with ActivityStatus(message(bot), "Загружаю архив…") as loader:
            await loader.update("Получено 4 из 10 сезонов")
            entered.set()
            await child()
        after.append("must not run")
    task = asyncio.create_task(work())
    await entered.wait()
    sent = next(m for m in session.methods if isinstance(m, SendMessage))
    event = loading_callback(bot, session)
    assert not stop_activity(bot.id + 1, event)
    assert not stop_activity(bot.id, event.model_copy(update={"message": event.message.model_copy(update={"chat": Chat(id=888, type="private")})}))
    assert not stop_activity(bot.id, event.model_copy(update={"from_user": User(id=888, is_bot=False, first_name="Other")}))
    assert not stop_activity(bot.id, event.model_copy(update={"from_user": BOT_USER}))
    assert not stop_activity(bot.id, event.model_copy(update={"message": event.message.model_copy(update={"message_id": 999})}))
    assert not stop_activity(bot.id, event.model_copy(update={"data": "activity:stop:wrong"}))
    assert not stop_activity(bot.id, event.model_copy(update={"data": event.data.removeprefix("activity:stop:")}))
    assert not stop_activity(bot.id, event.model_copy(update={"message": message(bot, group=True)}))
    dispatcher, router = Dispatcher(), Router()
    router.callback_query.register(telegram_features.cancel_activity, F.data.startswith("activity:stop:"))
    dispatcher.include_router(router)
    await dispatcher.feed_update(bot, Update(update_id=2, callback_query=event))
    with pytest.raises(asyncio.CancelledError):
        await task
    assert child_cancelled.is_set() and not after and not _active_statuses
    assert "остановлен" in session.methods[-1].text
    assert sent.reply_markup.inline_keyboard[0][0].text == "Остановить загрузку" and '%' not in sent.text
    assert not stop_activity(bot.id, event)  # an old Stop button cannot cancel another request


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["text", "card", "photo"])
async def test_loading_message_is_deleted_after_any_result_without_a_lingering_draft(local, kind):
    bot, session = local
    async with ActivityStatus(message(bot), "Готовлю…") as loader:
        if kind == "text":
            result = await bot.send_message(chat_id=777, text="Готовый результат")
        elif kind == "card":
            card, text = review_card(review())
            result = await send_card(bot, 777, card, text)
        else:
            result = await bot.send_photo(chat_id=777, photo="LOCAL_TEST_PHOTO")
    assert isinstance(session.methods[0], SendMessage)
    assert "Готовлю" in session.methods[0].text
    assert isinstance(session.methods[-1], DeleteMessage)
    assert session.methods[-1].message_id == loader.status.message_id != result.message_id
    assert not any(isinstance(m, SendMessageDraft) for m in session.methods)
    assert not any(isinstance(m, SendChatAction) for m in session.methods)
    assert session.methods[0].disable_notification
    assert loader.task.done()
    assert not _active_statuses


@pytest.mark.asyncio
async def test_failed_loading_is_deleted_without_hiding_the_original_error(local):
    bot, session = local
    with pytest.raises(RuntimeError, match="source failed"):
        async with ActivityStatus(message(bot), "Загружаю…"):
            raise RuntimeError("source failed")
    assert isinstance(session.methods[-1], DeleteMessage) and not _active_statuses


@pytest.mark.asyncio
async def test_failed_deletion_retires_label_and_stop_button_instead_of_leaving_loading(local, monkeypatch):
    bot, session = local
    original = session.make_request
    async def request(active_bot, method, timeout=None):
        if isinstance(method, DeleteMessage):
            raise TelegramBadRequest(method=method, message="cannot delete")
        return await original(active_bot, method, timeout=timeout)
    monkeypatch.setattr(session, "make_request", request)
    async with ActivityStatus(message(bot), "Загружаю…"):
        await bot.send_message(chat_id=777, text="Результат")
    ended = session.methods[-1]
    assert isinstance(ended, EditMessageText)
    assert ended.text == "Загрузка завершена." and ended.reply_markup is None
    assert ended.message_id == 1 and not _active_statuses


@pytest.mark.asyncio
async def test_progress_keeps_stop_button_and_cannot_restart_completed_loading(local):
    bot, session = local
    async with ActivityStatus(message(bot), "Загружаю…") as loader:
        await loader.update("Получено 2 из 3 этапов")
        progress = session.methods[-1]
        assert isinstance(progress, EditMessageText)
        assert progress.reply_markup == session.methods[0].reply_markup
        old_button = loading_callback(bot, session)
    calls = len(session.methods)
    await loader.update("Запоздавший прогресс")
    await asyncio.sleep(0)  # yield to any pending cleanup
    assert len(session.methods) == calls and loader.task.done() and not _active_statuses
    await telegram_features.cancel_activity(old_button)
    assert isinstance(session.methods[-1], AnswerCallbackQuery)
    assert session.methods[-1].text == "Загрузка уже завершена."
    assert len(session.methods) == calls + 1


@pytest.mark.asyncio
async def test_group_loading_is_deletable_but_never_offers_private_cancellation(local):
    bot, session = local
    async with ActivityStatus(message(bot, group=True), "Загружаю…"):
        assert session.methods[0].reply_markup is None and not _active_statuses
    assert isinstance(session.methods[-1], DeleteMessage)
    assert session.methods[-1].chat_id == -100123


@pytest.mark.asyncio
async def test_loading_ui_failure_does_not_block_the_actual_result(local, monkeypatch):
    bot, session = local
    original = session.make_request
    async def request(active_bot, method, timeout=None):
        if isinstance(method, SendMessage) and method.text.startswith("⏳"):
            raise TelegramNetworkError(method=method, message="timeout")
        return await original(active_bot, method, timeout=timeout)
    monkeypatch.setattr(session, "make_request", request)
    async with ActivityStatus(message(bot), "Загружаю…") as loader:
        await bot.send_message(chat_id=777, text="Результат")
    assert loader.status is None and loader.task is None and not _active_statuses
    assert len(session.methods) == 1 and session.methods[0].text == "Результат"


@pytest.mark.asyncio
async def test_external_cancellation_is_not_suppressed(local):
    bot, session = local
    with pytest.raises(asyncio.CancelledError):
        async with ActivityStatus(message(bot), "Готовлю…"):
            raise asyncio.CancelledError
    assert not _active_statuses and isinstance(session.methods[-1], DeleteMessage)


@pytest.mark.asyncio
async def test_stopping_comparison_cancels_all_pending_race_requests(local, monkeypatch):
    bot, session = local
    entered, cancelled, ready = [], [], asyncio.Event()
    async def race_request(year, round_num=None):
        if round_num is None:
            return pd.DataFrame([{"driverCode": "ALO", "points": 25}, {"driverCode": "HAM", "points": 25}])
        entered.append(round_num)
        if len(entered) == 2:
            ready.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(round_num)
    monkeypatch.setattr(compare, "get_season_schedule_short_async", AsyncMock(return_value=[
        {"round": 1, "event_name": "First GP"}, {"round": 2, "event_name": "Second GP"}]))
    monkeypatch.setattr(compare, "get_driver_standings_async", race_request)
    render = AsyncMock()
    monkeypatch.setattr(compare, "create_comparison_image", render)
    task = asyncio.create_task(compare.send_comparison_graph(message(bot), "ALO", "HAM", 2025))
    await asyncio.wait_for(ready.wait(), timeout=2)
    assert stop_activity(bot.id, loading_callback(bot, session))
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sorted(cancelled) == [1, 2] and not _active_statuses
    render.assert_not_called()


@pytest.mark.asyncio
async def test_parallel_comparison_keeps_points_in_schedule_order(local, monkeypatch):
    rendered = []
    second_done = asyncio.Event()
    async def race_request(year, round_num=None):
        if round_num is None:
            return pd.DataFrame([{"driverCode": "ALO", "points": 25}, {"driverCode": "HAM", "points": 50}])
        if round_num == 1:
            await second_done.wait()
        else:
            second_done.set()
        return pd.DataFrame([{"driverCode": "ALO", "points": 25},
                             {"driverCode": "HAM", "points": 0 if round_num == 1 else 50}])
    def image(data1, data2, labels):
        rendered.append((data1["history"], data2["history"], labels))
        return BytesIO(b"local-image")
    monkeypatch.setattr(compare, "get_season_schedule_short_async", AsyncMock(return_value=[
        {"round": 1, "event_name": "First Grand Prix"}, {"round": 2, "event_name": "Second Grand Prix"}]))
    monkeypatch.setattr(compare, "get_driver_standings_async", race_request)
    monkeypatch.setattr(compare, "create_comparison_image", image)
    await compare.send_comparison_graph(message(local[0]), "ALO", "HAM", 2025)
    assert rendered == [([25, 25], [0, 50], ["First", "Second"])]


@pytest.mark.asyncio
async def test_loading_does_not_depend_on_draft_api(local, monkeypatch):
    bot, session = local
    monkeypatch.setattr(bot, "send_message_draft", AsyncMock(side_effect=TelegramBadRequest(method=SendMessageDraft(chat_id=777, draft_id=1, text="test"), message="unsupported")))
    async with ActivityStatus(message(bot), "Загружаю…") as loader:
        assert loader.status is not None
    assert isinstance(session.methods[0], SendMessage) and "Загружаю" in session.methods[0].text
    bot.send_message_draft.assert_not_awaited()


@pytest.mark.parametrize("query, kind", [("@F1HubTestBot следующая гонка", "next"), ("итоги гонки", "recap"), ("/driver ALO 1997", "driver"), ("сравни ALO HAM", "compare"), ("что такое VSC?", "term"), ("/broadcast attack", "help"), ("мой прогноз", "help"), ("/driver ALO 2026 extra", "help")])
def test_guest_query_is_a_strict_public_allowlist(query, kind):
    assert guest.parse_query(query, "F1HubTestBot")[0] == kind


@pytest.mark.asyncio
async def test_guest_update_uses_answer_guest_query_not_regular_send(local, monkeypatch):
    bot, session = local
    guest._recent.clear()
    incoming = message(bot, "@F1HubTestBot что такое VSC", group=True).model_copy(update={"guest_query_id": "guest1", "guest_bot_caller_user": ACTOR})
    dispatcher, router = Dispatcher(), Router()
    router.guest_message.register(guest.guest_message)
    dispatcher.include_router(router)
    await dispatcher.feed_update(bot, Update(update_id=1, guest_message=incoming))
    sent = session.methods[-1]
    assert isinstance(sent, AnswerGuestQuery) and sent.guest_query_id == "guest1"
    assert "виртуальная" in sent.result.input_message_content.message_text
    assert not any(isinstance(m, (SendMessage, SendRichMessage)) for m in session.methods)
    assert "guest_message" in dispatcher.resolve_used_update_types()


@pytest.mark.asyncio
async def test_guest_comparison_uses_same_standings_source(local, monkeypatch):
    frame = pd.DataFrame([{"driverId": "alonso", "driverCode": "ALO", "givenName": "Fernando", "familyName": "Alonso", "position": 5, "points": 100},
                          {"driverId": "hamilton", "driverCode": "HAM", "givenName": "Lewis", "familyName": "Hamilton", "position": 2, "points": 200}])
    fetch = AsyncMock(return_value=frame)
    monkeypatch.setattr(guest, "get_driver_standings_async", fetch)
    text = await guest.public_answer("compare", ["ALO", "HAM", "2025"])
    fetch.assert_awaited_once_with(2025)
    assert "100" in text and "200" in text and "включая спринты" in text


def test_guest_throttle_is_bounded():
    guest._recent.clear()
    assert guest.allowed_rate(1, 777, -1)
    assert not guest.allowed_rate(1, 777, -1)
    for i in range(3000):
        guest.allowed_rate(1, i, -2)
    assert len(guest._recent) <= 2048


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["before", "open", "closed", "unknown"])
async def test_prediction_menu_states_are_explanatory_without_disabling_readonly_view(local, monkeypatch, state):
    now = datetime.now(timezone.utc)
    context = {"status": "ok", "is_open": state == "open", "opens_at_utc": (now + timedelta(days=1) if state == "before" else now - timedelta(days=1)).isoformat(),
               "deadline_utc": (now - timedelta(hours=1) if state == "closed" else now + timedelta(hours=1)).isoformat()}
    monkeypatch.setattr(menu, "get_prediction_context", AsyncMock(return_value={} if state == "unknown" else context))
    monkeypatch.setenv("MINI_APP_URL", "https://example.test")
    text, keyboard = await menu.section_content(local[0], "predictions")
    disabled = [button for row in keyboard.inline_keyboard for button in row if button.disabled is not None]
    web = [button for row in keyboard.inline_keyboard for button in row if button.web_app]
    assert len(disabled) == (0 if state == "open" else 1)
    assert web[0].web_app.url.endswith("tab=form")
    if state in {"open", "before"}:
        assert "tg-time" in text
