"""Isolated SQLite checks; no production notifications or network sends."""
import asyncio
import time
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api import admin_tools_api as tools, admin_api, auth_api
from app.db import Database
from app.emailer import MockMailer
from app.services.auth_service import AuthService


@pytest_asyncio.fixture
async def workspace(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    monkeypatch.setattr(tools, "db", database)
    monkeypatch.setattr(admin_api, "db", database)
    app = FastAPI()
    app.include_router(tools.router)
    for uid, role in [(1,"admin"),(2,"user"),(3,"user"),(4,"admin")]:
        await database.conn.execute("INSERT INTO users(id,telegram_id,display_name,role) VALUES(?,?,?,?)", (uid,900000+uid,f"User {uid}",role))
    await database.conn.executemany("INSERT INTO web_notification_members VALUES(?,?)", [(1,time.time()),(2,time.time()),(4,time.time())])
    await database.conn.execute("INSERT INTO favorite_drivers VALUES(2,'LEC')")
    await database.conn.commit()
    app.dependency_overrides[tools.require_admin_session] = lambda: tools.AdminContext(id=1,role="admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield database, app, client
    await database.close()


@pytest.mark.asyncio
async def test_product_report_counts_ordered_funnel_and_is_private(workspace):
    database, app, client = workspace
    now=time.time()
    for uid,event,created in [(1,'prediction_view',now-30),(1,'prediction_start',now-20),(2,'prediction_view',now-5),(2,'prediction_start',now-10),(3,'prediction_start',now-10)]:
        await database.conn.execute('INSERT INTO product_events VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uid),uid,event,'/predictions','browser',2026,1,0,created,0))
    await database.conn.execute("INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,first_retirement_driver,safety_car) VALUES(1,2026,1,'NOR','NOR','HAM','LEC','VER','PIA','NOR','HAM',0)")
    await database.conn.commit()
    result=await client.get('/api/admin/tools/product-analytics')
    assert result.status_code == 200,result.text
    assert result.json()['funnel'] == {'opened':2,'started':1,'saved':1}
    assert (await client.get('/api/admin/tools/product-analytics?days=7')).status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    assert 'user_id' not in result.text and 'NOR' not in result.text
    assert (await client.get('/api/admin/tools/product-analytics?days=999')).status_code == 422
    app.dependency_overrides.clear()
    assert (await client.get('/api/admin/tools/product-analytics')).status_code in {401,403}


@pytest.mark.asyncio
async def test_control_summary_filters_pagination_and_auth(workspace):
    database, app, client = workspace
    now = time.time()
    await database.conn.execute("INSERT INTO telegram_delivery_batches VALUES('control-test','Secret body',NULL,?,?)", (now+60,now-900000))
    await database.conn.executemany("INSERT INTO telegram_deliveries(event_key,telegram_id,timezone,updated,status) VALUES('control-test',?,'UTC',?,'unknown')", [(i,now) for i in range(51)])
    await database.conn.execute("INSERT INTO telegram_deliveries(event_key,telegram_id,timezone,updated,status) VALUES('control-test',100,'UTC',0,'pending')")
    await database.conn.execute("INSERT INTO telegram_deliveries(event_key,telegram_id,timezone,updated,status) VALUES('control-test',101,'UTC',0,'sent')")
    await database.conn.execute("INSERT INTO prediction_round_results(season,round,event_name,safety_car) VALUES(2026,14,'Test race',0)")
    await database.conn.commit()
    summary = await client.get('/api/admin/tools/control')
    assert summary.status_code == 200
    assert summary.json()['counts'] == {'unknown':51,'pending':1}
    assert summary.json()['oldest_pending'] == now-900000
    assert summary.json()['incomplete'][0]['missing'] == ['fastest_lap_driver','first_retirement_driver']
    page = await client.get('/api/admin/tools/control/deliveries')
    assert len(page.json()['items']) == 50 and page.json()['has_more']
    assert 'Secret body' not in page.text
    second = await client.get('/api/admin/tools/control/deliveries?offset=50')
    assert len(second.json()['items']) == 1 and not second.json()['has_more']
    assert not ({r['recipient'] for r in page.json()['items']} & {r['recipient'] for r in second.json()['items']})
    assert (await client.get('/api/admin/tools/control/deliveries?channel=webpush')).json()['items'] == []
    await database.conn.execute("INSERT INTO delivery_payloads(event_key,channel,payload) VALUES('control-test','webpush','{}')")
    await database.conn.commit()
    push = await client.get('/api/admin/tools/control/deliveries?channel=webpush&status=pending')
    assert len(push.json()['items']) == 1 and push.json()['items'][0]['channel'] == 'webpush'
    assert (await client.get('/api/admin/tools/control/deliveries?channel=telegram')).json()['items'] == []
    assert (await client.get('/api/admin/tools/control/deliveries?offset=-1')).status_code == 422
    assert (await client.get('/api/admin/tools/control/deliveries?status=invalid')).status_code == 422
    app.dependency_overrides.clear()
    for path in ['/control','/control/deliveries']:
        assert (await client.get('/api/admin/tools'+path)).status_code in {401,403}


@pytest.mark.asyncio
async def test_telegram_delivery_log_is_admin_only(workspace):
    database, app, client = workspace
    await database.conn.execute("INSERT INTO telegram_delivery_batches VALUES('test','Body',NULL,?,?)", (time.time()+60,time.time()))
    await database.conn.execute("INSERT INTO telegram_deliveries(event_key,telegram_id,timezone,updated,status) VALUES('test',900001,'UTC',?,'unknown')", (time.time(),))
    await database.conn.commit()
    result = await client.get('/api/admin/tools/telegram-deliveries')
    assert result.status_code == 200
    assert result.json()[0]['counts'] == {'unknown':1}
    app.dependency_overrides.clear()
    assert (await client.get('/api/admin/tools/telegram-deliveries')).status_code in {401,403}


@pytest.mark.asyncio
async def test_preview_is_inert_and_send_is_idempotent(workspace):
    database, _, client = workspace
    draft = {"title":"Test", "body":"Only test DB", "user_ids":"2, 2, 3"}
    result = await client.post("/api/admin/tools/notifications/preview", json=draft)
    assert result.status_code == 200, result.text
    assert result.json()["count"] == 1  # duplicates and non-members excluded
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0] == 0
    batch = result.json()["id"]
    url = f"/api/admin/tools/notifications/{batch}/send"
    assert (await client.post(url,json={"confirmation":""})).status_code == 422
    first, second = await asyncio.gather(*[client.post(url,json={"confirmation":"ОТПРАВИТЬ"}) for _ in range(2)])
    assert first.status_code == second.status_code == 200
    assert {first.json()["already_sent"],second.json()["already_sent"]} == {False, True}
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM web_notifications")).fetchone())[0] == 1
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM web_push_outbox")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_filters_snapshot_archive_expiry_and_author(workspace):
    database, app, client = workspace
    result = await client.post("/api/admin/tools/notifications/preview",json={"title":"T","body":"B","segment":"all","driver":"LEC"})
    assert result.json()["count"] == 1
    batch = result.json()["id"]
    url = f"/api/admin/tools/notifications/{batch}/send"
    app.dependency_overrides[tools.require_admin_session] = lambda: tools.AdminContext(id=4,role="admin")
    assert (await client.post(url,json={"confirmation":"ОТПРАВИТЬ"})).status_code == 403
    app.dependency_overrides[tools.require_admin_session] = lambda: tools.AdminContext(id=1,role="admin")
    await database.conn.execute("UPDATE users SET archived_at=? WHERE id=2", (datetime.now(timezone.utc).isoformat(),))
    await database.conn.commit()
    assert (await client.post(url,json={"confirmation":"ОТПРАВИТЬ"})).status_code == 409
    await database.conn.execute("UPDATE admin_notification_batches SET created_at=0 WHERE id=?",(batch,))
    await database.conn.commit()
    assert (await client.post(url,json={"confirmation":"ОТПРАВИТЬ"})).status_code == 409


@pytest.mark.asyncio
async def test_validations_and_insights(workspace):
    _, _, client = workspace
    for patch in [{"url":"https://evil.test"},{"url":"//evil.test"},{"url":"/\\evil.test"},{"title":" "},{"user_ids":""},{"driver":"A%"}]:
        result = await client.post("/api/admin/tools/notifications/preview",json={"title":"T","body":"B","user_ids":"2",**patch})
        assert result.status_code == 422, result.text
    result = await client.get("/api/admin/tools/insights",params={"days":7})
    assert result.status_code == 200, result.text
    assert result.json()["accounts"]["total"] == 4
    assert result.json()["reach"]["members"] == 3
    assert result.json()["drivers"] == [{"label":"LEC","users":1}]
    assert (await client.get("/api/admin/tools/insights?days=999")).status_code == 422


@pytest.mark.asyncio
async def test_push_is_opt_in_and_queued_only_for_frozen_audience(workspace, monkeypatch):
    database, _, client = workspace
    await database.conn.execute("INSERT INTO web_push_subscriptions(user_id,endpoint,subscription,created_at) VALUES(2,'https://example.invalid/test','{}',?)", (time.time(),))
    await database.conn.commit()
    monkeypatch.setattr(tools,"push_config",lambda:{"enabled":False})
    result = await client.post("/api/admin/tools/notifications/preview",json={"title":"T","body":"B","segment":"all","push":True})
    assert result.json()["count"] == 3
    assert result.json()["devices"] == 1
    batch = result.json()["id"]
    url = f"/api/admin/tools/notifications/{batch}/send"
    assert (await client.post(url,json={"confirmation":"ОТПРАВИТЬ"})).status_code == 409
    await database.conn.execute("INSERT INTO web_notification_members VALUES(3,?)", (time.time(),))
    await database.conn.commit()
    monkeypatch.setattr(tools,"push_config",lambda:{"enabled":True})
    result = await client.post(url,json={"confirmation":"ОТПРАВИТЬ"})
    assert result.status_code == 200, result.text
    assert result.json()["recipients"] == 3  # newly joined user not added
    assert result.json()["queued"] == 1
    job = await (await database.conn.execute("SELECT attempts,done FROM web_push_outbox")).fetchone()
    assert tuple(job) == (0,0)  # no real sending
    history = (await client.get("/api/admin/tools/notifications")).json()["items"]
    assert history[0]["recipients"] == 3 and history[0]["read_count"] == 0


@pytest.mark.asyncio
async def test_role_and_csrf_checks_are_not_bypassed(workspace, monkeypatch):
    database, app, client = workspace
    app.dependency_overrides.clear()
    auth = AuthService(database, MockMailer(), pepper="test-only")
    monkeypatch.setattr(auth_api,"get_auth_service",lambda:auth)
    assert (await client.get("/api/admin/tools/insights")).status_code == 401
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="test-only")
    await auth.register("admin-tools-test@example.com","FormulaOne-2026-Secure")
    session = await auth.verify_email("admin-tools-test@example.com",str(mailer.messages[-1]["code"]))
    client.cookies.set("turbotears_session",session.token)
    client.cookies.set("turbotears_csrf",session.csrf_token)
    assert (await client.get("/api/admin/tools/insights")).status_code == 403
    await database.conn.execute("UPDATE users SET role='admin' WHERE id=?",(session.user["id"],))
    await database.conn.commit()
    assert (await client.get("/api/admin/tools/insights")).status_code == 200
    draft = {"title":"T","body":"B","user_ids":"2"}
    assert (await client.post("/api/admin/tools/notifications/preview",json=draft)).status_code == 403
    result = await client.post("/api/admin/tools/notifications/preview",json=draft,headers={"X-CSRF-Token":session.csrf_token})
    assert result.status_code == 200, result.text
