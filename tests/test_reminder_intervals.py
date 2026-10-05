"""No live API calls, Telegram messages or production database writes."""
import asyncio
from itertools import combinations
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from app.session_reminders import interval_mask, reminder_intervals, reminder_enabled


@pytest.mark.parametrize("selected", [list(values) for size in range(6)
    for values in combinations([15,30,60,120,1440],size)]+[[60,15,60]],ids=lambda values:'intervals-'+('-'.join(map(str,values)) or 'disabled'))
def test_mask_roundtrip(selected):
    assert reminder_intervals(interval_mask(selected)) == sorted(set(selected))
    assert reminder_intervals(None, 1440) == [1440]
    assert reminder_intervals(0, 1440) == []


@pytest.mark.parametrize("invalid", [[True], [False], [15.0], ["60"], [0], [-1], [31], [1441], "60", None, (60,), {}],
                         ids=['true','false','float','string-member','zero','negative','unsupported','above-max','string','null','tuple','object'])
def test_invalid_intervals(invalid):
    with pytest.raises(ValueError):
        interval_mask(invalid)


def test_pending_interval_filter():
    mask = interval_mask([15, 1440])
    assert reminder_enabled(mask, 60, "reminder:2026:15:race:15:42")
    assert reminder_enabled(mask, 60, "reminder:2026:15:race:1440")
    assert not reminder_enabled(mask, 60, "reminder:2026:15:race:60")
    assert not reminder_enabled(0, 60, "reminder:2026:15:race:60")
    assert not reminder_enabled(None, 60, "invalid")


@pytest.mark.asyncio
async def test_migration_keeps_legacy_value_and_explicit_selection(tmp_path):
    from app.auth_schema import CREATE_USERS_SQL, ensure_auth_schema
    async with aiosqlite.connect(tmp_path / "legacy.db") as conn:
        await conn.execute("\n".join(line for line in CREATE_USERS_SQL.splitlines() if "notify_before_mask" not in line))
        await conn.execute("INSERT INTO users(telegram_id,notify_before) VALUES(42,1440)")
        await conn.commit()
        await ensure_auth_schema(conn)
        row = await (await conn.execute("SELECT notify_before_mask,notify_before FROM users")).fetchone()
        assert reminder_intervals(*row) == [1440]
        await conn.execute("UPDATE users SET notify_before_mask=0")
        await conn.commit()
        await ensure_auth_schema(conn)
        row = await (await conn.execute("SELECT notify_before_mask,notify_before FROM users")).fetchone()
        assert reminder_intervals(*row) == []


@pytest.mark.asyncio
async def test_api_bot_roundtrip_legacy_omission_and_empty(api_client):
    from app.db import get_user_settings, toggle_notification_interval
    body = dict(timezone="UTC", notify_before=60, notifications_enabled=False, notify_before_minutes=[1440, 60, 15, 60])
    assert (await api_client.get("/api/account/settings")).json()["notify_before_minutes"] == [60]
    assert (await api_client.post("/api/account/settings", json=body)).status_code == 200
    assert (await get_user_settings(999888))["notify_before_minutes"] == [15, 60, 1440]
    legacy = {key: value for key, value in body.items() if key != "notify_before_minutes"}
    for endpoint in ("/api/account/settings", "/api/settings"):
        assert (await api_client.post(endpoint, json=legacy)).status_code == 200
        assert (await get_user_settings(999888))["notify_before_minutes"] == [15, 60, 1440]
    await toggle_notification_interval(999888, 30)
    assert (await api_client.get("/api/account/settings")).json()["notify_before_minutes"] == [15, 30, 60, 1440]
    assert (await api_client.post("/api/settings", json=body | {"notify_before_minutes": []})).status_code == 200
    assert (await api_client.get("/api/account/settings")).json()["notify_before_minutes"] == []
    for invalid in ([True], [15.0], ["60"], [0], [2000], "60"):
        assert (await api_client.post("/api/account/settings", json=body | {"notify_before_minutes": invalid})).status_code == 422


@pytest.mark.asyncio
async def test_concurrent_bot_toggles_keep_other_selections(api_client):
    from app.db import get_user_settings, toggle_notification_interval
    await asyncio.gather(*(toggle_notification_interval(999888, value) for value in (15, 30, 120, 1440)))
    assert (await get_user_settings(999888))["notify_before_minutes"] == [15, 30, 60, 120, 1440]


@pytest.mark.asyncio
async def test_bot_selection_stays_open_and_highlights_all(api_client):
    from app.handlers.settings import cb_set_notify, SettingsSG, get_notify_keyboard
    from app.db import get_user_settings
    callback = SimpleNamespace(data="set_not:15", from_user=SimpleNamespace(id=999888),
                               answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock()))
    state = AsyncMock()
    await cb_set_notify(callback, state)
    state.set_state.assert_awaited_once_with(SettingsSG.choosing_notify)
    assert (await get_user_settings(999888))["notify_before_minutes"] == [15, 60]
    keyboard = get_notify_keyboard([15, 60, 1440])
    selected = [b.callback_data for row in keyboard.inline_keyboard for b in row if b.style == "success"]
    assert selected == ["set_not:15", "set_not:60", "set_not:1440"]
    await cb_set_notify(callback, state)
    assert (await get_user_settings(999888))["notify_before_minutes"] == [60]
    callback.data = "set_not:bad"
    await cb_set_notify(callback, state)
    assert (await get_user_settings(999888))["notify_before_minutes"] == [60]


@pytest.mark.asyncio
async def test_bot_sends_each_interval_once_and_no_unselected(monkeypatch):
    from app.utils import notifications as n
    clock = datetime(2026, 10, 2, 10, tzinfo=timezone.utc)
    start = clock + timedelta(minutes=1440)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock
    monkeypatch.setattr(n, "datetime", Clock)
    monkeypatch.setattr(n, "get_season_schedule_short_async", AsyncMock(return_value=[dict(round=16, event_name="Test", race_start_utc=start.isoformat())]))
    monkeypatch.setattr(n, "get_users_with_settings", AsyncMock(return_value=[(1,"UTC",60,0,31,0,interval_mask([15,60,1440])), (2,"UTC",60,1,31,0,0)]))
    monkeypatch.setattr(n, "get_all_group_chats", AsyncMock(return_value=[]))
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(n, "safe_send_message", sent)
    seen = set()
    async def was(*key): return key in seen
    async def mark(*key): seen.add(key)
    monkeypatch.setattr(n, "was_reminder_sent", was)
    monkeypatch.setattr(n, "set_reminder_sent", mark)
    for minutes in (1440, 120, 60, 30, 15):
        clock = start - timedelta(minutes=minutes)
        await n.check_and_send_notifications(None)
        await n.check_and_send_notifications(None)
    assert sent.await_count == 3
    assert [call.kwargs["delivery_key"] for call in sent.await_args_list] == [f"reminder:2026:16:race:{minutes}" for minutes in (1440,60,15)]
    assert all(call.args[1] == 1 for call in sent.await_args_list)


@pytest.mark.asyncio
async def test_pending_telegram_removed_interval_is_cancelled(api_client):
    from app.db import db
    from app.services.delivery_adapters import queued_message
    from app.services.telegram_outbox import drain, delivery_counts
    key = "reminder:2026:16:race:60"
    bot = SimpleNamespace(send_message=AsyncMock())
    await queued_message(bot, 999888, "Test", delivery_key=key)
    await db.conn.execute("UPDATE users SET notify_before_mask=? WHERE telegram_id=999888", (interval_mask([15,1440]),))
    await db.conn.commit()
    await drain(bot)
    assert await delivery_counts(f"{key}:999888") == {"cancelled": 1}
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_intervals_do_not_bypass_prediction_closing_suppression(monkeypatch):
    from app.utils import notifications as n
    when = (datetime.now(timezone.utc) + timedelta(minutes=120)).isoformat()
    event = dict(round=16, event_name="Test", quali_start_utc=when, race_start_utc=when,
                 practice1_start_utc=(datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat())
    monkeypatch.setattr(n, "get_season_schedule_short_async", AsyncMock(return_value=[event]))
    monkeypatch.setattr(n, "get_users_with_settings", AsyncMock(return_value=[(1,"UTC",60,0,31,0,interval_mask([60,120]))]))
    monkeypatch.setattr(n, "get_all_group_chats", AsyncMock(return_value=[]))
    monkeypatch.setattr(n, "was_reminder_sent", AsyncMock(return_value=False))
    monkeypatch.setattr(n, "set_reminder_sent", AsyncMock())
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(n, "safe_send_message", sent)
    await n.check_and_send_notifications(None)
    assert {call.kwargs['delivery_key'] for call in sent.await_args_list} == {'reminder:2026:16:race:120', 'reminder:2026:16:practice1:60'}
