from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.utils.mini_app_links import mini_app_button
from app.services.prediction_notifications import _send_prediction_opened, _send_prediction_results


@pytest.mark.asyncio
async def test_private_chat_button_targets_voting_stage(monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://example.test/?source=telegram")
    bot = AsyncMock()
    markup = await mini_app_button(bot, "Vote", "/voting", season=2026, round=15)
    button = markup.inline_keyboard[0][0]
    assert button.url is None  # Must open a Telegram WebView, not an external link.
    parts = urlsplit(button.web_app.url)
    assert parts.path == "/voting"
    assert parse_qs(parts.query) == {"source": ["telegram"], "season": ["2026"], "round": ["15"]}
    bot.get_chat_menu_button.assert_not_awaited()


@pytest.mark.asyncio
async def test_button_resolves_existing_bot_menu_when_env_is_missing(monkeypatch):
    for key in ("MINI_APP_URL", "PUBLIC_WEB_URL", "FRONTEND_URL"):
        monkeypatch.delenv(key, raising=False)
    bot = AsyncMock()
    bot.get_chat_menu_button.return_value = MenuButtonWebApp(text="Open", web_app=WebAppInfo(url="https://example.test/"))
    markup = await mini_app_button(bot, "Table", "/predictions", tab="leaderboard")
    assert markup.inline_keyboard[0][0].web_app.url == "https://example.test/predictions?tab=leaderboard"


@pytest.mark.asyncio
async def test_non_https_configuration_cannot_generate_a_broken_telegram_button(monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "http://localhost:5173")
    assert await mini_app_button(AsyncMock(), "Open", "/predictions") is None


@pytest.mark.asyncio
async def test_prediction_notifications_contain_destination_buttons(monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://example.test")
    bot = AsyncMock()
    event = {"event_name": "Italian <Grand Prix>", "round": 15}
    users = [(123, "UTC")]
    assert await _send_prediction_opened(bot, event, users) == 1
    opened = bot.send_message.await_args.kwargs
    assert opened["reply_markup"].inline_keyboard[0][0].web_app.url.endswith("/predictions?tab=form")
    assert "&lt;Grand Prix&gt;" in opened["text"]
    assert "\n\n\n" not in opened["text"]
    assert await _send_prediction_results(bot, event, [], users) == 1
    results = bot.send_message.await_args.kwargs
    assert results["reply_markup"].inline_keyboard[0][0].web_app.url.endswith("/predictions?tab=leaderboard")
