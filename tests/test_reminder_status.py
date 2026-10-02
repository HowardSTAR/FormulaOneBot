"""Reminder lifecycle with a local outbox and fake Telegram; no working DB/API."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import EditMessageText

from app.db import Database
from app.services import reminder_status as status, telegram_outbox as outbox
from app.utils.notifications import get_notification_text, format_time_left

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def event(kind='practice1', ago=38, **extra):
    return {'round': 16, 'event_name': 'Test <GP>', 'location': 'Sakhir & track',
            f'{kind}_start_utc': (NOW-timedelta(minutes=ago)).isoformat(), **extra}


@pytest.mark.parametrize('kind', status.SESSION_MINUTES)
def test_boundaries_and_no_negative_timer_for_every_session(kind):
    race = event(kind, ago=0)
    start = status.parse_utc(race[f'{kind}_start_utc'])
    assert status.session_phase(race, kind, start-timedelta(microseconds=1)) == ('before', False)
    assert status.session_phase(race, kind, start) == ('live', True)
    end = start+timedelta(minutes=status.SESSION_MINUTES[kind])
    assert status.session_phase(race, kind, end-timedelta(microseconds=1)) == ('live', True)
    assert status.session_phase(race, kind, end) == ('finished', True)
    for minutes, phrase in [(0, 'УЖЕ ИДЁТ'), (-38, 'УЖЕ ИДЁТ'),
                            (-status.SESSION_MINUTES[kind], 'Этап прошёл' if kind == 'race' else 'Сессия прошла')]:
        text = get_notification_text(race, 'Europe/Moscow', minutes, event_kind=kind)
        assert phrase in text
        assert 'format="r"' not in text and 'назад' not in text and 'Скоро' not in text
        assert 'Test &lt;GP&gt;' in text and 'Sakhir &amp; track' in text


def test_explicit_completion_cancellation_and_live_override_estimates():
    for kind, status_key in status.STATUS_KEYS.items():
        assert status.session_phase(event(kind, ago=1, **{status_key:'results_ready'}), kind, NOW) == ('finished', False)
        assert status.session_phase(event(kind, ago=240, **{status_key:'in_progress'}), kind, NOW) == ('live', False)
        assert status.session_phase(event(kind, ago=240, **{status_key:'suspended'}), kind, NOW) == ('live', False)
    assert status.session_phase(event(is_cancelled=True), 'practice1', NOW) == ('cancelled', False)
    assert status.session_phase({}, 'race', NOW) == ('unknown', False)
    assert status.parse_utc('broken') is None
    assert status.parse_utc('2026-10-02T15:00:00+03:00') == NOW
    assert status.parse_utc('2026-10-02T12:00:00') == NOW
    race = event(practice1_end_utc=NOW.isoformat())
    assert status.session_phase(race, 'practice1', NOW) == ('finished', False)
    text = get_notification_text(race, 'UTC', -38, event_kind='practice1', for_group=True)
    assert 'Сессия прошла' in text and 'расписанию' not in text and 'Начало' not in text
    assert format_time_left(-1) == 'УЖЕ ИДЁТ'
    assert format_time_left(.5) == 'Менее чем через минуту'


@pytest_asyncio.fixture
async def lifecycle(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    await database.conn.executemany('INSERT INTO users(telegram_id,timezone) VALUES(?,?)', [(1,'Europe/Moscow'),(2,'UTC')])
    await database.conn.execute('INSERT INTO group_chats(chat_id) VALUES(-100)')
    await database.conn.commit()
    monkeypatch.setattr(outbox, 'db', database)
    monkeypatch.setattr(status, 'utc_now', lambda: NOW)
    schedule = AsyncMock(return_value=[event()])
    monkeypatch.setattr('app.f1_data.get_season_schedule_short_async', schedule)
    yield database, schedule
    await database.close()


async def receipt(chat=1, kind='practice1', message_id=123, delivery_status='sent', minutes=60):
    # Legacy receipt: no lifecycle metadata is required on the original message.
    key = f'reminder:2026:16:{kind}:{minutes}:{chat}'
    await outbox.enqueue(key, 'Old reminder', None, [(chat,'Europe/Moscow')], NOW.timestamp()+86400)
    async with outbox.connection() as conn:
        await conn.execute('UPDATE telegram_deliveries SET status=?,message_id=? WHERE event_key=?',
                           (delivery_status, message_id, key))
        await conn.commit()
    return key


@pytest.mark.asyncio
async def test_restart_updates_same_private_and_group_messages_without_resending(lifecycle, monkeypatch):
    keys = [await receipt(1), await receipt(-100)]
    bot = SimpleNamespace(edit_message_text=AsyncMock(), send_message=AsyncMock())
    await status.refresh_reminder_messages()
    await status.refresh_reminder_messages()  # Restart/poll does not create duplicate jobs.
    await outbox.drain(bot)
    await outbox.drain(bot)
    assert bot.edit_message_text.await_count == 2
    for call in bot.edit_message_text.await_args_list:
        assert call.kwargs['message_id'] == 123 and 'УЖЕ ИДЁТ' in call.kwargs['text']
        assert 'disable_notification' not in call.kwargs
        assert ('Начало было в' in call.kwargs['text']) == (call.kwargs['chat_id'] > 0)
    later = NOW+timedelta(minutes=23)
    monkeypatch.setattr(status, 'utc_now', lambda: later)
    await status.refresh_reminder_messages()
    await outbox.drain(bot)
    assert bot.edit_message_text.await_count == 4
    assert all('Сессия прошла' in call.kwargs['text'] for call in bot.edit_message_text.await_args_list[-2:])
    bot.send_message.assert_not_awaited()
    for key in keys:
        assert await outbox.delivery_counts(key) == {'sent':1}
        assert await outbox.delivery_counts(f'reminder-state:{key}:finished') == {'sent':1}


@pytest.mark.asyncio
async def test_skip_unconfirmed_archived_future_testing_and_missing_schedule(lifecycle):
    database, schedule = lifecycle
    await receipt(1, message_id=None)
    await receipt(2, delivery_status='unknown')
    await receipt(2, minutes=30)
    await database.conn.execute('UPDATE users SET archived_at=CURRENT_TIMESTAMP WHERE telegram_id=2')
    await database.conn.commit()
    await status.refresh_reminder_messages()
    schedule.return_value = [event(ago=-15), event(is_testing=True), {'round':1}]
    await status.refresh_reminder_messages()
    schedule.side_effect = RuntimeError('source unavailable')
    await status.refresh_reminder_messages()
    async with outbox.connection() as conn:
        count = await (await conn.execute("SELECT COUNT(*) FROM telegram_delivery_batches WHERE event_key LIKE 'reminder-state:%'")).fetchone()
    assert count[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['unchanged','deleted','network','rate_limit'])
async def test_edit_failures_never_send_a_replacement_and_retry_only_safe_edits(lifecycle, failure):
    key = await receipt()
    await status.refresh_reminder_messages()
    method = EditMessageText(chat_id=1, message_id=123, text='test')
    exceptions = {
        'unchanged': TelegramBadRequest(method=method, message='Bad Request: message is not modified'),
        'deleted': TelegramBadRequest(method=method, message='Bad Request: message to edit not found'),
        'network': TelegramNetworkError(method=method, message='timeout'),
        'rate_limit': TelegramRetryAfter(method=method, message='wait', retry_after=60),
    }
    bot = SimpleNamespace(edit_message_text=AsyncMock(side_effect=[exceptions[failure], True]), send_message=AsyncMock())
    await outbox.drain(bot)
    edit_key = f'reminder-state:{key}:live'
    expected = {'unchanged':'sent','deleted':'cancelled','network':'retry','rate_limit':'retry'}[failure]
    assert await outbox.delivery_counts(edit_key) == {expected:1}
    if expected == 'retry':
        async with outbox.connection() as conn:
            await conn.execute('UPDATE telegram_deliveries SET next_attempt=0 WHERE event_key=?', (edit_key,))
            await conn.commit()
        await outbox.drain(bot)
        assert await outbox.delivery_counts(edit_key) == {'sent':1}
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_live_edit_cannot_overwrite_finished_status(lifecycle, monkeypatch):
    key = await receipt()
    await status.refresh_reminder_messages()
    later = NOW+timedelta(hours=2)
    monkeypatch.setattr(status, 'utc_now', lambda: later)
    await status.refresh_reminder_messages()
    bot = SimpleNamespace(edit_message_text=AsyncMock(), send_message=AsyncMock())
    await outbox.drain(bot)
    bot.edit_message_text.assert_awaited_once()
    assert 'Сессия прошла' in bot.edit_message_text.await_args.kwargs['text']
    assert await outbox.delivery_counts(f'reminder-state:{key}:live') == {'cancelled':1}
    assert await outbox.delivery_counts(f'reminder-state:{key}:finished') == {'sent':1}


@pytest.mark.asyncio
async def test_bounded_polls_do_not_starve_remaining_recipients(lifecycle):
    await receipt(1)
    await receipt(2)
    await status.refresh_reminder_messages(batch_size=1)
    await status.refresh_reminder_messages(batch_size=1)
    bot = SimpleNamespace(edit_message_text=AsyncMock())
    await outbox.drain(bot)
    assert bot.edit_message_text.await_count == 2


@pytest.mark.asyncio
async def test_edit_requires_matching_original_receipt(lifecycle):
    from app.services.delivery_adapters import queue_actions
    key = await receipt()
    await queue_actions(f'reminder-state:{key}:live', [{'method':'edit_message_text','kwargs':{
        'message_id':999, '_reminder':{'source_key':key}}}], [(1,'UTC')], NOW.timestamp()+86400)
    bot = SimpleNamespace(edit_message_text=AsyncMock())
    await outbox.drain(bot)
    bot.edit_message_text.assert_not_awaited()
    assert await outbox.delivery_counts(f'reminder-state:{key}:live') == {'cancelled':1}
