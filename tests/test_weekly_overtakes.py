"""Weekly crossings and durable personal alerts; Telegram is always mocked."""
import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.db import Database
from app.services import weekly_race_overtakes as service, telegram_outbox as outbox
from app.services.engagement import weekly_period
from tests.test_engagement import replay

NOW = datetime(2026,10,5,12,tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def store(temp_db_path,monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    await database.conn.executemany('INSERT INTO users(telegram_id,timezone) VALUES(?,?)',[(1,'UTC'),(2,'Europe/Moscow'),(3,'UTC')])
    await database.conn.executemany('INSERT INTO reaction_leaderboard_profiles(telegram_id,display_name,leaderboard_opt_in) VALUES(?,?,1)',[(1,'One'),(2,'Two <fast>'),(3,'Three')])
    await database.conn.commit()
    monkeypatch.setattr(service,'db',database)
    monkeypatch.setattr(outbox,'db',database)
    monkeypatch.setattr(importlib.import_module('app.db'),'db',database)
    monkeypatch.setattr('app.utils.safe_send._apply_sound_preference',AsyncMock())
    monkeypatch.setenv('MINI_APP_URL','https://example.test')
    yield database
    await database.close()


async def score(store,who,ms,*,at=NOW,track=None,record=True):
    track = track or weekly_period(at)[0]['id']
    cursor = await store.conn.execute('INSERT INTO race_game_scores(telegram_id,time_ms,created_at,track_id) VALUES(?,?,?,?)',(who,ms,at.isoformat(),track))
    if record:
        await service.record_overtakes(store.conn,cursor.lastrowid)
    await store.conn.commit()
    return cursor.lastrowid


async def alerts(store):
    return await (await store.conn.execute('SELECT * FROM weekly_race_overtakes ORDER BY id')).fetchall()


@pytest.mark.asyncio
async def test_real_crossings_ties_self_slower_and_already_faster(store):
    await score(store,1,70000)
    await score(store,2,70000)
    assert await alerts(store)==[]  # tie is not an overtake
    await score(store,2,69000)
    assert len(await alerts(store))==1
    await score(store,2,68000)
    await score(store,1,71000)
    assert len(await alerts(store))==1  # improving while already ahead is not another crossing
    await score(store,1,67000)
    assert len(await alerts(store))==2
    await score(store,2,66000)
    assert len(await alerts(store))==3  # retaking the record creates a new event
    notification = await (await store.conn.execute('SELECT COUNT(*) FROM web_notifications WHERE user_id=1')).fetchone()
    assert notification[0]==1  # one current weekly item, no inbox storm


@pytest.mark.asyncio
async def test_other_track_previous_week_private_archived_and_first_score_do_not_notify(store):
    await score(store,1,70000,at=NOW-timedelta(days=7))
    await score(store,2,60000)
    assert await alerts(store)==[]
    await score(store,1,70000)
    # One is already behind, so this score cannot create a crossing.
    await score(store,2,61000)
    assert await alerts(store)==[]
    await store.conn.execute('UPDATE users SET archived_at=CURRENT_TIMESTAMP WHERE telegram_id=1')
    await store.conn.commit()
    await score(store,3,59000)
    assert len(await alerts(store))==1  # Two only
    await store.conn.execute('UPDATE reaction_leaderboard_profiles SET leaderboard_opt_in=0 WHERE telegram_id=2')
    await store.conn.commit()
    await score(store,3,58000)
    assert len(await alerts(store))==1
    other = weekly_period(NOW)[0]
    from app.race_rules import TRACKS
    other_id = next(key for key in TRACKS if key!=other['id'])
    await score(store,3,57000,track=other_id)
    assert len(await alerts(store))==1


@pytest.mark.asyncio
async def test_atomic_event_and_inbox_rollback_and_idempotence(store):
    await score(store,1,70000)
    await store.conn.execute('BEGIN IMMEDIATE')
    cursor = await store.conn.execute('INSERT INTO race_game_scores(telegram_id,time_ms,created_at,track_id) VALUES(2,60000,?,?)',(NOW.isoformat(),weekly_period(NOW)[0]['id']))
    await service.record_overtakes(store.conn,cursor.lastrowid)
    await store.conn.rollback()
    assert await alerts(store)==[]
    assert (await (await store.conn.execute('SELECT COUNT(*) FROM web_notifications')).fetchone())[0]==0
    score_id = await score(store,2,60000)
    await service.record_overtakes(store.conn,score_id)
    await store.conn.commit()
    assert len(await alerts(store))==1
    status = await service.personal_weekly(1,now=NOW)
    assert status['place']==2 and status['alert_id'] and status['rival']['time_ms']==60000
    await score(store,1,59000)
    assert (await service.personal_weekly(1,now=NOW))['alert_id'] is None
    assert (await service.personal_weekly(1,now=NOW+timedelta(days=7))) is None


@pytest.mark.asyncio
async def test_delivery_is_deduplicated_coalesced_and_stale_alert_is_cancelled(store,monkeypatch):
    clock = [NOW.timestamp()]
    monkeypatch.setattr(outbox,'time',SimpleNamespace(time=lambda:clock[0]))
    monkeypatch.setattr(service,'time',SimpleNamespace(time=lambda:clock[0]))
    await score(store,1,70000)
    await score(store,2,69000)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    await service.dispatch_overtakes(bot,now=NOW)
    await service.dispatch_overtakes(bot,now=NOW)
    assert bot.send_message.await_count==1
    text = bot.send_message.await_args.kwargs['text']
    assert 'Two &lt;fast&gt;' in text and 'Попробуй перебить' in text
    button = bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard[0][0]
    assert '/race-game?' in button.web_app.url and 'weekly=1' in button.web_app.url
    await score(store,3,68000)
    clock[0] += 30
    await service.dispatch_overtakes(bot,now=NOW+timedelta(seconds=30))
    # One is cooling down; Two gets the actual crossing.
    assert bot.send_message.await_count==2
    await score(store,1,67000)
    clock[0] = (NOW+timedelta(hours=1)).timestamp()
    await service.dispatch_overtakes(bot,now=NOW+timedelta(hours=1))
    assert not any(call.kwargs['chat_id']==1 for call in bot.send_message.await_args_list[1:])


@pytest.mark.asyncio
async def test_actual_score_save_hook_requires_valid_telemetry(store,monkeypatch):
    module = importlib.import_module('app.db')
    track = weekly_period()[0]['id']
    slow,fast = replay(track,210),replay(track,220)
    assert await module.save_race_game_score(1,slow['time_ms'],slow['telemetry'],track_id=track)
    assert await module.save_race_game_score(2,fast['time_ms'],fast['telemetry'],track_id=track)
    assert len(await alerts(store))==1
    assert not await module.save_race_game_score(3,15000,[],track_id=track)
    assert len(await alerts(store))==1


@pytest.mark.asyncio
async def test_reclaimed_record_cancels_already_queued_message(store,monkeypatch):
    monkeypatch.setattr(outbox,'time',SimpleNamespace(time=lambda:NOW.timestamp()))
    monkeypatch.setattr(service,'time',SimpleNamespace(time=lambda:NOW.timestamp()))
    await score(store,1,70000)
    await score(store,2,69000)
    real_drain = outbox.drain
    monkeypatch.setattr(outbox,'drain',AsyncMock())
    await service.dispatch_overtakes(None,now=NOW)
    key = 'weekly-overtake:1'
    assert await outbox.delivery_counts(key)=={'pending':1}
    await score(store,1,68000)
    bot = SimpleNamespace(send_message=AsyncMock())
    await real_drain(bot,event_key=key)
    bot.send_message.assert_not_awaited()
    assert await outbox.delivery_counts(key)=={'cancelled':1}


@pytest.mark.asyncio
async def test_personal_weekly_api_is_private_and_empty_account_is_explicit(api_client):
    response = await api_client.get('/api/engagement/weekly/me')
    assert response.status_code==200
    assert response.headers['cache-control']=='private, no-store'
    assert response.json()['user_id'] and response.json()['weekly'] is None
    from app.api.auth_api import require_hybrid_user_id
    from app.api.miniapp_api import web_app
    from fastapi import HTTPException
    def denied():
        raise HTTPException(401,'Not signed in')
    web_app.dependency_overrides[require_hybrid_user_id] = denied
    assert (await api_client.get('/api/engagement/weekly/me')).status_code==401
