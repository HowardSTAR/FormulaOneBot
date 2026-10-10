"""Sharing never sends a message itself: Telegram opens a user-controlled dialog."""
import asyncio
import html
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from app.api.auth_api import COOKIE_NAME, require_hybrid_user_id
from app.db import db
from app.race_rules import TRACKS
from app.services import engagement as service

router = APIRouter(prefix="/api/engagement", tags=["Community"])
public_router = APIRouter()


async def optional_account(request: Request):
    try:
        return await require_hybrid_user_id(request=request,
            x_telegram_init_data=request.headers.get('x-telegram-init-data'),
            authorization=request.headers.get('authorization'),
            x_csrf_token=request.headers.get('x-csrf-token'), cookie_token=request.cookies.get(COOKIE_NAME))
    except HTTPException as exc:
        if exc.status_code == 401: return None
        raise


class ShareRequest(BaseModel):
    kind: Literal['profile', 'prediction', 'race', 'league', 'recap', 'history']
    consent: Literal[True]
    season: int = Field(default=2026, ge=1950, le=2100)
    round: int = Field(default=1, ge=1, le=40)
    track_id: str = 'emerald-loop-v2'
    league_id: int = Field(default=0, ge=0)
    history_kind: Literal['drivers', 'constructors'] = 'drivers'
    ids: list[str] = Field(default_factory=list, max_length=3)
    start_year: int = Field(default=2022, ge=1950)
    end_year: int = Field(default=2026, ge=1950)

    @model_validator(mode='after')
    def valid_context(self):
        current = datetime.now(timezone.utc).year
        if self.season > current: raise ValueError('Сезон ещё не начался')
        if self.kind == 'race' and self.track_id not in TRACKS: raise ValueError('Неизвестная версия трассы')
        if self.kind == 'league' and not self.league_id: raise ValueError('Выберите лигу')
        if self.kind == 'history' and (not self.ids or len(set(self.ids)) != len(self.ids)
            or any(not re.fullmatch(r'[a-z0-9_-]{1,60}', v) for v in self.ids)
            or not (1950 if self.history_kind == 'drivers' else 1958) <= self.start_year <= self.end_year <= current
            or self.end_year - self.start_year > 9):
            raise ValueError('Выберите до трёх участников и до десяти сезонов')
        return self


@router.post('/shares')
async def create_share(body: ShareRequest, request: Request, user_id=Depends(optional_account)):
    if request.headers.get('sec-fetch-site') == 'cross-site': raise HTTPException(403, 'Cross-site sharing is not supported')
    try:
        token = await service.create_share(user_id, body.kind, body.model_dump())
        return await service.public_share(token, str(request.base_url).rstrip('/'))
    except PermissionError as exc: raise HTTPException(401 if user_id is None else 403, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.get('/shares/{token}')
async def public_share(token: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try: return await service.public_share(token, str(request.base_url).rstrip('/'))
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


@router.get('/shares/{token}/image.jpg')
async def card_image(token: str):
    try: item = await service.public_share(token)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    return Response(await asyncio.to_thread(service.card_image, item), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@router.get('/shares/{token}/destination')
async def destination(token: str, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try: return {'path': await service.share_target(token)}
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


class EventRequest(BaseModel):
    token: str = Field(pattern='^' + service.TOKEN_PATTERN + '$')
    event: Literal['share_opened', 'share_sent', 'share_copied', 'arrival']


@router.post('/event')
async def event(body: EventRequest, request: Request, response: Response, user_id=Depends(optional_account)):
    if request.headers.get('sec-fetch-site') == 'cross-site': raise HTTPException(403, 'Cross-site tracking is not supported')
    try: visitor = str(uuid.UUID(request.cookies.get('turbotears_visitor', '')))
    except ValueError: visitor = str(uuid.uuid4())
    try:
        await service.record_event(body.token, visitor, body.event)
        if body.event == 'arrival': await service.arrival(user_id, body.token)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    response.set_cookie('turbotears_visitor', visitor, httponly=True, secure=request.url.scheme == 'https', samesite='lax', max_age=365*86400)
    return {'ok': True}


@router.post('/shares/{token}/revoke')
async def revoke(token: str, user_id: int = Depends(require_hybrid_user_id)):
    async with db.write_lock:
        cursor = await db.conn.execute('UPDATE engagement_shares SET revoked=1 WHERE token=? AND owner_id=?', (token, user_id))
        await db.conn.commit()
    if not cursor.rowcount: raise HTTPException(404, 'Карточка недоступна')
    return {'ok': True}


@router.get('/mine')
async def mine(response: Response, user_id: int = Depends(require_hybrid_user_id)):
    response.headers['Cache-Control'] = 'private, no-store'
    return await service.personal_engagement(user_id)


@router.get('/weekly')
async def weekly(response: Response, period: Literal['current', 'previous'] = 'current', week: date | None = None):
    response.headers['Cache-Control'] = 'no-store'
    now = datetime.now(timezone.utc)
    if week is not None:
        requested = datetime.combine(week, datetime.min.time(), tzinfo=timezone.utc)
        if week.weekday() != 0 or requested >= service.weekly_period(now)[1]:
            raise HTTPException(422, 'Выберите начало завершённой недели — понедельник.')
        return await service.weekly(requested)
    return await service.weekly(now - timedelta(days=7) if period == 'previous' else now)


@router.get('/weekly/me')
async def personal_weekly(response: Response, user_id: int = Depends(require_hybrid_user_id)):
    from app.services.weekly_race_overtakes import personal_weekly as status
    response.headers['Cache-Control'] = 'private, no-store'
    return {'user_id':user_id,'weekly':await status(user_id)}


@router.get('/challenges/{token}')
async def challenge(token: str, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try: return await service.challenge(token)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


@router.post('/shares/{token}/telegram')
async def prepare_telegram(token: str, user_id: int = Depends(require_hybrid_user_id)):
    try: item = await service.public_share(token)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    account = await (await db.conn.execute('SELECT telegram_id FROM users WHERE id=?', (user_id,))).fetchone()
    origin, bot_token = service.public_origin(), os.getenv('BOT_TOKEN')
    if not account or not account[0] or not origin or not origin.startswith('https://') or not bot_token:
        raise HTTPException(503, 'Для отправки карточки нужен Telegram и настроенный публичный HTTPS-адрес')
    caption = '\n'.join([item['title'], item['headline'], *item['lines']])[:950]
    message = {'type': 'photo', 'id': token, 'photo_url': item['image_url'], 'thumbnail_url': item['image_url'],
               'photo_width': 1200, 'photo_height': 630, 'caption': caption,
               'reply_markup': {'inline_keyboard': [[{'text': item['cta'], 'url': item['share_url']}]]}}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.post(f'https://api.telegram.org/bot{bot_token}/savePreparedInlineMessage', json={
                'user_id': account[0], 'result': message, 'allow_user_chats': True, 'allow_group_chats': True, 'allow_channel_chats': True}) as response:
                data = await response.json()
                if not data.get('ok'): raise ValueError('Telegram не подготовил карточку')
        return {'id': data['result']['id']}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
        # Never expose an exception containing the bot credential in its URL.
        raise HTTPException(503, 'Не удалось подготовить карточку. Можно отправить ссылку или скачать изображение.') from None


@public_router.get('/share/{token}', response_class=HTMLResponse)
async def share_page(token: str, request: Request):
    index = Path(__file__).resolve().parents[2] / 'front' / 'dist' / 'index.html'
    source = index.read_text(encoding='utf-8') if index.exists() else '<html><head></head><body><div id="root"></div></body></html>'
    try: item = await service.public_share(token, str(request.base_url).rstrip('/'))
    except ValueError:
        # Keep an expired invitation human-readable: the SPA displays its fallback.
        return HTMLResponse(source, status_code=404, headers={'Cache-Control': 'no-store'})
    description = ' · '.join([item['headline'], *item['lines']])[:350]
    # Card metadata must replace the generic site's title and description.
    source = re.sub(r'<meta\b[^>]*\b(?:property|name)\s*=\s*["\'](?:og:|twitter:)[^"\']*["\'][^>]*>\s*', '', source, flags=re.IGNORECASE)
    tags = ''.join(f'<meta property="{key}" content="{html.escape(str(value), quote=True)}">' for key, value in {
        'og:title': item['title'], 'og:description': description, 'og:image': item['image_url'],
        'og:image:type': 'image/jpeg', 'og:image:width': '1200', 'og:image:height': '630',
        'og:url': item['web_url'], 'og:type': 'website'}.items())
    return HTMLResponse(source.replace('</head>', tags + '</head>'), headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
