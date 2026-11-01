"""Real scheduler, PNG renderer and persistent outbox with local Telegram only."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import EditMessageText, SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import BufferedInputFile, Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message
from PIL import Image
import pytest
import pytest_asyncio

from app.services import championship, championship_notifications as cards
from app.services import reminder_status, telegram_outbox as outbox
from app.services.delivery_adapters import queued_illustrated_message, queued_photo
from app.utils import notifications
from scripts.championship_preview_data import preview_context

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text='Все условия титула', url='https://example.test/predictions'),
]])


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class LocalTelegram(BaseSession):
    def __init__(self, *, reject_media=False):
        super().__init__()
        self.methods = []
        self.reject_media = reject_media

    async def close(self):
        pass

    async def stream_content(self, url, **kwargs):
        yield b''

    async def make_request(self, bot, method, timeout=None):
        self.methods.append(method)
        if self.reject_media and isinstance(method, (SendPhoto, SendMediaGroup)):
            raise TelegramBadRequest(method=method, message='Bad Request: invalid photo dimensions')
        def message(index=0):
            return Message(message_id=len(self.methods)*10+index, date=NOW,
                           chat=Chat(id=method.chat_id, type='private' if method.chat_id > 0 else 'supergroup'),
                           text=getattr(method, 'text', None))
        return [message(i) for i in range(len(method.media))] if isinstance(method, SendMediaGroup) else message()


@pytest.fixture(scope='module')
def title_context():
    return preview_context()


@pytest_asyncio.fixture
async def delivery(db_session, monkeypatch):
    await db_session.conn.executemany('INSERT INTO users(telegram_id,timezone) VALUES(?,?)',
                                    [(1, 'UTC'), (2, 'Europe/Moscow')])
    await db_session.conn.execute('INSERT INTO group_chats(chat_id) VALUES(-100)')
    await db_session.conn.commit()
    monkeypatch.setattr(notifications, 'datetime', Clock)
    monkeypatch.setattr(championship, 'datetime', Clock)
    monkeypatch.setattr(outbox, 'time', SimpleNamespace(time=lambda: NOW.timestamp()))
    monkeypatch.setattr(notifications, 'mini_app_button', AsyncMock(return_value=KEYBOARD))
    event = {'round': 22, 'event_name': 'Test <GP>', 'location': 'Austin',
             'race_start_utc': (NOW+timedelta(minutes=60)).isoformat()}
    schedule = AsyncMock(return_value=[event])
    monkeypatch.setattr(notifications, 'get_season_schedule_short_async', schedule)
    monkeypatch.setattr('app.f1_data.get_season_schedule_short_async', schedule)
    session = LocalTelegram()
    bot = Bot('123456:LOCAL_TEST', session=session)
    yield db_session, event, bot, session
    await bot.session.close()


@pytest.mark.parametrize('competitions', [('drivers',), ('constructors',), ('drivers', 'constructors')])
async def test_scheduler_sends_current_images_to_private_chats_and_groups_once(delivery, monkeypatch, title_context, competitions):
    _, event, bot, session = delivery
    context = {**title_context, **{kind: [] for kind in ('drivers', 'constructors') if kind not in competitions}}
    source = AsyncMock(return_value=context)
    monkeypatch.setattr(championship, 'get_championship_context', source)
    render = Mock(wraps=cards.render_championship_card)
    monkeypatch.setattr(cards, 'render_championship_card', render)
    await notifications.check_and_send_notifications(bot)
    await notifications.check_and_send_notifications(bot)
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert render.call_count == len(competitions)  # One snapshot for the whole audience.
    source.assert_awaited_once()
    for chat in (1, 2, -100):
        methods = [m for m in session.methods if m.chat_id == chat]
        assert len(methods) == 2
        photo, text = methods
        assert photo.disable_notification is True  # One sound, from the text.
        assert isinstance(text, SendMessage) and 'Скоро гонка' in text.text and 'Титул может решиться' in text.text
        if chat > 0:
            assert text.reply_markup == KEYBOARD
        images = [photo.photo] if isinstance(photo, SendPhoto) else [m.media for m in photo.media]
        assert len(images) == len(competitions)
        for image in images:
            assert isinstance(image, BufferedInputFile)
            with Image.open(BytesIO(image.data)) as png:
                assert png.format == 'PNG' and png.width == 1080
        key = f'reminder:2026:22:race:60:{chat}'
        assert await outbox.delivery_counts(key) == {'sent': 1}
        async with outbox.connection() as conn:
            receipt = await (await conn.execute('SELECT message_id FROM telegram_deliveries WHERE event_key=?', (key,))).fetchone()
        assert receipt['message_id'] == session.methods.index(text)*10+10
    # The existing lifecycle must edit the final text, never the photo/album.
    monkeypatch.setattr(reminder_status, 'utc_now', lambda: NOW+timedelta(minutes=61))
    await reminder_status.refresh_reminder_messages()
    await outbox.drain(bot)
    edits = [m for m in session.methods if isinstance(m, EditMessageText)]
    assert len(edits) == 3 and all('УЖЕ ИДЁТ' in m.text for m in edits)
    assert len([m for m in session.methods if isinstance(m, SendMessage)]) == 3


@pytest.mark.parametrize('status', ['ok', 'unavailable'])
async def test_no_confirmed_title_opportunity_keeps_plain_reminders(delivery, monkeypatch, status):
    _, _, bot, session = delivery
    monkeypatch.setattr(championship, 'get_championship_context', AsyncMock(return_value={
        'status': status, 'drivers': [], 'constructors': [],
    }))
    render = Mock(side_effect=AssertionError('No image without a mathematical title chance'))
    monkeypatch.setattr(cards, 'render_championship_card', render)
    await notifications.check_and_send_notifications(bot)
    await outbox.drain(bot)
    assert len(session.methods) == 3 and all(isinstance(m, SendMessage) for m in session.methods)
    render.assert_not_called()


async def test_render_or_context_failure_does_not_drop_the_reminder(delivery, monkeypatch, title_context):
    _, event, _, _ = delivery
    source = AsyncMock(return_value=title_context)
    monkeypatch.setattr(championship, 'get_championship_context', source)
    render = Mock(side_effect=OSError('Artwork unavailable'))
    monkeypatch.setattr(cards, 'render_championship_card', render)
    enriched, images = await cards.prepare_reminder(event, 2026, 'race', schedule=[event])
    assert enriched['championship']['status'] == 'ok' and not images
    source.side_effect = TimeoutError()
    enriched, images = await cards.prepare_reminder(event, 2026, 'race', schedule=[event])
    assert enriched == event and not images
    source.reset_mock()
    for kind in ('practice1', 'quali', 'sprint_quali'):
        assert await cards.prepare_reminder(event, 2026, kind) == (event, ())
    source.assert_not_awaited()


async def test_sprint_and_race_snapshots_refresh_points_and_opponents(delivery, monkeypatch, title_context):
    _, event, _, _ = delivery
    event = {**event, 'sprint_start_utc': (NOW+timedelta(minutes=30)).isoformat()}
    source = AsyncMock(side_effect=[title_context, preview_context(next_round=True)])
    monkeypatch.setattr(championship, 'get_championship_context', source)
    render = Mock(return_value=b'png')
    monkeypatch.setattr(cards, 'render_championship_card', render)
    await cards.prepare_reminder(event, 2026, 'sprint', schedule=[event])
    # Explicit completed-Sprint event keeps this test independent of wall time.
    await cards.prepare_reminder({**event, 'sprint_start_utc': (NOW-timedelta(minutes=1)).isoformat()}, 2026, 'race', schedule=[event])
    first, updated = render.call_args_list[0].args[0], render.call_args_list[2].args[0]
    assert first.leader.points == 350 and updated.leader.points == 375
    assert [r.entrant.code for r in updated.rivals] == ['NOR', 'RUS']
    assert [call.kwargs['phase'] for call in source.await_args_list] == ['weekend', 'race']


@pytest.mark.parametrize('photo_count', [1, 2])
async def test_rejected_optional_artwork_keeps_full_text_and_button(delivery, photo_count):
    _, _, bot, session = delivery
    session.reject_media = True
    text = 'Полные условия титула. ' * 70  # Longer than a photo caption.
    await queued_illustrated_message(bot, 1, text, photos=[b'png']*photo_count,
                                    delivery_key='reminder:2026:22:race:60', expires=NOW.timestamp()+86400,
                                    reply_markup=KEYBOARD, parse_mode='HTML')
    await outbox.drain(bot)
    assert len(session.methods) == 2 and isinstance(session.methods[-1], SendMessage)
    assert session.methods[-1].text == text and session.methods[-1].reply_markup == KEYBOARD
    assert await outbox.delivery_counts('reminder:2026:22:race:60:1') == {'sent': 1}


async def test_unrelated_photo_rejection_is_still_reported_as_failure(delivery):
    _, _, bot, session = delivery
    session.reject_media = True
    await queued_photo(bot, 1, b'png', caption='Results', delivery_key='results:test', expires=NOW.timestamp()+86400)
    await outbox.drain(bot)
    assert await outbox.delivery_counts('results:test:1') == {'failed': 1}
    assert len(session.methods) == 1


async def test_rate_limited_album_retries_without_duplicating_the_text(delivery, monkeypatch):
    _, _, bot, session = delivery
    send = session.make_request
    limited = False
    async def rate_limit_once(bot, method, timeout=None):
        nonlocal limited
        if isinstance(method, SendMediaGroup) and not limited:
            limited = True
            raise TelegramRetryAfter(method=method, message='Too Many Requests', retry_after=1)
        return await send(bot, method, timeout)
    monkeypatch.setattr(session, 'make_request', rate_limit_once)
    key = 'reminder:2026:22:race:60'
    await queued_illustrated_message(bot, 1, 'Reminder', photos=[b'png', b'png'],
                                    delivery_key=key, expires=NOW.timestamp()+3600)
    await outbox.drain(bot, limit=1)
    assert await outbox.delivery_counts(key+':1') == {'retry': 1}
    assert not session.methods
    monkeypatch.setattr(outbox, 'time', SimpleNamespace(time=lambda: NOW.timestamp()+120))
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert [type(m) for m in session.methods] == [SendMediaGroup, SendMessage]
    assert await outbox.delivery_counts(key+':1') == {'sent': 1}


async def test_changed_preference_cancels_artwork_before_delivery(delivery):
    database, _, bot, session = delivery
    await queued_illustrated_message(bot, 1, 'Reminder', photos=[b'png'],
                                    delivery_key='reminder:2026:22:race:60', expires=NOW.timestamp()+3600)
    await database.conn.execute('UPDATE users SET reminder_sessions=0 WHERE telegram_id=1')
    await database.conn.commit()
    await outbox.drain(bot)
    assert not session.methods
    assert await outbox.delivery_counts('reminder:2026:22:race:60:1') == {'cancelled': 1}


async def test_muted_recipient_gets_both_artwork_and_text_silently(delivery):
    database, _, bot, session = delivery
    await database.conn.execute('UPDATE users SET notifications_enabled=0 WHERE telegram_id=1')
    await database.conn.commit()
    await queued_illustrated_message(bot, 1, 'Reminder', photos=[b'png'],
                                    delivery_key='reminder:2026:22:race:60', expires=NOW.timestamp()+3600)
    await outbox.drain(bot)
    assert len(session.methods) == 2 and all(m.disable_notification is True for m in session.methods)
