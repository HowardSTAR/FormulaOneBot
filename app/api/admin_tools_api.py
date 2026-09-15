"""Admin-only insights and explicitly confirmed, idempotent inbox notifications.

No Telegram posts or synchronous network sends. Push uses the existing outbox.
"""
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import unquote

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from app.api.admin_api import AdminContext, require_admin_session
from app.db import db
from app.services.web_notifications import push_config

router = APIRouter(prefix="/api/admin/tools", tags=["administration"])


@router.get('/product-analytics')
async def product_analytics(response: Response, days: int=Query(30,ge=1,le=90), actor: AdminContext=Depends(require_admin_session)):
    from app.services.product_analytics import report
    response.headers['Cache-Control']='no-store'
    async with connection() as conn:
        return await report(conn,time.time()-days*86400)


@router.get('/control')
async def control_summary(actor: AdminContext = Depends(require_admin_session)):
    now = time.time()
    async with connection() as conn:
        counts = await (await conn.execute("SELECT status,COUNT(*) n FROM telegram_deliveries WHERE updated>=? OR status IN ('pending','retry','sending') GROUP BY status",(now-7*86400,))).fetchall()
        oldest = await (await conn.execute("SELECT MIN(b.created) FROM telegram_deliveries d JOIN telegram_delivery_batches b USING(event_key) WHERE d.status IN ('pending','retry','sending')")).fetchone()
        recoveries = await (await conn.execute("SELECT state,COUNT(*) n FROM prediction_recovery WHERE created>=? GROUP BY state",(now-7*86400,))).fetchall()
        missing = await (await conn.execute("SELECT season,round,event_name,fastest_lap_driver,first_retirement_driver,safety_car,calculated_at FROM prediction_round_results WHERE fastest_lap_driver IS NULL OR first_retirement_driver IS NULL OR safety_car IS NULL ORDER BY season DESC,round DESC LIMIT 30")).fetchall()
        return {'as_of':now,'counts':{r['status']:r['n'] for r in counts},'oldest_pending':oldest[0],
                'recoveries':{r['state']:r['n'] for r in recoveries},'push_configured':push_config()['enabled'],
                'incomplete':[{'season':r['season'],'round':r['round'],'event_name':r['event_name'],
                               'missing':[key for key in ('fastest_lap_driver','first_retirement_driver','safety_car') if r[key] is None]} for r in missing]}


@router.get('/control/deliveries')
async def control_deliveries(
    channel: Literal['all','telegram','webpush']='all',
    status: Literal['all','attention','pending','retry','sending','sent','unknown','failed','blocked','expired','cancelled']='attention',
    offset: int=Query(0,ge=0,le=100000), actor: AdminContext=Depends(require_admin_session),
):
    conditions, params = [], []
    if channel != 'all':
        conditions.append("COALESCE(p.channel,'telegram')=?"); params.append(channel)
    if status == 'attention':
        conditions.append("d.status IN ('unknown','failed','blocked','retry')")
    elif status != 'all':
        conditions.append('d.status=?'); params.append(status)
    where = ' WHERE '+' AND '.join(conditions) if conditions else ''
    async with connection() as conn:
        rows = await (await conn.execute("SELECT d.event_key,d.telegram_id recipient,d.status,d.attempts,d.next_attempt,d.updated,d.message_id,d.error,COALESCE(p.channel,'telegram') channel,b.expires FROM telegram_deliveries d JOIN telegram_delivery_batches b USING(event_key) LEFT JOIN delivery_payloads p USING(event_key)"+where+' ORDER BY d.updated DESC,d.event_key,d.telegram_id LIMIT 51 OFFSET ?',(*params,offset))).fetchall()
        return {'items':[dict(row) for row in rows[:50]],'has_more':len(rows)>50}


class RecoveryRequest(BaseModel):
    season: int = Field(ge=1950, le=2100)
    round: int = Field(ge=1, le=40)


class RecoveryConfirmation(BaseModel):
    confirmation: Literal['ПЕРЕСЧИТАТЬ']


@router.get('/prediction-recovery')
async def recovery_history(actor: AdminContext = Depends(require_admin_session)):
    from app.services.prediction_recovery import history
    return await history()


@router.post('/prediction-recovery/preview')
async def recovery_preview(data: RecoveryRequest, actor: AdminContext = Depends(require_admin_session)):
    from app.services.prediction_recovery import prepare
    try:
        return await prepare(data.season,data.round)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


@router.post('/prediction-recovery/{identifier}/apply')
async def recovery_apply(identifier: str, data: RecoveryConfirmation, actor: AdminContext = Depends(require_admin_session)):
    from app.services.prediction_recovery import apply
    try:
        return await apply(identifier,actor.id)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc


@router.get('/telegram-deliveries')
async def telegram_delivery_log(actor: AdminContext = Depends(require_admin_session)):
    async with connection() as conn:
        exists = await (await conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_delivery_batches'")).fetchone()
        if not exists:
            return []
        batches = await (await conn.execute("SELECT b.event_key,b.created,b.expires,COALESCE(p.channel,'telegram') channel FROM telegram_delivery_batches b LEFT JOIN delivery_payloads p USING(event_key) ORDER BY created DESC LIMIT 30")).fetchall()
        result = []
        for batch in batches:
            counts = await (await conn.execute('SELECT status,COUNT(*) n FROM telegram_deliveries WHERE event_key=? GROUP BY status', (batch['event_key'],))).fetchall()
            result.append({**dict(batch), 'counts': {row['status']:row['n'] for row in counts}})
        return result


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=10000")
        yield conn


class NotificationDraft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1500)
    url: str = Field(default="/notifications", max_length=500)
    segment: Literal["selected", "all", "admins", "active", "inactive"] = "selected"
    user_ids: str = Field(default="", max_length=4000)
    driver: str = Field(default="", max_length=3)
    push: bool = False

    @field_validator("title", "body")
    @classmethod
    def text(cls, value):
        if not value.strip():
            raise ValueError("Введите текст")
        return value.strip()

    @field_validator("url")
    @classmethod
    def local_url(cls, value):
        decoded = unquote(value)
        if not decoded.startswith("/") or decoded.startswith("//") or "%" in decoded or any(ord(c) < 32 or c == "\\" for c in decoded):
            raise ValueError("Нужна внутренняя ссылка, например /predictions")
        return value

    @field_validator("driver")
    @classmethod
    def code(cls, value):
        value = value.strip().upper()
        if value and not re.fullmatch("[A-Z]{3}", value):
            raise ValueError("Введите трёхбуквенный код пилота")
        return value


class SendConfirmation(BaseModel):
    confirmation: str


async def audience(conn, data):
    clauses = ["u.archived_at IS NULL"]
    params = []
    if data.segment == "selected":
        tokens = re.split(r"[,\s]+", data.user_ids.strip())
        if not tokens or len(tokens) > 500 or any(not re.fullmatch(r"[0-9]{1,18}", v) or int(v) <= 0 for v in tokens):
            raise HTTPException(422, "Укажите 1–500 внутренних ID пользователей через запятую")
        ids = sorted({int(v) for v in tokens})
        clauses.append("u.id IN (" + ",".join("?" for _ in ids) + ")")
        params.extend(ids)
    elif data.segment == "admins":
        clauses.append("u.role IN ('admin','superadmin')")
    elif data.segment in {"active", "inactive"}:
        clauses.append(("NOT " if data.segment == "inactive" else "") + "EXISTS (SELECT 1 FROM user_activity_events e WHERE e.user_id=u.id AND datetime(e.occurred_at)>=datetime('now','-30 days'))")
    if data.driver:
        clauses.append("EXISTS (SELECT 1 FROM favorite_drivers f WHERE f.user_id=u.id AND upper(f.driver_code)=?)")
        params.append(data.driver)
    return await (await conn.execute("SELECT u.id,u.display_name,u.telegram_username FROM users u JOIN web_notification_members m ON m.user_id=u.id WHERE " + " AND ".join(clauses) + " ORDER BY u.id LIMIT 1001", params)).fetchall()


async def audit(conn, actor, action, details):
    await conn.execute("INSERT INTO admin_audit_log(actor_user_id,action,details_json,created_at) VALUES(?,?,?,?)",
                       (actor, action, json.dumps(details), datetime.now(timezone.utc).isoformat()))


@router.post("/notifications/preview")
async def preview(data: NotificationDraft, admin: AdminContext = Depends(require_admin_session)):
    async with connection() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        targets = await audience(conn, data)
        if len(targets) > 1000:
            raise HTTPException(422, "Больше 1000 получателей — сузьте аудиторию")
        batch_id = uuid.uuid4().hex
        await conn.execute("INSERT INTO admin_notification_batches(id,actor_id,title,body,url,filters,push,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (batch_id,admin.id,data.title,data.body,data.url,json.dumps({"segment":data.segment,"driver":data.driver}),int(data.push),time.time()))
        await conn.executemany("INSERT INTO admin_notification_targets VALUES(?,?)", [(batch_id,t["id"]) for t in targets])
        devices = (await (await conn.execute("SELECT COUNT(*) FROM web_push_subscriptions s JOIN admin_notification_targets t ON t.user_id=s.user_id WHERE t.batch_id=?", (batch_id,))).fetchone())[0]
        await audit(conn,admin.id,"notification.preview",{"batch_id":batch_id,"audience":len(targets)})
        await conn.commit()
        return {"id":batch_id,"count":len(targets),"devices":devices,"sample":[dict(t) for t in targets[:20]],"push_enabled":push_config()["enabled"]}


@router.post("/notifications/{batch_id}/send")
async def send(batch_id: str, data: SendConfirmation, admin: AdminContext = Depends(require_admin_session)):
    if data.confirmation != "ОТПРАВИТЬ":
        raise HTTPException(422, "Введите ОТПРАВИТЬ")
    async with connection() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        batch = await (await conn.execute("SELECT * FROM admin_notification_batches WHERE id=?", (batch_id,))).fetchone()
        if not batch:
            raise HTTPException(404, "Предпросмотр не найден")
        if batch["actor_id"] != admin.id:
            raise HTTPException(403, "Отправить может только автор предпросмотра")
        if batch["sent_at"] is not None:
            return {"recipients":batch["recipients"],"queued":batch["queued"],"already_sent":True}
        now = time.time()
        if now-batch["created_at"] > 3600:
            raise HTTPException(409, "Предпросмотр старше часа — проверьте аудиторию заново")
        if batch["push"] and not push_config()["enabled"]:
            raise HTTPException(409, "Push не настроен. Отключите push и создайте новый предпросмотр")
        filters = json.loads(batch["filters"])
        # Freeze audience at preview; recheck archive/membership/role at send.
        targets = await (await conn.execute("""SELECT t.user_id FROM admin_notification_targets t
            JOIN users u ON u.id=t.user_id JOIN web_notification_members m ON m.user_id=u.id
            WHERE t.batch_id=? AND u.archived_at IS NULL""" +
            (" AND u.role IN ('admin','superadmin')" if filters["segment"] == "admins" else ""), (batch_id,))).fetchall()
        if not targets:
            raise HTTPException(409, "Нет доступных получателей")
        key = "admin-manual:" + batch_id
        await conn.execute("INSERT INTO web_notification_events VALUES(?,?)", (key,now))
        queued = 0
        for target in targets:
            row = await conn.execute("INSERT INTO web_notifications(user_id,event_key,title,body,url,created_at) VALUES(?,?,?,?,?,?)",
                                     (target[0],key,batch["title"],batch["body"],batch["url"],now))
            if batch["push"]:
                job = await conn.execute("INSERT INTO web_push_outbox(notification_id,subscription_id,next_attempt) SELECT ?,id,? FROM web_push_subscriptions WHERE user_id=?", (row.lastrowid,now,target[0]))
                queued += job.rowcount
        await conn.execute("UPDATE admin_notification_batches SET sent_at=?,recipients=?,queued=? WHERE id=?", (now,len(targets),queued,batch_id))
        await audit(conn,admin.id,"notification.sent",{"batch_id":batch_id,"recipients":len(targets),"queued_push":queued})
        await conn.commit()
        return {"recipients":len(targets),"queued":queued,"already_sent":False}


@router.get("/notifications")
async def history(_: AdminContext = Depends(require_admin_session)):
    async with connection() as conn:
        items = await (await conn.execute("""SELECT b.*,
            (SELECT COUNT(*) FROM admin_notification_targets t WHERE t.batch_id=b.id) AS audience,
            (SELECT COUNT(*) FROM web_notifications n WHERE n.event_key='admin-manual:'||b.id AND n.read_at IS NOT NULL) AS read_count
            FROM admin_notification_batches b ORDER BY b.created_at DESC LIMIT 50""")).fetchall()
        return {"items":[dict(r) for r in items]}


@router.get("/insights")
async def insights(days: int = Query(30, ge=1, le=90), _: AdminContext = Depends(require_admin_session)):
    async with connection() as conn:
        async def rows(sql, params=()):
            return [dict(r) for r in await (await conn.execute(sql, params)).fetchall()]
        since = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        accounts = (await rows("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN datetime(created_at)>=datetime(?) THEN 1 ELSE 0 END) AS new_users,
            SUM(CASE WHEN telegram_id IS NOT NULL THEN 1 ELSE 0 END) AS telegram_linked,
            SUM(CASE WHEN email_verified=1 THEN 1 ELSE 0 END) AS verified_email
            FROM users WHERE archived_at IS NULL""", (since,)))[0]
        reach = (await rows("""SELECT COUNT(*) AS members,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM web_push_subscriptions s WHERE s.user_id=m.user_id) THEN 1 ELSE 0 END) AS push_users
            FROM web_notification_members m JOIN users u ON u.id=m.user_id WHERE u.archived_at IS NULL"""))[0]
        inbox = (await rows("""SELECT COUNT(*) AS total,SUM(CASE WHEN read_at IS NOT NULL THEN 1 ELSE 0 END) AS read_count
            FROM web_notifications WHERE created_at>=?""", (time.time()-days*86400,)))[0]
        queue = (await rows("""SELECT SUM(CASE WHEN done=0 AND attempts<4 THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN done=0 AND attempts>=4 THEN 1 ELSE 0 END) AS exhausted FROM web_push_outbox"""))[0]
        shared = (await rows("""SELECT SUM(CASE WHEN d.status IN ('pending','retry','sending') THEN 1 ELSE 0 END) pending,
            SUM(CASE WHEN d.status IN ('failed','unknown','blocked') THEN 1 ELSE 0 END) exhausted
            FROM telegram_deliveries d JOIN delivery_payloads p USING(event_key) WHERE p.channel='webpush'"""))[0]
        queue = {key: (queue[key] or 0)+(shared[key] or 0) for key in queue}
        visitors = (await rows("""SELECT COUNT(*) AS unique_browsers,SUM(CASE WHEN days>1 THEN 1 ELSE 0 END) AS returning_browsers
            FROM (SELECT visitor_id,COUNT(DISTINCT CAST(bucket/288 AS INTEGER)) AS days FROM site_visits WHERE bucket>=? GROUP BY visitor_id)""", (int(time.time()-days*86400)//300,)))[0]
        drivers = await rows("""SELECT f.driver_code AS label,COUNT(DISTINCT f.user_id) AS users FROM favorite_drivers f
            JOIN users u ON u.id=f.user_id WHERE u.archived_at IS NULL GROUP BY f.driver_code ORDER BY users DESC LIMIT 12""")
        registrations = await rows("SELECT date(created_at) AS day,COUNT(*) AS users FROM users WHERE archived_at IS NULL AND datetime(created_at)>=datetime(?) GROUP BY date(created_at) ORDER BY day", (since,))
        return {"days":days,"accounts":accounts,"reach":reach,"inbox":inbox,"queue":queue,"visitors":visitors,"drivers":drivers,"registrations":registrations,"push_enabled":push_config()["enabled"]}
