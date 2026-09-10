from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.session_reminders import SESSION_BITS, session_enabled


def test_defaults_none_and_category_mapping():
    assert all(session_enabled(None, kind) for kind in SESSION_BITS)
    assert all(session_enabled(31, kind) for kind in SESSION_BITS)
    assert not any(session_enabled(0, kind) for kind in SESSION_BITS)
    assert all(session_enabled(1, f"practice{i}") for i in (1, 2, 3))
    assert not session_enabled(1, "quali")
    assert not session_enabled(8, "sprint")
    assert not session_enabled(16, "sprint_quali")


def test_reminder_keys_are_distinct():
    from app.utils.notifications import _event_reminder_key
    keys = [_event_reminder_key(kind, minutes) for kind in SESSION_BITS for minutes in (15,30,60,120,1440)]
    assert len(set(keys)) == len(keys)


@pytest.mark.asyncio
async def test_existing_accounts_migrate_with_all_sessions(tmp_path):
    import aiosqlite
    from app.auth_schema import CREATE_USERS_SQL, ensure_auth_schema
    async with aiosqlite.connect(tmp_path / "legacy.db") as conn:
        legacy_sql = "\n".join(line for line in CREATE_USERS_SQL.splitlines() if "reminder_sessions" not in line)
        await conn.execute(legacy_sql)
        await conn.execute("INSERT INTO users(telegram_id,notifications_enabled) VALUES(42,0)")
        await conn.commit()
        await ensure_auth_schema(conn)
        row = await (await conn.execute("SELECT reminder_sessions,notifications_enabled FROM users WHERE telegram_id=42")).fetchone()
        assert tuple(row) == (31, 0)
        await conn.execute("UPDATE users SET reminder_sessions=0 WHERE telegram_id=42")
        await conn.commit()
        await ensure_auth_schema(conn)
        assert (await (await conn.execute("SELECT reminder_sessions FROM users WHERE telegram_id=42")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_account_settings_shared_with_bot_and_legacy_client(api_client):
    from app.db import get_user_settings, update_user_setting
    assert (await api_client.get("/api/account/settings")).json()["reminder_sessions"] == 31
    body = {"timezone": "Europe/Moscow", "notify_before": 60, "notifications_enabled": False, "reminder_sessions": 0}
    assert (await api_client.post("/api/account/settings", json=body)).status_code == 200
    assert (await get_user_settings(999888))["reminder_sessions"] == 0
    body.pop("reminder_sessions")
    await api_client.post("/api/settings", json=body)
    assert (await get_user_settings(999888))["reminder_sessions"] == 0
    await update_user_setting(999888, "reminder_sessions", 12)
    assert (await api_client.get("/api/account/settings")).json()["reminder_sessions"] == 12
    for invalid in (-1, 32, True, "4"):
        assert (await api_client.post("/api/account/settings", json=body | {"reminder_sessions": invalid})).status_code == 422


@pytest.mark.asyncio
async def test_bot_filters_and_deduplicates_practices(monkeypatch):
    from app.utils import notifications as n
    when = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    event = {"round": 5, "event_name": "Test", **{f"{kind}_start_utc": when for kind in SESSION_BITS}}
    monkeypatch.setattr(n, "get_season_schedule_short_async", AsyncMock(return_value=[event]))
    monkeypatch.setattr(n, "get_users_with_settings", AsyncMock(return_value=[(1,"UTC",60,1,1), (2,"UTC",60,1,0), (3,"UTC",60,1,8)]))
    monkeypatch.setattr(n, "get_all_group_chats", AsyncMock(return_value=[]))
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(n, "safe_send_message", sent)
    seen = set()
    async def was(*key): return key in seen
    async def mark(*key): seen.add(key)
    monkeypatch.setattr(n, "was_reminder_sent", was)
    monkeypatch.setattr(n, "set_reminder_sent", mark)
    await n.check_and_send_notifications(None)
    await n.check_and_send_notifications(None)
    assert sent.await_count == 4
    assert [call.args[1] for call in sent.call_args_list] == [1,1,1,3]
    assert all(f"FP{i}" in sent.call_args_list[i-1].args[2] for i in (1,2,3))
