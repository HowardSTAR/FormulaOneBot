import asyncio
import json
import sqlite3
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramUnauthorizedError
from aiogram.methods import GetMe
from app.services import error_alerts as alerts, web_notifications as web


@pytest.mark.parametrize("error,expected", [
    (TelegramBadRequest(method=GetMe(), message="query is too old"), "minimal"),
    (TelegramNetworkError(method=GetMe(), message="Request timeout error"), "low"),
    (TimeoutError(), "low"), (ValueError("invalid state"), "medium"),
    (sqlite3.OperationalError("no such table"), "critical"),
    (sqlite3.DatabaseError("database disk image is malformed"), "blocking"),
    (TelegramUnauthorizedError(method=GetMe(), message="Unauthorized"), "blocking"),
])
def test_priorities(error, expected):
    assert alerts.priority_for(error) == expected


def test_sensitive_values_are_redacted():
    result = alerts.redact("password=badsecret https://api.test/path?secret=x 123456:abcdefghijklmnopqrstuvwxyz0123456789 Authorization: Bearer eyJsecret.value.sig a@example.com")
    for secret in ("badsecret", "secret=x", "abcdefghijklmnopqrstuvwxyz", "eyJsecret", "a@example.com"):
        assert secret not in result


@pytest_asyncio.fixture
async def store(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "db", SimpleNamespace(db_path=tmp_path / "alerts.db"))
    monkeypatch.setattr(alerts, "get_primary_admin_telegram_id", lambda: 123)
    async with web.connection() as conn:
        await conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,archived_at TEXT)")
        await conn.executemany("INSERT INTO users VALUES(?,?,NULL)", [(1,"admin"),(2,"superadmin"),(3,"user")])
        await web.initialize(conn)
        await conn.commit()
    return web


@pytest.mark.asyncio
async def test_admin_inbox_without_push_enrollment_dedup_and_escalation(store):
    from app.api.web_notifications_api import inbox
    bot = SimpleNamespace(send_message=AsyncMock())
    for _ in range(6):
        await alerts.report_error(TimeoutError("timed out"), bot=bot)
    assert bot.send_message.await_count == 2  # Initial low + escalation, not six messages.
    admin = await inbox(before=0, user_id=1)
    assert [i["priority"] for i in admin["items"]] == ["medium", "low"]
    assert "Повторов в серии: 6" in admin["items"][0]["body"]
    assert len((await inbox(before=0, user_id=2))["items"]) == 2
    assert (await inbox(before=0, user_id=3))["items"] == []
    async with store.connection() as conn:
        await conn.execute("UPDATE users SET role='user' WHERE id=1")
        await conn.commit()
    assert (await inbox(before=0, user_id=1))["items"] == []
    assert (await inbox(before=0, user_id=1))["unread"] == 0


@pytest.mark.asyncio
async def test_parallel_incidents_are_deduplicated(store):
    await asyncio.gather(*(alerts.report_error(ValueError("same")) for _ in range(4)))
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0] == 2


@pytest.mark.asyncio
async def test_database_failure_falls_back_without_recursive_alerts(monkeypatch):
    monkeypatch.setattr(alerts, "record_incident", AsyncMock(side_effect=sqlite3.OperationalError("offline")))
    monkeypatch.setattr(alerts, "get_primary_admin_telegram_id", lambda: 123)
    monkeypatch.setattr(alerts, "_fallback", {})
    bot = SimpleNamespace(send_message=AsyncMock())
    await alerts.report_error(ValueError("same"), bot=bot)
    await alerts.report_error(ValueError("same"), bot=bot)
    assert bot.send_message.await_count == 1
    assert "Не удалось сохранить" in bot.send_message.call_args.args[1]


@pytest.mark.asyncio
async def test_middleware_reports_stale_callback_without_reply(monkeypatch):
    from app.middlewares import error_logging
    from aiogram.types import Update
    reporter = AsyncMock()
    monkeypatch.setattr(error_logging, "report_error", reporter)
    handler = AsyncMock(side_effect=TelegramBadRequest(method=GetMe(), message="query is too old"))
    assert await error_logging.ErrorLoggingMiddleware()(handler, Update(update_id=1), {}) is None
    assert reporter.call_args.kwargs["priority"] == "minimal"


@pytest.mark.asyncio
async def test_telegram_failure_does_not_lose_website_alert(store):
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=TimeoutError()))
    await alerts.report_error(ValueError("<unsafe>"), bot=bot)
    assert "&lt;unsafe&gt;" in bot.send_message.call_args.args[1]
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0] == 2


@pytest.mark.asyncio
async def test_push_is_not_delivered_after_admin_demotion(store, monkeypatch):
    from tests.test_web_notifications import subscription
    sent = []
    monkeypatch.setenv("WEB_PUSH_PUBLIC_KEY", "test")
    monkeypatch.setenv("WEB_PUSH_PRIVATE_KEY", "test")
    monkeypatch.setenv("WEB_PUSH_SUBJECT", "mailto:test@example.test")
    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(webpush=lambda **kw: sent.append(kw), WebPushException=type("WebPushException", (Exception,), {})))
    async with store.connection() as conn:
        await conn.execute("INSERT INTO web_notification_members VALUES(1,?)", (time.time(),))
        await conn.execute("INSERT INTO web_push_subscriptions VALUES(1,1,?,?,?)", (subscription()["endpoint"], json.dumps(subscription()), time.time()))
        await conn.commit()
    await alerts.report_error(ValueError("test"))
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_push_outbox")).fetchone())[0] == 1
        await conn.execute("UPDATE users SET role='user' WHERE id=1")
        await conn.commit()
    await store.dispatch_push(not_before=time.time()-60)
    assert not sent
