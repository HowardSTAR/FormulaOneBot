"""First-party visit counts without storing IP addresses or browser fingerprints."""
import time
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.auth_api import COOKIE_NAME, require_hybrid_user_id
from app.db import db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class Visit(BaseModel):
    path: str = Field(max_length=160, pattern=r"^/[a-zA-Z0-9/_-]*$")
    platform: Literal['telegram','pwa','browser','unknown'] = 'unknown'


@router.post("/visit")
async def record_visit(body: Visit, request: Request, response: Response):
    # Browsers send this on cross-origin requests; don't accept third-party traffic.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site tracking is not supported")
    raw = request.cookies.get("turbotears_visitor", "")
    try:
        visitor = str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        visitor = str(uuid.uuid4())
    user_id = None
    try:
        user_id = await require_hybrid_user_id(
            request=request,
            x_telegram_init_data=request.headers.get("x-telegram-init-data"),
            authorization=request.headers.get("authorization"),
            x_csrf_token=request.headers.get("x-csrf-token"),
            cookie_token=request.cookies.get(COOKIE_NAME),
        )
    except HTTPException as exc:
        if exc.status_code not in (401, 403):
            raise
    bucket = int(time.time()) // 300
    assert db.conn is not None
    async with db.write_lock:
        await db.conn.execute(
            "INSERT OR IGNORE INTO site_visits(visitor_id, user_id, path, bucket,platform) VALUES (?, ?, ?, ?,?)",
            (visitor, user_id, body.path, bucket,body.platform),
        )
        # Preserve authentication state at the time of a visit, including shared browsers.
        await db.conn.execute("DELETE FROM site_visits WHERE bucket < ?", (bucket - 366 * 288,))
        await db.conn.commit()
    response.set_cookie("turbotears_visitor", visitor, max_age=365 * 86400,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}


class ProductEvent(Visit):
    event: Literal['prediction_view','prediction_start','error']
    season: int = Field(default=0, ge=0, le=2100)
    round: int = Field(default=0, ge=0, le=40)
    error_code: int = Field(default=0, ge=0, le=599)


@router.post('/event')
async def record_event(body: ProductEvent, request: Request, response: Response):
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site tracking is not supported')
    user_id = None
    try:
        user_id = await require_hybrid_user_id(request=request,
            x_telegram_init_data=request.headers.get('x-telegram-init-data'),
            authorization=request.headers.get('authorization'),
            x_csrf_token=request.headers.get('x-csrf-token'), cookie_token=request.cookies.get(COOKIE_NAME))
    except HTTPException as exc:
        if exc.status_code not in (401,403):
            raise
    if body.event != 'error' and (user_id is None or body.path != '/predictions' or not body.season or not body.round):
        raise HTTPException(400, 'Authenticated prediction round required')
    try:
        visitor = str(uuid.UUID(request.cookies.get('turbotears_visitor','')))
    except ValueError:
        visitor = str(uuid.uuid4())
    now = time.time()
    async with db.write_lock:
        await db.conn.execute('INSERT OR IGNORE INTO product_events VALUES(?,?,?,?,?,?,?,?,?,?)',
            (visitor,user_id,body.event,body.path,body.platform,body.season,body.round,int(now)//300,now,body.error_code))
        await db.conn.execute('DELETE FROM product_events WHERE created<?',(now-366*86400,))
        await db.conn.commit()
    response.set_cookie('turbotears_visitor',visitor,max_age=365*86400,httponly=True,secure=request.url.scheme=='https',samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok':True}
