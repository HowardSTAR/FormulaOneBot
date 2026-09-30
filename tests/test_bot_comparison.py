from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendMessage, SendPhoto, AnswerCallbackQuery
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.handlers import compare, drivers
from app.services.bot_comparison import load_points_series, participant_points

ACTOR = User(id=777, is_bot=False, first_name="Pilot")
BOT_USER = User(id=123456, is_bot=True, first_name="F1Hub", username="F1HubTestBot")


class LocalSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods = []
    async def close(self):
        pass
    async def stream_content(self, url, **kwargs):
        yield b""
    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, (SendMessage, SendPhoto)):
            return Message(message_id=len(self.methods), date=datetime.now(timezone.utc),
                           chat=Chat(id=777, type="private"), from_user=BOT_USER,
                           text=getattr(method, "text", None)).as_(bot)
        return True


def frame(kind="drivers", points=(33, 18), round_num=2):
    if kind == "drivers":
        result = pd.DataFrame([{"driverId": "alonso", "driverCode": "ALO", "givenName": "Fernando", "familyName": "Alonso", "points": points[0]},
                               {"driverId": "hamilton", "driverCode": "HAM", "givenName": "Lewis", "familyName": "Hamilton", "points": points[1]}])
    else:
        result = pd.DataFrame([{"constructorId": "mercedes", "constructorName": "Mercedes", "points": points[0]},
                               {"constructorId": "ferrari", "constructorName": "Ferrari", "points": points[1]}])
    result.attrs["round"] = round_num
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["drivers", "teams"])
async def test_actual_dispatcher_season_pair_and_graph_not_standings(monkeypatch, kind):
    session = LocalSession()
    bot = Bot("123456:LOCAL_TEST", session=session)
    dp, driver_router, comparison = Dispatcher(), Router(), Router()
    # Same ordering as main: driver's broad callback used to steal compare's year.
    driver_router.callback_query.register(drivers.drivers_year_current, F.data.startswith("drivers_current_"))
    comparison.message.register(compare.cmd_compare, F.text == "/compare")
    comparison.message.register(compare.process_compare_year, compare.CompareState.waiting_for_year)
    comparison.callback_query.register(compare.comparison_callback, F.data.startswith("cmp:"))
    dp.include_routers(driver_router, comparison)
    fetch = AsyncMock(return_value=frame(kind))
    monkeypatch.setattr(compare, "get_driver_standings_async" if kind == "drivers" else "get_constructor_standings_async", fetch)
    favorite_lookup = AsyncMock(return_value=[])
    monkeypatch.setattr(compare, "get_favorite_drivers", favorite_lookup)
    graph = AsyncMock()
    monkeypatch.setattr(compare, "send_comparison_graph", graph)
    never_standings = AsyncMock()
    monkeypatch.setattr(drivers, "_send_drivers_for_year", never_standings)
    state = dp.fsm.get_context(bot, chat_id=777, user_id=777)
    incoming = Message(message_id=1, date=datetime.now(timezone.utc), from_user=ACTOR,
                       chat=Chat(id=777, type="private"), text="/compare")
    await dp.feed_update(bot, Update(update_id=1, message=incoming))
    counter = 1
    async def click(data):
        nonlocal counter
        counter += 1
        reply = incoming.model_copy(update={"from_user": BOT_USER, "text": "Bot's menu"})
        cb = CallbackQuery(id=f"q{counter}", from_user=ACTOR, chat_instance="test", message=reply, data=data)
        await dp.feed_update(bot, Update(update_id=counter, callback_query=cb))
    nonce = (await state.get_data())["nonce"]
    await click(f"cmp:kind:{nonce}:{kind}")
    year_message = next(method for method in reversed(session.methods) if isinstance(method, SendMessage))
    assert year_message.reply_markup.inline_keyboard[0][0].callback_data.startswith("cmp:year:")
    await click(f"drivers_current_{datetime.now().year}")  # even a leftover old button cannot hijack this flow
    never_standings.assert_not_awaited()
    await click(f"cmp:year:{nonce}:2025")
    assert await state.get_state() == compare.CompareState.waiting_for_driver_1.state
    graph.assert_not_awaited()
    await click(f"cmp:pick:{nonce}:0")
    second_data = await state.get_data()
    assert all(b.callback_data != f"cmp:pick:{nonce}:0" for row in compare._picker(second_data, True).inline_keyboard for b in row)
    await click(f"cmp:pick:{nonce}:0")  # forged repeated participant
    graph.assert_not_awaited()
    await click(f"cmp:pick:{nonce}:1")
    graph.assert_awaited_once()
    args, kwargs = graph.await_args
    assert args[0].from_user.id == ACTOR.id and args[3] == 2025 and kwargs["kind"] == kind
    assert {args[1], args[2]} == ({"alonso", "hamilton"} if kind == "drivers" else {"mercedes", "ferrari"})
    assert await state.get_state() is None
    never_standings.assert_not_awaited()
    if kind == "drivers":
        favorite_lookup.assert_awaited_once_with(ACTOR.id)


def test_picker_is_paged_and_callbacks_use_indices_not_historical_codes():
    participants = [{"id": f"driver_{i}", "code": "SAM", "name": f"Pilot {i}"} for i in range(23)]
    data = {"nonce": "token", "kind": "drivers", "participants": participants, "first": 0, "year": 1997}
    all_choices = []
    for page in range(3):
        keyboard = compare._picker(data, page=page)
        choices = [b.callback_data for row in keyboard.inline_keyboard for b in row if (b.callback_data or "").startswith("cmp:pick:")]
        assert len(choices) <= 8
        all_choices.extend(choices)
    assert len(all_choices) == len(set(all_choices)) == 23


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,ids", [("drivers", ["alonso", "hamilton"]), ("teams", ["mercedes", "ferrari"])])
async def test_points_include_sprint_and_latest_equals_table(kind, ids):
    snapshots = {1: frame(kind, (33, 18), 1), 2: frame(kind, (40, 43), 2)}
    async def fetch(year, round_num=None):
        return snapshots[round_num or 2]
    result = await load_points_series(2025, kind, ids, [{"round": 2}, {"round": 1}, {"round": 3}], fetch)
    assert [e["round"] for e in result["events"]] == [1, 2]
    assert result["histories"] == [[33, 40], [18, 43]]  # includes 8 sprint points, not a race-only sum
    assert result["totals"] == [40, 43] and result["missing"] == 0


@pytest.mark.asyncio
async def test_missing_snapshot_is_gap_and_legitimate_absence_is_zero():
    async def fetch(year, round_num=None):
        if round_num == 1:
            return pd.DataFrame()
        return frame(round_num=2)
    result = await load_points_series(2025, "drivers", ["alonso", "hamilton"], [{"round": 1}, {"round": 2}], fetch)
    assert result["histories"] == [[None, 33], [None, 18]] and result["missing"] == 1
    assert participant_points(frame(), "new_driver", "drivers") == 0
    assert participant_points(pd.DataFrame(), "new_driver", "drivers") is None
    assert participant_points(pd.DataFrame([{"points": 12}]), "new_driver", "drivers") is None


@pytest.mark.asyncio
async def test_snapshot_from_another_round_is_not_relabelled():
    async def fetch(year, round_num=None):
        return frame(round_num=2)
    result = await load_points_series(2025, "drivers", ["alonso", "hamilton"], [{"round": 1}, {"round": 2}], fetch)
    assert result["histories"][0] == [None, 33]


@pytest.mark.asyncio
async def test_same_three_letter_code_still_matches_stable_driver_identity():
    standings = pd.DataFrame([{"driverId": "first", "driverCode": "SAM", "points": 10},
                              {"driverId": "second", "driverCode": "SAM", "points": 20}])
    assert participant_points(standings, "first", "drivers") == 10
    assert participant_points(standings, "second", "drivers") == 20
    assert participant_points(standings, "SAM", "drivers") is None
