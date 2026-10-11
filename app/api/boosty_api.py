"""Authenticated, CSRF-protected Boosty pilot endpoints."""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.auth_api import require_hybrid_user_id
from app.db import db
from app.services.boosty_service import BoostyService, BoostyUnavailable

router = APIRouter(prefix="/api/account/boosty", tags=["account"])


@lru_cache(maxsize=1)
def get_boosty_service():
    return BoostyService(db)


async def require_boosty_user(user_id: int = Depends(require_hybrid_user_id)):
    async with get_boosty_service().database.conn.execute(
        "SELECT * FROM users WHERE id=? AND archived_at IS NULL", (user_id,)
    ) as cursor:
        user = await cursor.fetchone()
    if user is None:
        raise HTTPException(401, detail="Войдите в аккаунт для проверки подписки")
    return dict(user)


@router.get("")
async def status(response: Response, user: dict = Depends(require_boosty_user)):
    response.headers["Cache-Control"] = "no-store"
    return await get_boosty_service().status(user)


@router.post("/check")
async def check(response: Response, user: dict = Depends(require_boosty_user)):
    service = get_boosty_service()
    if not service.eligible(user):
        raise HTTPException(403, detail="Проверка пока доступна только тестовому аккаунту")
    if not user.get("email_verified") or not user.get("email"):
        raise HTTPException(403, detail="Подтвердите email, используемый в Boosty")
    try:
        await service.sync()
    except BoostyUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return await service.status(user)
