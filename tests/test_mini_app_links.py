from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.utils.mini_app_links import destination_buttons, mini_app_button
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
async def test_prediction_notifications_contain_destination_buttons(monkeypatch, api_client):
    from app.db import db
    await db.conn.execute('INSERT INTO users(telegram_id) VALUES(123)')
    await db.conn.commit()
    monkeypatch.setattr('app.services.prediction_notifications.publish_web', AsyncMock())
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
    parts = urlsplit(results["reply_markup"].inline_keyboard[0][0].web_app.url)
    assert parts.path == '/predictions' and parse_qs(parts.query)['tab'] == ['leaderboard']
    assert len(parse_qs(parts.query)['nb'][0]) == 32


@pytest.mark.asyncio
async def test_multiple_destinations_resolve_menu_once(monkeypatch):
    for key in ('MINI_APP_URL', 'PUBLIC_WEB_URL', 'FRONTEND_URL'):
        monkeypatch.delenv(key, raising=False)
    bot = AsyncMock()
    bot.get_chat_menu_button.return_value = MenuButtonWebApp(
        text='Open', web_app=WebAppInfo(url='https://example.test/?source=telegram'),
    )
    markup = await destination_buttons(bot, [
        ('История', '/history?tag=a&tag=b#latest', {}),
        ('Пилоты', '/drivers', {'driver': 'ALO'}),
        ('Рекап', '/race-results', {}),
    ])
    bot.get_chat_menu_button.assert_awaited_once()
    buttons = [row[0] for row in markup.inline_keyboard]
    assert len(buttons) == 3 and all(button.url is None for button in buttons)
    assert buttons[0].web_app.url == 'https://example.test/history?source=telegram&tag=a&tag=b#latest'
    assert buttons[1].web_app.url == 'https://example.test/drivers?source=telegram&driver=ALO'
    assert buttons[2].web_app.url == 'https://example.test/race-results?source=telegram'


@pytest.mark.asyncio
async def test_mixed_buttons_and_independent_queries(monkeypatch):
    monkeypatch.setenv('MINI_APP_URL', 'https://example.test/?source=telegram&tab=form')
    bot = AsyncMock()
    markup = await destination_buttons(bot, [
        ('Table', '/predictions?tab=leaderboard', {}),
        ('Site', 'https://other.test/page', {}),
        ('History', '/history', {}),
    ])
    first, external, last = [row[0] for row in markup.inline_keyboard]
    assert first.web_app.url == 'https://example.test/predictions?source=telegram&tab=leaderboard'
    assert external.url == 'https://other.test/page' and external.web_app is None
    assert last.web_app.url == 'https://example.test/history?source=telegram&tab=form'
    bot.get_chat_menu_button.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_only_buttons_do_not_resolve_miniapp(monkeypatch):
    for key in ('MINI_APP_URL', 'PUBLIC_WEB_URL', 'FRONTEND_URL'):
        monkeypatch.delenv(key, raising=False)
    bot = AsyncMock()
    markup = await destination_buttons(bot, [('Channel', 'https://t.me/example', {})])
    assert markup.inline_keyboard[0][0].url == 'https://t.me/example'
    bot.get_chat_menu_button.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_partial_keyboard_on_config_or_destination_error(monkeypatch):
    monkeypatch.setenv('MINI_APP_URL', 'http://localhost:5173')
    bot = AsyncMock()
    assert await destination_buttons(bot, [
        ('Channel', 'https://t.me/example', {}), ('History', '/history', {}),
    ]) is None
    with pytest.raises(ValueError):
        await destination_buttons(bot, [('History', '/history', {}), ('Bad', 'javascript:alert(1)', {})])
    bot.get_chat_menu_button.assert_not_awaited()
    assert await destination_buttons(bot, []) is None
