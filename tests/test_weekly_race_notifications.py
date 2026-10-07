"""Weekly recap timing, real week boundaries, durable delivery and destinations."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio

from app.db import Database
from app.services import engagement, telegram_outbox as outbox, weekly_race_notifications as service

DUE = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)  # Monday 11:00 Moscow


@pytest_asyncio.fixture
async def weekly_store(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    await database.conn.executemany('INSERT INTO users(telegram_id,timezone) VALUES(?,?)', [(1,'Europe/Moscow'), (2,'UTC')])
    await database.conn.commit()
    monkeypatch.setattr(outbox, 'db', database)
    monkeypatch.setattr(engagement, 'db', database)
    monkeypatch.setattr(service, 'get_users_with_settings', AsyncMock(return_value=[(1,'Europe/Moscow'), (2,'UTC')]))
    monkeypatch.setattr(service, 'publish_web', AsyncMock())
    monkeypatch.setattr('app.utils.safe_send._apply_sound_preference', AsyncMock())
    monkeypatch.setenv('MINI_APP_URL', 'https://example.test')
    yield database
    await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('now', [DUE-timedelta(seconds=1), DUE+timedelta(hours=1),
                                DUE+timedelta(days=1), DUE-timedelta(days=1)])
async def test_no_early_or_stale_broadcast(weekly_store, monkeypatch, now):
    fetch = AsyncMock()
    monkeypatch.setattr(service, 'weekly', fetch)
    assert await service.check_and_notify_weekly_race(None, now=now) is False
    fetch.assert_not_awaited()
    service.publish_web.assert_not_awaited()


@pytest.mark.asyncio
async def test_winner_cutoff_and_only_one_delivery_after_restart(weekly_store, monkeypatch):
    database = weekly_store
    # The scheduler and durable queue must share the simulated time, including TTL checks.
    delivery_now = DUE
    monkeypatch.setattr(outbox, 'time', SimpleNamespace(time=lambda: delivery_now.timestamp()))
    previous_track, start, end = engagement.weekly_period(DUE-timedelta(days=7))
    current_track, _, _ = engagement.weekly_period(DUE)
    await database.conn.executemany(
        'INSERT INTO reaction_leaderboard_profiles(telegram_id,display_name,leaderboard_opt_in) VALUES(?,?,?)',
        [(1,'Winner <One>',1), (2,'Second',1), (3,'Private',0)])
    # Faster scores outside the week, on another track, or from opted-out players cannot win.
    scores = [(1,61001,start+timedelta(seconds=1),previous_track['id']),
              (1,62000,start+timedelta(days=1),previous_track['id']),
              (2,64000,end-timedelta(seconds=1),previous_track['id']),
              (2,15000,end,previous_track['id']),
              (2,15000,start-timedelta(seconds=1),previous_track['id']),
              (2,15000,start+timedelta(days=1),current_track['id']),
              (3,15000,start+timedelta(days=1),previous_track['id'])]
    await database.conn.executemany('INSERT INTO race_game_scores(telegram_id,time_ms,created_at,track_id) VALUES(?,?,?,?)',
                                   [(who,ms,at.isoformat(),track) for who,ms,at,track in scores])
    await database.conn.commit()
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=123)))
    assert await service.check_and_notify_weekly_race(bot, now=DUE)
    delivery_now = DUE + timedelta(minutes=5)
    assert await service.check_and_notify_weekly_race(bot, now=delivery_now)
    assert bot.send_message.await_count == 2
    text = bot.send_message.await_args.kwargs['text']
    assert 'Winner &lt;One&gt;' in text and '01:01.001' in text and 'Началась новая неделя' in text
    assert 'Second' not in text and 'Private' not in text
    button = bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard[0][0]
    parts = urlsplit(button.web_app.url)
    query = parse_qs(parts.query)
    assert parts.path == '/community'
    assert query['weekly'] == ['previous'] and query['week'] == ['2026-09-28']
    assert len(query['nb'][0]) == 32
    assert await outbox.delivery_counts('weekly-race:2026-10-05') == {'sent':2}
    assert service.publish_web.await_args.args[3] == '/community?weekly=previous&week=2026-09-28'
    assert service.publish_web.await_args.kwargs['expires'] == DUE.replace(hour=20,minute=59).timestamp()
    previous = await engagement.weekly(end-timedelta(microseconds=1))
    assert [entry['name'] for entry in previous['entries']] == ['Winner <One>', 'Second']


@pytest.mark.parametrize('entries, phrase', [([], 'победителя нет'),
    ([{'name':'One','time_ms':61000},{'name':'Two','time_ms':61000}], 'Победители: <b>One, Two</b>')])
def test_empty_week_and_equal_winners(entries, phrase):
    text = service.recap_text({'entries': entries,'name':'Track & One'}, {'name':'New <Track>'})
    assert phrase in text and 'Track &amp; One' in text and 'New &lt;Track&gt;' in text


@pytest.mark.asyncio
async def test_missing_destination_retries_without_freezing_an_incomplete_push(weekly_store, monkeypatch):
    monkeypatch.setattr(service, 'mini_app_button', AsyncMock(return_value=None))
    assert not await service.check_and_notify_weekly_race(None, now=DUE)
    async with outbox.connection() as conn:
        assert (await (await conn.execute('SELECT COUNT(*) FROM telegram_delivery_batches')).fetchone())[0] == 0
    service.publish_web.assert_not_awaited()
