import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError, TelegramForbiddenError, TelegramBadRequest
from aiogram.methods import SendMessage, SendPhoto

from app.db import Database
from app.services import telegram_outbox as outbox
from tests.support import Clock


@pytest.mark.parametrize('terminal',['sent','blocked','failed','unknown','cancelled','expired'])
async def test_terminal_delivery_states_are_never_replayed(queue,terminal):
    await outbox.enqueue('terminal','Original',None,[(1,'UTC')],time.time()+1000)
    async with outbox.connection() as conn:
        await conn.execute('UPDATE telegram_deliveries SET status=? WHERE event_key=?',(terminal,'terminal'))
        await conn.commit()
    bot = SimpleNamespace(send_message=AsyncMock())
    await outbox.drain(bot)
    await outbox.enqueue('terminal','Changed',None,[(1,'UTC'),(2,'UTC')],time.time()+1000)
    await outbox.drain(bot)
    bot.send_message.assert_not_awaited()
    assert await outbox.delivery_counts('terminal') == {terminal:1}


@pytest.mark.parametrize('offset,sent',[pytest.param(-0.001,True,id='before-expiry'),
    pytest.param(0,False,id='at-expiry'),pytest.param(0.001,False,id='after-expiry')])
async def test_delivery_ttl_boundary(queue,monkeypatch,offset,sent):
    clock = Clock()
    monkeypatch.setattr(outbox,'time',clock)
    expires = clock.time()+10
    await outbox.enqueue('boundary','Original',None,[(1,'UTC')],expires)
    clock.advance(seconds=10+offset)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    await outbox.drain(bot)
    assert bot.send_message.await_count == int(sent)
    assert await outbox.delivery_counts('boundary') == {'sent' if sent else 'expired':1}


@pytest_asyncio.fixture
async def queue(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    await database.conn.executemany('INSERT INTO users(telegram_id) VALUES(?)', [(1,), (2,), (3,)])
    await database.conn.commit()
    monkeypatch.setattr(outbox, 'db', database)
    monkeypatch.setattr(outbox, '_apply_sound_preference', AsyncMock())
    monkeypatch.setattr('app.utils.safe_send._apply_sound_preference', AsyncMock())
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_restart_dedup_audience_and_rate_limit(queue):
    key = 'test:1'
    await outbox.enqueue(key, 'Original', None, [(1,'UTC'),(2,'UTC')], time.time()+1000)
    method = SendMessage(chat_id=2, text='Original')
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[SimpleNamespace(message_id=10), TelegramRetryAfter(method=method,message='wait',retry_after=1), SimpleNamespace(message_id=11)]))
    await outbox.drain(bot)
    assert await outbox.delivery_counts(key) == {'sent':1,'retry':1}
    # Re-enqueue after restart cannot change text or add newly registered users.
    await outbox.enqueue(key, 'Changed', None, [(1,'UTC'),(2,'UTC'),(3,'UTC')], time.time()+1000)
    await outbox.drain(bot)
    assert bot.send_message.await_count == 2  # cooldown is respected
    async with outbox.connection() as conn:
        await conn.execute('UPDATE telegram_deliveries SET next_attempt=0')
        await conn.commit()
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert [c.kwargs['chat_id'] for c in bot.send_message.await_args_list] == [1,2,2]
    assert all(c.kwargs['text']=='Original' for c in bot.send_message.await_args_list)
    assert await outbox.delivery_counts(key) == {'sent':2}


@pytest.mark.asyncio
async def test_ambiguous_and_blocked_are_not_replayed(queue):
    await outbox.enqueue('errors', 'Text', None, [(1,'UTC'),(2,'UTC')], time.time()+1000)
    method = SendMessage(chat_id=1,text='Text')
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[TelegramNetworkError(method=method,message='timeout'),TelegramForbiddenError(method=method,message='blocked')]))
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert await outbox.delivery_counts('errors') == {'unknown':1,'blocked':1}
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_bad_request_keeps_telegram_reason_without_retrying(queue):
    from app.services.delivery_adapters import queued_photo
    await queued_photo(None, 1, b'png-test', delivery_key='bad-photo')
    method = SendPhoto(chat_id=1, photo='test')
    bot = SimpleNamespace(send_photo=AsyncMock(side_effect=TelegramBadRequest(
        method=method, message='Bad Request: chat not found')))
    await outbox.drain(bot)
    async with outbox.connection() as conn:
        row = await (await conn.execute(
            'SELECT status, attempts, error FROM telegram_deliveries WHERE event_key=?',
            ('bad-photo:1',))).fetchone()
    assert tuple(row) == ('failed', 1, 'telegram_bad_request: Bad Request: chat not found')
    await outbox.drain(bot)
    bot.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_expiration_archiving_and_interrupted_send(queue):
    await outbox.enqueue('expired', 'Text', None, [(1,'UTC')], time.time()-1)
    await outbox.enqueue('archived', 'Text', None, [(2,'UTC')], time.time()+1000)
    await queue.conn.execute("UPDATE users SET archived_at=CURRENT_TIMESTAMP WHERE telegram_id=2")
    await queue.conn.commit()
    await outbox.enqueue('crash', 'Text', None, [(3,'UTC')], time.time()+1000)
    async with outbox.connection() as conn:
        await conn.execute("UPDATE telegram_deliveries SET status='sending',updated=0 WHERE event_key='crash'")
        await conn.commit()
    bot = SimpleNamespace(send_message=AsyncMock())
    await outbox.drain(bot)
    assert await outbox.delivery_counts('expired') == {'expired':1}
    assert await outbox.delivery_counts('archived') == {'cancelled':1}
    assert await outbox.delivery_counts('crash') == {'unknown':1}
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_workers_claim_once(queue):
    await outbox.enqueue('concurrent','Text',None,[(1,'UTC')],time.time()+1000)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    await asyncio.gather(outbox.drain(bot),outbox.drain(bot))
    bot.send_message.assert_awaited_once()
    assert await outbox.delivery_counts('concurrent') == {'sent':1}


@pytest.mark.asyncio
async def test_album_progress_survives_retry_and_capture_is_inert(queue):
    from app.services.delivery_adapters import capture, queue_actions
    from app.utils.safe_send import safe_send_media_group, safe_send_message
    from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    bot = SimpleNamespace(send_media_group=AsyncMock(return_value=[SimpleNamespace(message_id=1)]),
                          send_message=AsyncMock(side_effect=[TelegramRetryAfter(method=SendMessage(chat_id=1,text='Text'),message='wait',retry_after=1),SimpleNamespace(message_id=2)]))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Open',web_app=WebAppInfo(url='https://example.com'))]])
    with capture() as actions:
        await safe_send_media_group(bot,1,[InputMediaPhoto(media='one'),InputMediaPhoto(media='two')])
        await safe_send_message(bot,1,'Text',reply_markup=keyboard)
    bot.send_media_group.assert_not_awaited()
    bot.send_message.assert_not_awaited()
    await queue_actions('album',actions,[(1,'UTC')],time.time()+1000)
    await outbox.drain(bot)
    assert bot.send_media_group.await_count == 1
    async with outbox.connection() as conn:
        await conn.execute('UPDATE telegram_deliveries SET next_attempt=0')
        await conn.commit()
    await outbox.drain(bot)
    assert bot.send_media_group.await_count == 1
    assert bot.send_message.await_count == 2
    assert bot.send_message.call_args.kwargs['reply_markup'] == keyboard
    assert await outbox.delivery_counts('album') == {'sent':1}


@pytest.mark.asyncio
async def test_binary_photo_and_group_delivery(queue):
    from app.services.delivery_adapters import queued_photo
    from aiogram.types import BufferedInputFile
    await queue.conn.execute('INSERT INTO group_chats(chat_id) VALUES(-100)')
    await queue.conn.commit()
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=2)))
    await queued_photo(bot,-100,b'png-test',delivery_key='group-results',has_spoiler=True)
    await outbox.drain(bot)
    kwargs = bot.send_photo.call_args.kwargs
    assert kwargs['chat_id'] == -100 and kwargs['has_spoiler']
    assert isinstance(kwargs['photo'],BufferedInputFile) and kwargs['photo'].data == b'png-test'


@pytest.mark.asyncio
@pytest.mark.parametrize('original_rich', [True, False])
async def test_rich_upgrade_preserves_frozen_delivery_and_deduplicates(queue, monkeypatch, original_rich):
    from aiogram.types import InputRichMessage, BufferedInputFile
    from app.services.delivery_adapters import queued_photo, queued_rich_message
    from app.utils.telegram_presentation import race_card, personal_buttons
    monkeypatch.setenv('TELEGRAM_RICH_MESSAGES', '1')
    await queue.conn.execute('INSERT INTO group_chats(chat_id) VALUES(-100)')
    await queue.conn.commit()
    bot = SimpleNamespace(
        send_rich_message=AsyncMock(return_value=SimpleNamespace(message_id=31)),
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=32)),
        send_message=AsyncMock(),
    )
    card = race_card('Test GP', 2026, 15, [{'pos': 1, 'driver': 'RUS', 'points': 25}], {'items': []},
                     photo=BufferedInputFile(b'rich-png', filename='results.png'))
    async def rich():
        await queued_rich_message(bot, -100, card, 'Full fallback', delivery_key='race-photo:2026:15', reply_markup=personal_buttons(2026, 15))
    async def photo():
        await queued_photo(bot, -100, b'original-png', delivery_key='race-photo:2026:15')
    await (rich() if original_rich else photo())
    await (photo() if original_rich else rich())
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert await outbox.delivery_counts('race-photo:2026:15:-100') == {'sent': 1}
    bot.send_message.assert_not_awaited()
    if original_rich:
        bot.send_photo.assert_not_awaited()
        bot.send_rich_message.assert_awaited_once()
        sent = bot.send_rich_message.await_args.kwargs
        assert isinstance(sent['rich_message'], InputRichMessage)
        image = next(block for block in sent['rich_message'].blocks if block.type == 'photo')
        assert isinstance(image.photo.media, BufferedInputFile) and image.photo.media.data == b'rich-png'
        assert sent['chat_id'] == -100
        assert sent['reply_markup'].inline_keyboard[-1][0].callback_data == 'personal:review:2026:15'
    else:
        bot.send_rich_message.assert_not_awaited()
        bot.send_photo.assert_awaited_once()
        assert bot.send_photo.await_args.kwargs['photo'].data == b'original-png'


@pytest.mark.asyncio
@pytest.mark.parametrize('ambiguous', [False, True])
async def test_queued_rich_fallback_is_only_for_explicit_feature_rejection(queue, monkeypatch, ambiguous):
    from aiogram.methods import SendRichMessage
    from app.services.delivery_adapters import queued_rich_message
    from app.utils.telegram_presentation import race_card
    monkeypatch.setenv('TELEGRAM_RICH_MESSAGES', '1')
    card = race_card('Test GP', 2026, 15, [], {'items': []})
    method = SendRichMessage(chat_id=1, rich_message=card)
    failure = (TelegramNetworkError(method=method, message='timeout') if ambiguous else
               TelegramBadRequest(method=method, message='rich message is not supported'))
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=failure),
                          send_message=AsyncMock(return_value=SimpleNamespace(message_id=33)))
    await queued_rich_message(bot, 1, card, 'Verified classification', delivery_key='rich-fallback')
    await outbox.drain(bot)
    await outbox.drain(bot)
    bot.send_rich_message.assert_awaited_once()
    if ambiguous:
        bot.send_message.assert_not_awaited()
        assert await outbox.delivery_counts('rich-fallback:1') == {'unknown': 1}
    else:
        bot.send_message.assert_awaited_once()
        assert bot.send_message.await_args.kwargs['text'] == 'Verified classification'
        assert await outbox.delivery_counts('rich-fallback:1') == {'sent': 1}
