"""FastAPI routes for email authentication and Telegram account linking."""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import get_current_user_id as get_telegram_user_id
from app.db import db
from app.emailer import EmailDeliveryError, EnvironmentMailer
from app.services.account_link_service import (
    AccountLinkService,
    LinkAlreadyUsed,
    LinkConflict,
    LinkError,
    LinkExpired,
    LinkNotFound,
)
from app.services.auth_service import (
    AuthError,
    AuthService,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidInput,
    InvalidVerificationCode,
    RateLimitExceeded,
    VerificationCodeExpired,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "f1hub_session"
CSRF_COOKIE_NAME = "f1hub_csrf"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class LinkCodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    strategy: Literal["keep_web", "keep_telegram"] | None = None


@dataclass(frozen=True)
class WebSessionContext:
    user: dict
    raw_token: str
    from_cookie: bool


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(db, EnvironmentMailer())


@lru_cache(maxsize=1)
def get_link_service() -> AccountLinkService:
    return AccountLinkService(db)


def _client_ip(request: Request) -> str | None:
    # Trust proxy headers only when the deployment explicitly enables them in its proxy layer.
    return request.client.host if request.client else None


def _set_session_cookie(response: Response, token: str, csrf_token: str, max_age: int) -> None:
    secure = os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Double-submit value: JavaScript may read it, but the server accepts it
    # only when it also matches the hash bound to the HttpOnly session.
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _session_payload(session) -> dict:
    return {
        "access_token": session.token,
        "token_type": "bearer",
        "csrf_token": session.csrf_token,
        "expires_at": session.expires_at,
        "user": session.user,
    }


def _auth_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (InvalidCredentials, InvalidVerificationCode)):
        return HTTPException(401, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailNotVerified):
        return HTTPException(403, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailAlreadyRegistered):
        return HTTPException(409, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, (VerificationCodeExpired, RateLimitExceeded)):
        status = 429 if isinstance(exc, RateLimitExceeded) else 410
        return HTTPException(status, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, InvalidInput):
        return HTTPException(422, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailDeliveryError):
        return HTTPException(503, detail={"code": "email_delivery_failed", "message": str(exc)})
    return HTTPException(400, detail={"code": "auth_error", "message": str(exc)})


def _link_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LinkConflict):
        return HTTPException(409, detail={"code": exc.code, "message": str(exc), "strategies": ["keep_web", "keep_telegram"]})
    if isinstance(exc, LinkExpired):
        return HTTPException(410, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, (LinkNotFound, LinkAlreadyUsed)):
        return HTTPException(404, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(400, detail={"code": getattr(exc, "code", "link_error"), "message": str(exc)})


async def require_web_session(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> WebSessionContext:
    bearer_token = None
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            bearer_token = credentials.strip()
    raw_token = bearer_token or cookie_token
    if not raw_token:
        raise HTTPException(401, detail={"code": "missing_session", "message": "Authentication required"})
    try:
        user = await get_auth_service().authenticate_session(raw_token)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    from_cookie = bearer_token is None
    if from_cookie and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        if not get_auth_service().verify_csrf(x_csrf_token, user["csrf_hash"]):
            raise HTTPException(403, detail={"code": "invalid_csrf", "message": "CSRF token is missing or invalid"})
    return WebSessionContext(user=user, raw_token=raw_token, from_cookie=from_cookie)


async def require_hybrid_telegram_id(
    request: Request,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> int:
    """Accept Telegram initData or a linked website session.

    Existing database helpers use Telegram IDs as their public identity key, so
    a website account must have completed linking before personalized Mini App
    data can be accessed.
    """
    if x_telegram_init_data:
        return await get_telegram_user_id(x_telegram_init_data)
    session = await require_web_session(
        request=request,
        authorization=authorization,
        x_csrf_token=x_csrf_token,
        cookie_token=cookie_token,
    )
    telegram_id = session.user.get("telegram_id")
    if telegram_id is None:
        raise HTTPException(
            403,
            detail={
                "code": "telegram_link_required",
                "message": "Link Telegram to use personalized features",
            },
        )
    return int(telegram_id)


async def get_optional_hybrid_telegram_id(
    request: Request,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> int | None:
    if x_telegram_init_data:
        try:
            return await get_telegram_user_id(x_telegram_init_data)
        except HTTPException:
            return None
    if not authorization and not cookie_token:
        return None
    try:
        session = await require_web_session(
            request=request,
            authorization=authorization,
            x_csrf_token=None,
            cookie_token=cookie_token,
        )
    except HTTPException:
        return None
    telegram_id = session.user.get("telegram_id")
    return int(telegram_id) if telegram_id is not None else None


@router.post("/register", status_code=202)
async def register(data: RegisterRequest):
    try:
        return await get_auth_service().register(data.email, data.password)
    except (AuthError, EmailDeliveryError) as exc:
        raise _auth_http_error(exc) from exc


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest, request: Request, response: Response):
    try:
        session = await get_auth_service().verify_email(
            data.email,
            data.code,
            request.headers.get("user-agent"),
            _client_ip(request),
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    _set_session_cookie(
        response, session.token, session.csrf_token,
        int(get_auth_service().session_ttl.total_seconds()),
    )
    return _session_payload(session)


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response):
    try:
        session = await get_auth_service().login(
            data.email,
            data.password,
            request.headers.get("user-agent"),
            _client_ip(request),
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    _set_session_cookie(
        response, session.token, session.csrf_token,
        int(get_auth_service().session_ttl.total_seconds()),
    )
    return _session_payload(session)


@router.post("/logout", status_code=204)
async def logout(response: Response, session: WebSessionContext = Depends(require_web_session)):
    await get_auth_service().logout(session.raw_token)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/me")
async def me(session: WebSessionContext = Depends(require_web_session)):
    return {key: value for key, value in session.user.items() if not key.endswith("_hash")}


def _bot_deep_link(token: str) -> str:
    username = (os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "").lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise HTTPException(
            503,
            detail={"code": "bot_username_missing", "message": "TELEGRAM_BOT_USERNAME is not configured"},
        )
    return f"https://t.me/{username}?start=link_{token}"


@router.post("/telegram/link-sessions", status_code=201)
async def create_telegram_link(session: WebSessionContext = Depends(require_web_session)):
    try:
        result = await get_link_service().create_web_link_session(int(session.user["id"]))
    except LinkError as exc:
        raise _link_http_error(exc) from exc
    deep_link = _bot_deep_link(result["token"])
    return {
        **result,
        "deep_link": deep_link,
        "qr_url": f"/api/auth/telegram/link-sessions/{result['token']}/qr.svg",
        "manual_flow": "Send /link to the bot, then enter the bot-generated code on the website.",
    }


@router.get("/telegram/link-sessions/{token}/status")
async def telegram_link_status(token: str, session: WebSessionContext = Depends(require_web_session)):
    try:
        return await get_link_service().get_link_status(token, int(session.user["id"]))
    except LinkError as exc:
        raise _link_http_error(exc) from exc


@router.get("/telegram/link-sessions/{token}/qr.svg")
async def telegram_link_qr(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{48,59}", token):
        raise HTTPException(404, detail={"code": "link_not_found", "message": "Link session not found"})
    try:
        await get_link_service().validate_public_token(token)
    except LinkError as exc:
        raise _link_http_error(exc) from exc
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError as exc:
        raise HTTPException(503, detail={"code": "qr_dependency_missing", "message": "Install qrcode package"}) from exc
    deep_link = _bot_deep_link(token)
    image = qrcode.make(deep_link, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    output = io.BytesIO()
    image.save(output)
    return Response(output.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.post("/telegram/link-by-code")
async def telegram_link_by_code(
    data: LinkCodeRequest,
    session: WebSessionContext = Depends(require_web_session),
):
    try:
        return await get_link_service().link_with_bot_code(
            int(session.user["id"]), data.code, data.strategy
        )
    except LinkError as exc:
        raise _link_http_error(exc) from exc
