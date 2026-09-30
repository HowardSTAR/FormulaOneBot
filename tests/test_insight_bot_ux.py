"""Bot UX checks without Telegram requests or database writes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.handlers import insights
from app.utils.activity_status import ActivityStatus
from app.utils import activity_status


def message():
    status = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
    return SimpleNamespace(answer=AsyncMock(return_value=status), chat=SimpleNamespace(id=123, type='private'),
                           bot=SimpleNamespace(send_chat_action=AsyncMock())), status


def roster():
    return pd.DataFrame([{'driverId': 'alonso', 'driverCode': 'ALO', 'givenName': 'Fernando', 'familyName': 'Alonso', 'position': 19, 'points': 3.0}])


async def test_status_is_immediate_truthful_and_cleaned_on_success():
    msg, status = message()
    async with ActivityStatus(msg, 'Готовлю справку…') as loader:
        msg.answer.assert_awaited_once_with('⏳ Готовлю справку…')
        assert '%' not in msg.answer.call_args.args[0]
        assert loader.task is not None
        await asyncio.sleep(0)
    status.delete.assert_awaited_once()
    assert loader.task.done()


async def test_status_is_cleaned_on_failure():
    msg, status = message()
    with pytest.raises(RuntimeError):
        async with ActivityStatus(msg, 'Загрузка…'):
            raise RuntimeError('test')
    status.delete.assert_awaited_once()


async def test_long_wait_explains_source_is_still_answering(monkeypatch):
    msg, status = message()
    loader = ActivityStatus(msg, 'Загружаю данные…')
    loader.status = status
    calls = 0
    async def tick(seconds):
        nonlocal calls
        assert seconds == 4
        calls += 1
        if calls == 5:
            raise asyncio.CancelledError
    monkeypatch.setattr(activity_status.asyncio, 'sleep', tick)
    with pytest.raises(asyncio.CancelledError):
        await loader._typing()
    assert 'Источник ещё отвечает' in status.edit_text.call_args.args[0]
    assert '%' not in status.edit_text.call_args.args[0]


async def test_start_menu_contains_history_and_driver_buttons(monkeypatch):
    from app.handlers import start
    msg, _ = message()
    msg.from_user = SimpleNamespace(id=123)
    monkeypatch.setattr(start, 'get_or_create_user', AsyncMock())
    monkeypatch.setattr(start, '_show_main_settings', AsyncMock())
    await start.cmd_start(msg, SimpleNamespace())
    keyboard = msg.answer.call_args.kwargs['reply_markup']
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert '📈 История сезонов' in labels
    assert '🏎 Справка о пилоте' in labels
    assert '🤝 С друзьями' in labels


async def test_driver_answers_loading_before_awaiting_source(monkeypatch):
    msg, status = message()
    async def fetch(year):
        assert msg.answer.call_args.args[0].startswith('⏳')
        return roster()
    monkeypatch.setattr(insights, 'get_driver_standings_async', fetch)
    monkeypatch.setattr(insights, 'mini_app_button', AsyncMock(return_value=None))
    await insights.driver(msg, SimpleNamespace(args='ALO'))
    assert 'Fernando Alonso' in msg.answer.call_args.args[0]
    markup = msg.answer.call_args.kwargs['reply_markup']
    assert markup.inline_keyboard[-1][0].callback_data == 'insights:drivers'
    status.delete.assert_awaited_once()


async def test_driver_without_code_opens_named_buttons(monkeypatch):
    msg, _ = message()
    monkeypatch.setattr(insights, 'get_driver_standings_async', AsyncMock(return_value=roster()))
    await insights.driver(msg, SimpleNamespace(args=None))
    button = msg.answer.call_args.kwargs['reply_markup'].inline_keyboard[0][0]
    assert button.text == 'Fernando Alonso'
    assert button.callback_data.endswith(':ALO')


async def test_source_failure_replaces_loading_with_useful_message(monkeypatch):
    msg, status = message()
    monkeypatch.setattr(insights, 'get_driver_standings_async', AsyncMock(side_effect=TimeoutError()))
    await insights.choose_driver(msg)
    assert 'Не удалось загрузить' in msg.answer.call_args.args[0]
    status.delete.assert_awaited_once()


async def test_history_has_loading_and_discoverable_driver_button(monkeypatch):
    msg, status = message()
    async def button(*args, **kwargs):
        assert msg.answer.call_args.args[0].startswith('⏳')
        return None
    monkeypatch.setattr(insights, 'mini_app_button', button)
    await insights.history(msg)
    assert 'Показать сравнение' in msg.answer.call_args.args[0]
    assert msg.answer.call_args.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == 'insights:drivers'
    status.delete.assert_awaited_once()


async def test_mini_app_lookup_timeout_does_not_block_result(monkeypatch):
    msg, _ = message()
    monkeypatch.setattr(insights, 'mini_app_button', AsyncMock(side_effect=asyncio.TimeoutError()))
    assert await insights._web_button(msg, 'История', '/history') is None


async def test_callback_acknowledged_before_loading(monkeypatch):
    msg, _ = message()
    callback = SimpleNamespace(answer=AsyncMock(), message=msg, data='insights:driver:2026:ALO')
    monkeypatch.setattr(insights, 'Message', SimpleNamespace)
    async def fetch(year):
        callback.answer.assert_awaited_once()
        return roster()
    monkeypatch.setattr(insights, 'get_driver_standings_async', fetch)
    monkeypatch.setattr(insights, 'mini_app_button', AsyncMock(return_value=None))
    await insights.driver_callback(callback)
    assert 'Fernando Alonso' in msg.answer.call_args.args[0]
