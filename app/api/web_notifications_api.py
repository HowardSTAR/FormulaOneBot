import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.api.auth_api import require_hybrid_user_id
from app.services.web_notifications import connection, initialize, push_config, validate_subscription

router = APIRouter(prefix="/api/web-notifications", tags=["web-notifications"])

@router.get("")
async def inbox(before: int = Query(0, ge=0), user_id: int = Depends(require_hybrid_user_id)):
    async with connection() as conn:
        await initialize(conn)
        await conn.execute("INSERT OR IGNORE INTO web_notification_members VALUES(?,?)", (user_id,time.time()))
        await conn.commit()
        rows = await (await conn.execute("SELECT id,title,body,url,created_at,read_at FROM web_notifications WHERE user_id=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 31", (user_id,before,before))).fetchall()
        unread = await (await conn.execute("SELECT COUNT(*) FROM web_notifications WHERE user_id=? AND read_at IS NULL", (user_id,))).fetchone()
        return {"items":[dict(r) for r in rows[:30]], "next_before":rows[29]["id"] if len(rows)>30 else None, "unread":unread[0], "push":push_config()}

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
