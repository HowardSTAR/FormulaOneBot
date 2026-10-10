from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from app.api.auth_api import require_hybrid_user_id
from app.api.engagement_api import optional_account
from app.services import user_profiles as profiles

router = APIRouter(prefix='/api/profiles', tags=['profiles'])


class StyleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    frame: str
    color: str
    background: str


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
