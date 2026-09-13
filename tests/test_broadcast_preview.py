"""Broadcast preview tests with mocked Telegram: never send real messages."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.handlers import secret
from app.utils.broadcast_draft import parse_button


def test_button_parser_preserves_rich_text():
    text, plain, button = parse_button('<b>Итоги</b>\n/button Таблица | /predictions?tab=leaderboard', 'Итоги\n/button Таблица | /predictions?tab=leaderboard')
    assert text == '<b>Итоги</b>' and plain == 'Итоги'
    assert button == ('Таблица','/predictions',{'tab':'leaderboard'})
    assert parse_button('Hi','Hi') == ('Hi','Hi',None)


@pytest.mark.parametrize('footer',[
    '/button X | https://evil.test/predictions',
    '/button X | //evil.test/predictions',
    '/button X | /predictions?tab=bad',
    '/button X | /voting?tab=form',
    '/button | /predictions',
    '/button X | /predictions\nmore',
    '/button X | /predictions\n/button Y | /voting',
])
def test_invalid_directives_rejected(footer):
    with pytest.raises(ValueError):
        parse_button('Hi\n'+footer,'Hi\n'+footer)


@pytest.fixture
def mock_broadcast(monkeypatch):
    secret._broadcast_drafts.clear()
    monkeypatch.setattr(secret,'get_settings',lambda:SimpleNamespace(admin_ids={1}))
    monkeypatch.setattr(secret,'get_users_with_settings',AsyncMock(return_value=[(2,'UTC'),(3,'UTC')]))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Open',web_app=WebAppInfo(url='https://example.test/predictions'))]])
    monkeypatch.setattr(secret,'mini_app_button',AsyncMock(return_value=keyboard))
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(secret,'_deliver_broadcast',deliver)
    text = '/broadcast Hello\n/button Open | /predictions?tab=leaderboard'
    msg = SimpleNamespace(from_user=SimpleNamespace(id=1),chat=SimpleNamespace(id=1,type='private'),
                          bot=object(),text=text,caption=None,html_text=text,media_group_id=None,
                          photo=None,reply_to_message=None,answer=AsyncMock(),edit_text=AsyncMock(),edit_reply_markup=AsyncMock())
    yield msg, deliver
    secret._broadcast_drafts.clear()


def callback(msg, token, action='send', owner=1):
    return SimpleNamespace(from_user=SimpleNamespace(id=owner),data=f'bc:{action}:{token}',
                           message=msg,bot=msg.bot,answer=AsyncMock())


@pytest.mark.asyncio
async def test_preview_only_then_double_click_sends_once(mock_broadcast):
    msg, deliver = mock_broadcast
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    assert deliver.await_count == 1 and deliver.call_args.args[1] == 1
    token = next(iter(secret._broadcast_drafts))
    draft = secret._broadcast_drafts[token]
    assert draft['plain'] == 'Hello' and draft['keyboard'] is not None
    await asyncio.gather(secret.confirm_broadcast(callback(msg,token)),secret.confirm_broadcast(callback(msg,token)))
    assert [call.args[1] for call in deliver.await_args_list] == [1,2,3]
    assert token not in secret._broadcast_drafts


@pytest.mark.asyncio
async def test_owner_cancel_expiry_and_replacement(mock_broadcast):
    msg, deliver = mock_broadcast
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    token = next(iter(secret._broadcast_drafts))
    await secret.confirm_broadcast(callback(msg,token,owner=2))
    assert token in secret._broadcast_drafts
    await secret.confirm_broadcast(callback(msg,token,'cancel'))
    assert not secret._broadcast_drafts and deliver.await_count == 1
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    old = next(iter(secret._broadcast_drafts))
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    assert old not in secret._broadcast_drafts
    token = next(iter(secret._broadcast_drafts))
    secret._broadcast_drafts[token]['expires'] = 0
    await secret.confirm_broadcast(callback(msg,token))
    assert deliver.await_count == 3  # previews only


@pytest.mark.asyncio
async def test_missing_configuration_no_confirmation(mock_broadcast, monkeypatch):
    msg, deliver = mock_broadcast
    monkeypatch.setattr(secret,'mini_app_button',AsyncMock(return_value=None))
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    assert not secret._broadcast_drafts and deliver.await_count == 0


@pytest.mark.asyncio
async def test_album_uses_separate_button_message(monkeypatch):
    media, text = AsyncMock(return_value=True), AsyncMock(return_value=True)
    monkeypatch.setattr(secret,'safe_send_media_group',media)
    monkeypatch.setattr(secret,'_send_broadcast_text',text)
    keyboard = object()
    result = await secret._deliver_broadcast(object(),1,dict(photos=['a','b'],text='Hello',plain='Hello',keyboard=keyboard),quiet=True)
    assert result
    assert media.call_args.args[2][0].caption is None
    assert text.call_args.kwargs['reply_markup'] is keyboard
