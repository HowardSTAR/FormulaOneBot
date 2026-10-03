import json
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from app.api.auth_api import require_hybrid_user_id
from app.services.web_notifications import connection, initialize, push_config, validate_subscription

router = APIRouter(prefix="/api/web-notifications", tags=["web-notifications"])

@router.get('/unread-count')
async def unread_count(user_id: int = Depends(require_hybrid_user_id)):
    # Homepage inspection must not subscribe users or mark messages as read.
    async with connection() as conn:
        row = await (await conn.execute("SELECT COUNT(*) FROM web_notifications WHERE user_id=? AND read_at IS NULL AND (event_key NOT LIKE 'admin-error:%' OR EXISTS(SELECT 1 FROM users u WHERE u.id=web_notifications.user_id AND u.role IN ('admin','superadmin') AND u.archived_at IS NULL))", (user_id,))).fetchone()
        return {'unread': row[0]}

@router.get("")
async def inbox(before: int = Query(0, ge=0), user_id: int = Depends(require_hybrid_user_id), category: Literal['all', 'results', 'predictions', 'voting', 'reminders', 'admin'] = 'all'):
    async with connection() as conn:
        await initialize(conn)
        await conn.execute("INSERT OR IGNORE INTO web_notification_members VALUES(?,?)", (user_id,time.time()))
        await conn.commit()
        visible = "(event_key NOT LIKE 'admin-error:%' OR EXISTS(SELECT 1 FROM users u WHERE u.id=web_notifications.user_id AND u.role IN ('admin','superadmin') AND u.archived_at IS NULL))"
        category_filter = {'results': "(url LIKE '%-results%' OR event_key LIKE 'weekly-race:%')", 'predictions': "url LIKE '/predictions%'", 'voting': "url LIKE '/voting%'", 'reminders': "event_key LIKE 'reminder:%'", 'admin': "event_key LIKE 'admin-error:%'"}.get(category, '1=1')
        visible += f" AND ({category_filter})"
        rows = await (await conn.execute(f"SELECT id,title,body,url,created_at,read_at,event_key,e.expires FROM web_notifications LEFT JOIN web_notification_expirations e ON e.notification_id=web_notifications.id WHERE user_id=? AND (?=0 OR id<?) AND {visible} ORDER BY id DESC LIMIT 31", (user_id,before,before))).fetchall()
        unread = await (await conn.execute(f"SELECT COUNT(*) FROM web_notifications WHERE user_id=? AND read_at IS NULL AND {visible}", (user_id,))).fetchone()
        items = [{**{k:r[k] for k in r.keys() if k not in {'event_key', 'expires'}}, "historical_snapshot": '-results' in r['url'] or r['url'].startswith(('/predictions', '/voting')) or r['event_key'].startswith('weekly-race:'), "priority": r["event_key"].split(":")[1] if r["event_key"].startswith("admin-error:") else None,
                  "reminder": reminder_metadata(r['event_key'], r['expires'])} for r in rows[:30]]
        return {"items":items, "next_before":rows[29]["id"] if len(rows)>30 else None, "unread":unread[0], "push":push_config()}


def reminder_metadata(event_key, expires):
    # The stored push expiration is the scheduled UTC start, not created_at +
    # lead time (delivery can be delayed). Never infer a start from message text.
    if not event_key.startswith('reminder:'):
        return None
    from app.services.reminder_status import SESSION_MINUTES
    parts = event_key.split(':')
    kind = parts[3] if len(parts) == 5 else ''
    if kind not in SESSION_MINUTES:
        return None
    try:
        start = datetime.fromtimestamp(float(expires), timezone.utc).isoformat() if expires is not None else None
    except (ValueError, TypeError, OverflowError, OSError):
        start = None
    return {'kind': kind, 'start_utc': start, 'duration_minutes': SESSION_MINUTES[kind]}

class ReadBody(BaseModel):
    through_id: int = Field(ge=1)

@router.post("/read")
async def mark_read(body: ReadBody, user_id: int = Depends(require_hybrid_user_id)):
    async with connection() as conn:
        await initialize(conn)
        await conn.execute("UPDATE web_notifications SET read_at=? WHERE user_id=? AND id<=? AND read_at IS NULL", (time.time(),user_id,body.through_id))
        await conn.commit()
    return {"ok":True}

class SubscriptionBody(BaseModel):
    endpoint: str = Field(max_length=2048)
    p256dh: str = Field(max_length=128)
    auth: str = Field(max_length=32)

@router.post("/subscription")
async def subscribe(body: SubscriptionBody, user_id: int = Depends(require_hybrid_user_id)):
    if not push_config()["enabled"]:
        raise HTTPException(503, "Push ещё не настроен на сервере")
    subscription = {"endpoint":body.endpoint,"keys":{"p256dh":body.p256dh,"auth":body.auth}}
    try:
        validate_subscription(subscription)
    except (ValueError, TypeError):
        raise HTTPException(400, "Некорректная push-подписка")
    async with connection() as conn:
        await initialize(conn)
        await conn.execute("BEGIN IMMEDIATE")
        existing = await (await conn.execute("SELECT user_id FROM web_push_subscriptions WHERE endpoint=?", (body.endpoint,))).fetchone()
        if existing and existing[0] != user_id:
            raise HTTPException(409, "Эта подписка принадлежит другому аккаунту. Отключите её в браузере и подключите заново.")
        count = await (await conn.execute("SELECT COUNT(*) FROM web_push_subscriptions WHERE user_id=?", (user_id,))).fetchone()
        if not existing and count[0]>=10:
            raise HTTPException(400, "Достигнут лимит устройств")
        await conn.execute("INSERT OR IGNORE INTO web_notification_members VALUES(?,?)", (user_id,time.time()))
        await conn.execute("INSERT INTO web_push_subscriptions(user_id,endpoint,subscription,created_at) VALUES(?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET subscription=excluded.subscription", (user_id,body.endpoint,json.dumps(subscription),time.time()))
        await conn.commit()
    return {"ok":True}

class EndpointBody(BaseModel):
    endpoint: str = Field(max_length=2048)

@router.delete("/subscription")
async def unsubscribe(body: EndpointBody, user_id: int = Depends(require_hybrid_user_id)):
    async with connection() as conn:
        await initialize(conn)
        await conn.execute("DELETE FROM web_push_subscriptions WHERE user_id=? AND endpoint=?", (user_id,body.endpoint))
        await conn.commit()
    return {"ok":True}
