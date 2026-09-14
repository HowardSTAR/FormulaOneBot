import base64
import json
import sys
import time
from types import SimpleNamespace

import pytest
import pytest_asyncio
from app.services import web_notifications as service

def subscription(endpoint="https://fcm.googleapis.com/fcm/send/test"):
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return {"endpoint":endpoint,"keys":{"p256dh":encode(b"\x04"+b"a"*64),"auth":encode(b"b"*16)}}

@pytest_asyncio.fixture
async def store(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "db", SimpleNamespace(db_path=tmp_path/"notifications.db"))
    monkeypatch.setattr('app.services.telegram_outbox.db', service.db)
    async with service.connection() as conn:
        await conn.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,archived_at TEXT,role TEXT DEFAULT 'user',timezone TEXT DEFAULT 'UTC',notify_before INTEGER DEFAULT 60,reminder_sessions INTEGER DEFAULT 31);
        INSERT INTO users(id,archived_at) VALUES(1,NULL),(2,NULL);
        CREATE TABLE favorite_drivers(user_id INTEGER,driver_code TEXT);
        CREATE TABLE favorite_teams(user_id INTEGER,constructor_name TEXT);
        INSERT INTO favorite_drivers VALUES(1,'NOR');""")
        await conn.execute('ALTER TABLE users ADD COLUMN telegram_id INTEGER')
        await conn.execute('CREATE TABLE group_chats(chat_id INTEGER PRIMARY KEY)')
        await service.initialize(conn)
        await conn.executemany("INSERT INTO web_notification_members VALUES(?,?)",[(1,time.time()),(2,time.time())])
        await conn.execute("INSERT INTO web_push_subscriptions VALUES(1,1,?,?,?)",(subscription()["endpoint"],json.dumps(subscription()),time.time()))
        await conn.commit()
    return service

@pytest.mark.parametrize("endpoint", ["http://fcm.googleapis.com/a", "https://127.0.0.1/a", "https://fcm.googleapis.com.attacker.test/a", "https://fcm.googleapis.com:8000/a", "https://user@fcm.googleapis.com/a"])
def test_rejects_ssrf_endpoints(endpoint):
    with pytest.raises(ValueError): service.validate_subscription(subscription(endpoint))

def test_validates_key_sizes():
    service.validate_subscription(subscription())
    data = subscription(); data["keys"]["auth"] = "a"
    with pytest.raises(ValueError): service.validate_subscription(data)


@pytest.mark.asyncio
async def test_session_reminders_filter_and_no_backfill(store, monkeypatch):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock
    import app.f1_data as f1
    now = time.time()
    async with store.connection() as conn:
        await conn.execute("UPDATE users SET reminder_sessions=CASE id WHEN 1 THEN 1 ELSE 0 END")
        await conn.execute("UPDATE web_notification_members SET joined_at=?", (now-600,))
        await conn.commit()
    start = datetime.fromtimestamp(now+3600-10, timezone.utc).isoformat()
    old = datetime.fromtimestamp(now-86400, timezone.utc).isoformat()
    schedule = [{"round": 1, "event_name": "Test", "practice1_start_utc": start, "quali_start_utc": start, "race_start_utc": old}]
    monkeypatch.setattr(f1, "get_season_schedule_short_async", AsyncMock(return_value=schedule))
    monkeypatch.setattr(store, "dispatch_push", AsyncMock())
    await store.poll_web_notifications(not_before=now-60)
    await store.poll_web_notifications(not_before=now-60)
    async with store.connection() as conn:
        rows = await (await conn.execute("SELECT user_id,event_key FROM web_notifications")).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1 and ":practice1:" in rows[0][1]


@pytest.mark.asyncio
async def test_disabled_session_drops_pending_push(store, monkeypatch):
    sent = []
    monkeypatch.setenv("WEB_PUSH_PUBLIC_KEY", "test")
    monkeypatch.setenv("WEB_PUSH_PRIVATE_KEY", "test")
    monkeypatch.setenv("WEB_PUSH_SUBJECT", "mailto:test@example.com")
    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(webpush=lambda **kw: sent.append(kw), WebPushException=type("WebPushException", (Exception,), {})))
    await store.publish("reminder:2026:1:quali:60", "Soon", "Soon", "/notifications", user_id=1)
    async with store.connection() as conn:
        await conn.execute("UPDATE users SET reminder_sessions=0 WHERE id=1")
        await conn.commit()
    await store.dispatch_push(not_before=time.time()-60)
    assert sent == []
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT done FROM web_push_outbox")).fetchone())[0] == 1

@pytest.mark.asyncio
async def test_deduplication_personalization_and_queue(store):
    for _ in range(2):
        await store.publish("race:1", "Race", "<b>Results</b>", "/race-results", rows=[{"code":"NOR","name":"Norris","team":"McLaren","position":1}])
    async with store.connection() as conn:
        rows = await (await conn.execute("SELECT user_id,body FROM web_notifications ORDER BY user_id")).fetchall()
        assert len(rows)==2
        assert "Ваше избранное" in rows[0][1] and "Ваше избранное" not in rows[1][1]
        assert "<b>" not in rows[0][1]
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_push_outbox")).fetchone())[0]==1

@pytest.mark.asyncio
async def test_restart_keeps_queued_push_within_ttl(store,monkeypatch):
    sent=[]
    monkeypatch.setenv("WEB_PUSH_PUBLIC_KEY","test"); monkeypatch.setenv("WEB_PUSH_PRIVATE_KEY","test"); monkeypatch.setenv("WEB_PUSH_SUBJECT","mailto:test@example.com")
    monkeypatch.setitem(sys.modules,"pywebpush",SimpleNamespace(webpush=lambda **kw:sent.append(kw),WebPushException=type("WebPushException",(Exception,),{})))
    await store.publish("old", "Old", "Old", "/notifications")
    baseline=time.time()
    await store.publish("new", "New", "New", "/notifications")
    await store.dispatch_push(not_before=baseline)
    await store.dispatch_push(not_before=baseline)
    assert len(sent)==2 and {json.loads(item['data'])['title'] for item in sent}=={'Old','New'}
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0]==4

@pytest.mark.asyncio
async def test_legacy_attempt_and_expired_reminder_are_not_replayed(store,monkeypatch):
    from app.services.telegram_outbox import delivery_counts
    await store.publish('legacy','Legacy','Body','/notifications')
    await store.publish('reminder:2026:1:quali:5','Soon','Body','/notifications',expires=time.time()-1)
    async with store.connection() as conn:
        await conn.execute("UPDATE web_push_outbox SET attempts=1 WHERE notification_id IN (SELECT id FROM web_notifications WHERE event_key='legacy')")
        ids = await (await conn.execute('SELECT notification_id,subscription_id FROM web_push_outbox ORDER BY notification_id')).fetchall()
        await conn.commit()
    await store.dispatch_push(not_before=time.time())
    assert await delivery_counts(f'webpush:{ids[0][0]}:{ids[0][1]}') == {'unknown':1}
    assert await delivery_counts(f'webpush:{ids[1][0]}:{ids[1][1]}') == {'expired':1}


@pytest.mark.asyncio
async def test_inbox_and_read_are_scoped_to_account(store):
    from app.api.web_notifications_api import inbox,mark_read,ReadBody
    await store.publish("one","Title","Body","/notifications")
    own=await inbox(before=0,user_id=1)
    assert len(own["items"])==1 and own["unread"]==1
    await mark_read(ReadBody(through_id=999),user_id=1)
    assert (await inbox(before=0,user_id=1))["unread"]==0
    assert (await inbox(before=0,user_id=2))["unread"]==1
