"""Authenticated, CSRF-protected Boosty pilot endpoints."""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.auth_api import WebSessionContext, require_web_session
from app.db import db
from app.services.boosty_service import BoostyService, BoostyUnavailable

router = APIRouter(prefix="/api/account/boosty", tags=["account"])


@lru_cache(maxsize=1)
def get_boosty_service():
    return BoostyService(db)


@router.get("")
async def status(response: Response, session: WebSessionContext = Depends(require_web_session)):
    response.headers["Cache-Control"] = "no-store"
    return await get_boosty_service().status(session.user)


@router.post("/check")
async def check(response: Response, session: WebSessionContext = Depends(require_web_session)):
    service = get_boosty_service()
    if not service.eligible(session.user):
        raise HTTPException(403, detail="Проверка пока доступна только тестовому аккаунту")
    if not session.user.get("email_verified") or not session.user.get("email"):
        raise HTTPException(403, detail="Подтвердите email, используемый в Boosty")
    try:
        await service.sync()
    except BoostyUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return await service.status(session.user)
