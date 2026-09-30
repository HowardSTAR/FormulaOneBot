"""Broadcast preview tests with mocked Telegram: never send real messages."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardMarkup

from app.handlers import secret
from app.handlers.secret import _deliver_broadcast
from app.utils.broadcast_draft import parse_button, parse_buttons
from app.utils.mini_app_links import destination_buttons


RELEASE_BUTTONS = (
    '/button 📈 История и сравнение | /history\n'
    '/button 🏎 Пилоты | /drivers\n'
    '/button 📰 Рекап гонки | /race-results'
)


def test_three_buttons_preserve_rich_body_and_order():
    plain = 'Новое ❤️ & полезное\n\n' + RELEASE_BUTTONS
    formatted = '<b>Новое ❤️ &amp; полезное\n\n' + RELEASE_BUTTONS + '</b>'
    body, text, buttons = parse_buttons(formatted, plain)
    assert body == '<b>Новое ❤️ &amp; полезное</b>'
    assert text == 'Новое ❤️ & полезное'
    assert buttons == [
        ('📈 История и сравнение', '/history', {}),
        ('🏎 Пилоты', '/drivers', {}),
        ('📰 Рекап гонки', '/race-results', {}),
    ]


def test_multiple_buttons_allow_blank_lines_and_optional_separator():
    text = 'Hello\n/button First /history\n\n/button Second | /drivers\n'
    assert parse_buttons(text, text) == (
        'Hello', 'Hello', [('First', '/history', {}), ('Second', '/drivers', {})],
    )
    assert parse_buttons('Hello', 'Hello') == ('Hello', 'Hello', [])


@pytest.mark.parametrize('text', [
    '/button X | /history',
    'Hello\n/button X | /history\nOther text\n/button Y | /drivers',
    'Hello\n/button X | /history\n/button Y | javascript:alert(1)',
    'Hello\n/button X | /history\n/button Y | //evil.test',
    'Hello\n/button X | /history\n/button',
    'Hello\n/button X | /history\n/button | /drivers',
    'Hello\n' + '\n'.join('/button X | /history' for _ in range(11)),
])
def test_invalid_multiple_buttons_reject_entire_block(text):
    with pytest.raises(ValueError):
        parse_buttons(text, text)


def test_ten_buttons_and_formatting_mismatch():
    text = 'Hello\n' + '\n'.join('/button X | /history' for _ in range(10))
    assert len(parse_buttons(text, text)[2]) == 10
    with pytest.raises(ValueError):
        parse_buttons('Different\n' + RELEASE_BUTTONS, 'Hello\n' + RELEASE_BUTTONS)


def test_button_parser_preserves_rich_text():
    text, plain, button = parse_button('<b>Итоги</b>\n/button Таблица | /predictions?tab=leaderboard', 'Итоги\n/button Таблица | /predictions?tab=leaderboard')
    assert text == '<b>Итоги</b>' and plain == 'Итоги'
    assert button == ('Таблица','/predictions?tab=leaderboard',{})
    assert parse_button('Hi','Hi') == ('Hi','Hi',None)


@pytest.mark.parametrize('formatted', [
    '<b>Привет ❤️</b>\n\n<b>/button ⭐️ Обратная связь /contact-admin</b>',
    '<b>Привет ❤️\n\n/button ⭐️ Обратная связь /contact-admin</b>',
    '<b>Привет ❤️</b>\n\n/button <tg-emoji emoji-id="123">⭐️</tg-emoji> Обратная связь /contact-admin',
    '<b>Привет ❤️</b>\n\n/button ⭐️ Обратная связь <a href="https://example.test">/contact-admin</a>',
])
def test_formatted_button_footer_preserves_body_and_closes_tags(formatted):
    plain = 'Привет ❤️\n\n/button ⭐️ Обратная связь /contact-admin'
    body, text, button = parse_button(formatted, plain)
    assert body == '<b>Привет ❤️</b>'
    assert text == 'Привет ❤️'
    assert button == ('⭐️ Обратная связь', '/contact-admin', {})


def test_button_cut_preserves_html_entities_and_nested_formatting():
    formatted = '<b>A &amp; <i>B\n/button X | /contact-admin</i></b>'
    body, _, _ = parse_button(formatted, 'A & B\n/button X | /contact-admin')
    assert body == '<b>A &amp; <i>B</i></b>'


@pytest.mark.parametrize('footer',[
    '/button X | javascript:alert(1)',
    '/button X | //evil.test/predictions',
    '/button X | https://user:pass@example.com',
    '/button X | /%2fevil.test',
    '/button | /predictions',
    '/button X | /predictions\nmore',
    '/button X | /predictions\n/button Y | /voting',
])
def test_invalid_directives_rejected(footer):
    with pytest.raises(ValueError):
        parse_button('Hi\n'+footer,'Hi\n'+footer)


@pytest.mark.parametrize('destination', ['/contact-admin', '/news?tag=a&tag=b#latest', 'https://t.me/example', 'https://example.com/post?id=1'])
def test_arbitrary_destinations_and_optional_separator(destination):
    for separator in [' | ', ' ']:
        message = 'Hello\n/button 🔔 Обратная связь' + separator + destination
        assert parse_button(message, message)[2] == ('🔔 Обратная связь', destination, {})


@pytest.mark.asyncio
async def test_external_link_preview_needs_no_miniapp_config(mock_broadcast, monkeypatch):
    for key in ('MINI_APP_URL', 'PUBLIC_WEB_URL', 'FRONTEND_URL'):
        monkeypatch.delenv(key, raising=False)
    msg, deliver = mock_broadcast
    msg.text = msg.html_text = '/broadcast Hello\n/button Канал | https://t.me/example'
    await secret.admin_silent_broadcast(msg, SimpleNamespace(args=''))
    assert deliver.await_count == 1
    draft = next(iter(secret._broadcast_drafts.values()))
    button = draft['keyboard'].inline_keyboard[0][0]
    assert button.url == 'https://t.me/example'
    assert button.web_app is None


@pytest.fixture
def mock_broadcast(monkeypatch):
    secret._broadcast_drafts.clear()
    monkeypatch.setattr(secret,'get_settings',lambda:SimpleNamespace(admin_ids={1}))
    monkeypatch.setattr(secret,'get_users_with_settings',AsyncMock(return_value=[(2,'UTC'),(3,'UTC')]))
    monkeypatch.setenv('MINI_APP_URL', 'https://example.test/')
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
async def test_preview_only_then_double_click_sends_once(mock_broadcast, monkeypatch):
    queue = AsyncMock()
    monkeypatch.setattr('app.services.delivery_adapters.queue_actions', queue)
    msg, deliver = mock_broadcast
    await secret.admin_silent_broadcast(msg,SimpleNamespace(args=''))
    assert deliver.await_count == 1 and deliver.call_args.args[1] == 1
    token = next(iter(secret._broadcast_drafts))
    draft = secret._broadcast_drafts[token]
    assert draft['plain'] == 'Hello' and draft['keyboard'] is not None
    await asyncio.gather(secret.confirm_broadcast(callback(msg,token)),secret.confirm_broadcast(callback(msg,token)))
    assert [call.args[1] for call in deliver.await_args_list] == [1,1]  # preview + inert payload capture
    queue.assert_awaited_once()
    assert queue.call_args.args[2] == [(2,'UTC'),(3,'UTC')]
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
    monkeypatch.setattr(secret,'destination_buttons',AsyncMock(return_value=None))
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


@pytest.mark.asyncio
async def test_three_buttons_preview_is_private_and_footer_is_removed(mock_broadcast):
    msg, deliver = mock_broadcast
    msg.text = '/broadcast Новости ❤️\n\n' + RELEASE_BUTTONS
    msg.html_text = '/broadcast <b>Новости ❤️</b>\n\n' + RELEASE_BUTTONS
    await secret.admin_silent_broadcast(msg, SimpleNamespace(args=''))
    assert deliver.await_count == 1 and deliver.call_args.args[1] == msg.chat.id
    draft = next(iter(secret._broadcast_drafts.values()))
    assert draft['text'] == '<b>Новости ❤️</b>' and draft['plain'] == 'Новости ❤️'
    assert [row[0].text for row in draft['keyboard'].inline_keyboard] == [
        '📈 История и сравнение', '🏎 Пилоты', '📰 Рекап гонки',
    ]
    assert [row[0].web_app.url for row in draft['keyboard'].inline_keyboard] == [
        'https://example.test/history', 'https://example.test/drivers', 'https://example.test/race-results',
    ]
    assert all(row[0].url is None for row in draft['keyboard'].inline_keyboard)


@pytest.mark.asyncio
async def test_invalid_third_button_has_no_preview_or_draft(mock_broadcast):
    msg, deliver = mock_broadcast
    msg.text = msg.html_text = '/broadcast Hello\n' + RELEASE_BUTTONS.replace('/race-results', 'javascript:alert(1)')
    await secret.admin_silent_broadcast(msg, SimpleNamespace(args=''))
    assert not secret._broadcast_drafts and deliver.await_count == 0
    secret.get_users_with_settings.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmation_captures_all_three_buttons(mock_broadcast, monkeypatch):
    msg, preview = mock_broadcast
    queue = AsyncMock()
    monkeypatch.setattr('app.services.delivery_adapters.queue_actions', queue)
    msg.text = msg.html_text = '/broadcast Hello\n' + RELEASE_BUTTONS
    await secret.admin_silent_broadcast(msg, SimpleNamespace(args=''))
    token = next(iter(secret._broadcast_drafts))
    expected = secret._broadcast_drafts[token]['keyboard']
    monkeypatch.setattr(secret, '_deliver_broadcast', _deliver_broadcast)
    await secret.confirm_broadcast(callback(msg, token))
    assert preview.await_count == 1  # only the admin preview; capture sends nothing
    queue.assert_awaited_once()
    actions = queue.call_args.args[1]
    assert len(actions) == 1 and actions[0]['method'] == 'send_message'
    assert actions[0]['kwargs']['text'] == 'Hello'
    restored = InlineKeyboardMarkup.model_validate(actions[0]['kwargs']['reply_markup'])
    assert restored == expected
    assert queue.call_args.args[2] == [(2, 'UTC'), (3, 'UTC')]
    assert token not in secret._broadcast_drafts


@pytest.mark.asyncio
@pytest.mark.parametrize('photos', [[], ['one'], ['one', 'two']])
async def test_delivery_serialization_preserves_three_miniapp_buttons(monkeypatch, photos):
    """Capture is inert: exercise the actual delivery path without Telegram or DB writes."""
    from app.services.delivery_adapters import capture

    monkeypatch.setenv('MINI_APP_URL', 'https://example.test/')
    _, _, buttons = parse_buttons('Hello\n' + RELEASE_BUTTONS, 'Hello\n' + RELEASE_BUTTONS)
    markup = await destination_buttons(object(), buttons)
    with capture() as actions:
        assert await secret._deliver_broadcast(object(), 1, dict(
            text='Hello', plain='Hello', photos=photos, keyboard=markup,
        ), quiet=True)
    assert len(actions) == (2 if len(photos) > 1 else 1)
    restored = InlineKeyboardMarkup.model_validate(actions[-1]['kwargs']['reply_markup'])
    assert restored == markup
    assert '/button' not in actions[-1]['kwargs'].get('text', actions[-1]['kwargs'].get('caption', ''))
