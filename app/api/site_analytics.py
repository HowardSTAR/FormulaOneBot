"""First-party visit counts without storing IP addresses or browser fingerprints."""
import time
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.auth_api import COOKIE_NAME, require_hybrid_user_id
from app.db import db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
PUBLIC_ROUTES = frozenset(('/', '/account', '/compare', '/constructor-details', '/team-principal',
    '/constructors', '/driver-details', '/drivers', '/history', '/community', '/favorites', '/next-race',
    '/quali-results', '/race-details', '/race-results', '/reaction-game', '/reflex-grid-game', '/race-game',
    '/predictions', '/practice-results', '/contact-admin', '/settings', '/season', '/sprint-quali-results',
    '/sprint-results', '/voting', '/wiki', '/notifications', '/privacy', '/terms', '/legal/ip', '/about/data',
    '/account/delete', '/legal/notices', '/legal/assets', '/share'))


class Visit(BaseModel):
    path: str = Field(max_length=160, pattern=r"^/[a-zA-Z0-9/_-]*$")
    platform: Literal['telegram','pwa','browser','unknown'] = 'unknown'


@router.post("/visit")
async def record_visit(body: Visit, request: Request, response: Response):
    # Browsers send this on cross-origin requests; don't accept third-party traffic.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site tracking is not supported")
    if body.path not in PUBLIC_ROUTES:
        raise HTTPException(400, "Public route required")
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
    event: Literal['prediction_view','prediction_start','error','click','screen_view']
    season: int = Field(default=0, ge=0, le=2100)
    round: int = Field(default=0, ge=0, le=40)
    error_code: int = Field(default=0, ge=0, le=599)
    event_id: UUID | None = None
    action: Literal['calendar_open','session_open','results_open','compare_open','history_open','wiki_open',
        'prediction_submit','game_start','game_restart','settings_save','favorites_toggle','vote_submit',
        'review_open','filter_change','tab_change','back','expand','button','navigate','screen','game_hit'] = 'screen'
    destination: str = Field(default='', max_length=160, pattern=r'^(/[a-zA-Z0-9/_-]*)?$')


class NotificationEntry(Visit):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{32}$')
    event_id: UUID


@router.post('/notification-entry')
async def notification_entry(body: NotificationEntry, request: Request, response: Response):
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site tracking is not supported')
    user_id = None
    try:
        user_id = await require_hybrid_user_id(request=request,
            x_telegram_init_data=request.headers.get('x-telegram-init-data'),
            authorization=request.headers.get('authorization'),
            x_csrf_token=request.headers.get('x-csrf-token'), cookie_token=request.cookies.get(COOKIE_NAME))
    except HTTPException as exc:
        if exc.status_code not in (401, 403):
            raise
    try:
        visitor = str(uuid.UUID(request.cookies.get('turbotears_visitor', '')))
    except ValueError:
        visitor = str(uuid.uuid4())
    from app.services.notification_clicks import record, viewer_key
    async with db.write_lock:
        link = await (await db.conn.execute(
            'SELECT destination,button FROM notification_button_links WHERE token=?', (body.token,),
        )).fetchone()
        if (not link or link['destination'] != body.path or body.path not in PUBLIC_ROUTES
                or not (link['button'] in ('leaderboard', 'community') or link['button'].startswith('bot:arrival:'))):
            raise HTTPException(400, 'Valid notification destination required')
        viewer = viewer_key(visitor, user_id)
        count = (await (await db.conn.execute(
            'SELECT COUNT(*) FROM notification_button_events WHERE viewer=? AND created>?',
            (viewer, time.time()-60),
        )).fetchone())[0]
        if count >= 120:
            raise HTTPException(429, 'Too many analytics events')
        await record(db.conn, body.token, str(body.event_id), visitor, user_id)
        await db.conn.commit()
    response.set_cookie('turbotears_visitor', visitor, max_age=365*86400, httponly=True,
                        secure=request.url.scheme == 'https', samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}


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
    interaction = body.event in ('click', 'screen_view')
    if interaction and (body.event_id is None or body.path not in PUBLIC_ROUTES or (body.destination and body.destination not in PUBLIC_ROUTES)):
        raise HTTPException(400, 'Public route and event ID required')
    if body.event in ('prediction_view','prediction_start') and (user_id is None or body.path != '/predictions' or not body.season or not body.round):
        raise HTTPException(400, 'Authenticated prediction round required')
    try:
        visitor = str(uuid.UUID(request.cookies.get('turbotears_visitor','')))
    except ValueError:
        visitor = str(uuid.uuid4())
    now = time.time()
    async with db.write_lock:
        if interaction:
            count = (await (await db.conn.execute('SELECT COUNT(*) FROM ui_events WHERE visitor_id=? AND created>?', (visitor,now-60))).fetchone())[0]
            if count >= 120:
                raise HTTPException(429, 'Too many analytics events')
            await db.conn.execute('INSERT OR IGNORE INTO ui_events VALUES(?,?,?,?,?,?,?,?,?)',
                (str(body.event_id),visitor,user_id,body.event,body.path,body.action,body.destination,body.platform,now))
            from app.services.posthog_bridge import enqueue
            await enqueue(db.conn,str(body.event_id),visitor,user_id,
                '$pageview' if body.event == 'screen_view' else 'button_clicked',
                {'path':body.path,'action':body.action,'destination':body.destination,'platform':body.platform,
                 '$current_url':body.path}, now)
            await db.conn.execute('DELETE FROM ui_events WHERE created<?',(now-366*86400,))
        else:
            cursor = await db.conn.execute('INSERT OR IGNORE INTO product_events VALUES(?,?,?,?,?,?,?,?,?,?)',
                (visitor,user_id,body.event,body.path,body.platform,body.season,body.round,int(now)//300,now,body.error_code))
            if cursor.rowcount and body.event in ('prediction_view', 'prediction_start'):
                from app.services.posthog_bridge import enqueue
                await enqueue(db.conn,str(uuid.uuid4()),visitor,user_id,body.event,
                    {'path':body.path,'season':body.season,'round':body.round,'platform':body.platform},now)
        await db.conn.execute('DELETE FROM product_events WHERE created<?',(now-366*86400,))
        await db.conn.commit()
    response.set_cookie('turbotears_visitor',visitor,max_age=365*86400,httponly=True,secure=request.url.scheme=='https',samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok':True}
