from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_api import require_hybrid_user_id
from app.api.engagement_api import optional_account
from app.services import user_profiles as profiles
from app.services import profile_avatar
from app.services import trophies
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix='/api/profiles', tags=['profiles'])


class StyleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    frame: str
    color: str
    background: str


class AvatarRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    helmet: str
    suit: str
    background: str


class TrophyReceipts(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(max_length=60)


class TrophyBadge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None


@router.get('/me/trophies')
async def my_trophies(response: Response, user_id: int = Depends(require_hybrid_user_id)):
    response.headers['Cache-Control'] = 'no-store'
    return await trophies.collection(user_id, owner=True)


@router.post('/me/trophies/seen')
async def seen_trophies(data: TrophyReceipts, user_id: int = Depends(require_hybrid_user_id)):
    await trophies.acknowledge(user_id, data.ids)
    return {'saved': True}


@router.patch('/me/trophy-badge')
async def trophy_badge(data: TrophyBadge, user_id: int = Depends(require_hybrid_user_id)):
    try:
        await trophies.select_badge(user_id, data.id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {'saved': True}


@router.get('/{profile_id}/trophies')
async def public_trophies(profile_id: int, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    # Resolve the subject without evaluating private progress for a visitor.
    if profile_id not in await profiles.identities():
        raise HTTPException(404, 'Профиль не найден')
    return await trophies.collection(profile_id)


@router.get('/avatar/v1.png')
async def avatar_image(helmet: str = Query('scarlet', max_length=24),
                       suit: str = Query('scarlet', max_length=24),
                       background: str = Query('garage', max_length=24)):
    try:
        profile_avatar.validate(dict(helmet=helmet, suit=suit, background=background))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    content = await run_in_threadpool(profile_avatar.render, helmet, suit, background)
    return Response(content, media_type='image/png', headers={'Cache-Control': 'public, max-age=31536000, immutable'})


@router.patch('/me/avatar')
async def avatar(data: AvatarRequest, user_id: int = Depends(require_hybrid_user_id)):
    try:
        await profiles.save_avatar(user_id, data.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'saved': True}


@router.get('/me')
async def mine(response: Response, season: int | None = Query(None, ge=1950, le=2100),
               user_id: int = Depends(require_hybrid_user_id)):
    response.headers['Cache-Control'] = 'no-store'
    return await profiles.profile(user_id, user_id, season)


@router.patch('/me/style')
async def style(data: StyleRequest, user_id: int = Depends(require_hybrid_user_id)):
    try:
        await profiles.save_style(user_id, data.model_dump())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'saved': True}


@router.get('/supporters')
async def supporters(response: Response, season: int | None = Query(None, ge=1950, le=2100),
                     user_id: int = Depends(require_hybrid_user_id)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await profiles.supporter_league(user_id, season)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get('/{profile_id}')
async def public_profile(profile_id: int, response: Response,
                         season: int | None = Query(None, ge=1950, le=2100),
                         user_id: int | None = Depends(optional_account)):
    response.headers['Cache-Control'] = 'no-store'
    value = await profiles.profile(profile_id, user_id if user_id is not None else -1, season)
    if value is None:
        raise HTTPException(404, 'Профиль не найден')
    return value
