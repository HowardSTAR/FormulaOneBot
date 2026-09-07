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
    async with service.connection() as conn:
        await conn.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,archived_at TEXT);
        INSERT INTO users VALUES(1,NULL),(2,NULL);
        CREATE TABLE favorite_drivers(user_id INTEGER,driver_code TEXT);
        CREATE TABLE favorite_teams(user_id INTEGER,constructor_name TEXT);
        INSERT INTO favorite_drivers VALUES(1,'NOR');""")
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
async def test_restart_drops_old_push_but_keeps_history(store,monkeypatch):
    sent=[]
    monkeypatch.setenv("WEB_PUSH_PUBLIC_KEY","test"); monkeypatch.setenv("WEB_PUSH_PRIVATE_KEY","test"); monkeypatch.setenv("WEB_PUSH_SUBJECT","mailto:test@example.com")
    monkeypatch.setitem(sys.modules,"pywebpush",SimpleNamespace(webpush=lambda **kw:sent.append(kw),WebPushException=type("WebPushException",(Exception,),{})))
    await store.publish("old", "Old", "Old", "/notifications")
    baseline=time.time()
    await store.publish("new", "New", "New", "/notifications")
    await store.dispatch_push(not_before=baseline)
    await store.dispatch_push(not_before=baseline)
    assert len(sent)==1 and json.loads(sent[0]["data"])["title"]=="New"
    async with store.connection() as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0]==4

@pytest.mark.asyncio
async def test_inbox_and_read_are_scoped_to_account(store):
    from app.api.web_notifications_api import inbox,mark_read,ReadBody
    await store.publish("one","Title","Body","/notifications")
    own=await inbox(before=0,user_id=1)
    assert len(own["items"])==1 and own["unread"]==1
    await mark_read(ReadBody(through_id=999),user_id=1)
    assert (await inbox(before=0,user_id=1))["unread"]==0
    assert (await inbox(before=0,user_id=2))["unread"]==1
