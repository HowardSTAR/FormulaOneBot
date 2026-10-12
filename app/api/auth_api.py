"""FastAPI routes for email authentication and Telegram account linking."""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import get_current_user_id as get_telegram_user_id
from app.db import db, get_or_create_user
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
    InvalidResetToken,
    InvalidVerificationCode,
    PasswordResetExpired,
    RateLimitExceeded,
    VerificationCodeExpired,
    VerificationResendCooldown,
)
from app.services.activity_service import record_user_activity
from app.services.auth_service import normalize_email
from app.security import secure_cookies, validate_request_origin

logger = logging.getLogger(__name__)


async def auth_request_guard(request: Request):
    validate_request_origin(request)
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    ip_address = _client_ip(request)
    if not ip_address:
        return
    limits = {
        "/api/auth/register": (10, timedelta(hours=1)),
        "/api/auth/password/forgot": (10, timedelta(hours=1)),
        "/api/auth/password/reset": (10, timedelta(minutes=15)),
        "/api/auth/verify-email": (20, timedelta(minutes=15)),
    }
    limit, window = limits.get(request.url.path, (30, timedelta(minutes=15)))
    try:
        await get_auth_service().reserve_attempt("auth-ip:" + request.url.path, ip_address, limit, window)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc


router = APIRouter(prefix="/api/auth", tags=["authentication"], dependencies=[Depends(auth_request_guard)])
COOKIE_NAME = "turbotears_session"
CSRF_COOKIE_NAME = "turbotears_csrf"


class RegistrationAvatar(BaseModel):
    helmet: str = Field(max_length=24)
    suit: str = Field(max_length=24)
    background: str = Field(max_length=24)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=15, max_length=128)
    display_name: str = Field(min_length=2, max_length=32)
    avatar: RegistrationAvatar | None = None
    favorite_drivers: list[str] = Field(default_factory=list, max_length=30)
    favorite_teams: list[str] = Field(default_factory=list, max_length=20)


class VerifyEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=40, max_length=512)
    new_password: str = Field(min_length=15, max_length=128)
    password_confirmation: str = Field(min_length=15, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)
    password_confirmation: str = Field(min_length=15, max_length=128)


class DeleteAccountRequest(BaseModel):
    confirmation: Literal["DELETE"]
    current_password: str | None = Field(default=None, min_length=1, max_length=128)


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
    secure = secure_cookies()
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
    if isinstance(exc, VerificationResendCooldown):
        return HTTPException(429, detail={"code": exc.code, "message": str(exc), "retry_after": exc.retry_after},
                             headers={"Retry-After": str(exc.retry_after)})
    if isinstance(exc, (InvalidCredentials, InvalidVerificationCode)):
        return HTTPException(401, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailNotVerified):
        return HTTPException(403, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailAlreadyRegistered):
        return HTTPException(409, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, RateLimitExceeded):
        detail = {"code": exc.code, "message": str(exc), "scope": exc.scope}
        headers = {}
        if exc.retry_after:
            detail["retry_after"] = exc.retry_after
            headers["Retry-After"] = str(exc.retry_after)
        return HTTPException(429, detail=detail, headers=headers)
    if isinstance(exc, VerificationCodeExpired):
        return HTTPException(410, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, PasswordResetExpired):
        return HTTPException(410, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, InvalidResetToken):
        return HTTPException(400, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, InvalidInput):
        return HTTPException(422, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, EmailDeliveryError):
        return HTTPException(503, detail={"code": "email_delivery_failed", "message": "Не удалось отправить письмо. Попробуйте позже"})
    return HTTPException(400, detail={"code": "auth_error", "message": "Не удалось выполнить запрос"})


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
    auth_service = get_auth_service()
    try:
        user = await auth_service.authenticate_session(raw_token)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    await record_user_activity(auth_service.database, int(user["id"]), "site")
    from_cookie = bearer_token is None
    if from_cookie and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        validate_request_origin(request)
        if not auth_service.verify_csrf(x_csrf_token, user["csrf_hash"]):
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


async def require_hybrid_user_id(
    request: Request,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
    cookie_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> int:
    """Return the canonical users.id for Telegram or website authentication."""
    if x_telegram_init_data:
        telegram_id = await get_telegram_user_id(x_telegram_init_data)
        return await get_or_create_user(telegram_id)
    session = await require_web_session(
        request=request,
        authorization=authorization,
        x_csrf_token=x_csrf_token,
        cookie_token=cookie_token,
    )
    return int(session.user["id"])


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
async def register(data: RegisterRequest, request: Request, response: Response):
    try:
        result = await get_auth_service().register(
            data.email, data.password, display_name=data.display_name,
            avatar=data.avatar.model_dump() if data.avatar else None,
            favorite_drivers=data.favorite_drivers, favorite_teams=data.favorite_teams,
            user_agent=request.headers.get("user-agent"), ip_address=_client_ip(request),
        )
    except (AuthError, EmailDeliveryError) as exc:
        raise _auth_http_error(exc) from exc
    _set_session_cookie(response, result["access_token"], result["csrf_token"],
                        int(get_auth_service().session_ttl.total_seconds()))
    return result


@router.post("/resend-verification", status_code=202)
async def resend_verification(session: WebSessionContext = Depends(require_web_session)):
    try:
        return await get_auth_service().resend_verification(int(session.user["id"]))
    except (AuthError, EmailDeliveryError) as exc:
        raise _auth_http_error(exc) from exc


@router.get("/verification-status")
async def verification_status(response: Response, session: WebSessionContext = Depends(require_web_session)):
    response.headers["Cache-Control"] = "no-store"
    return await get_auth_service().verification_status(int(session.user["id"]))


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


def _public_web_url(request: Request) -> str:
    configured = (
        os.getenv("PUBLIC_WEB_URL")
        or os.getenv("FRONTEND_URL")
        or os.getenv("MINI_APP_URL")
        or ""
    ).strip()
    if configured:
        return configured.rstrip("/")
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise HTTPException(
            503,
            detail={"code": "public_web_url_missing", "message": "PUBLIC_WEB_URL is not configured"},
        )
    return str(request.base_url).rstrip("/")


@router.post("/password/forgot", status_code=202)
async def forgot_password(data: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks):
    # Response is sent before account lookup/delivery, including SMTP failures.
    # Reserve the same persistent limit for known and unknown email addresses.
    try:
        email = normalize_email(data.email)
        public_url = _public_web_url(request)
        service = get_auth_service()
        await service.reserve_attempt("password-reset-request", email, 4, timedelta(hours=1))
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    background_tasks.add_task(_deliver_password_reset, service, email, public_url)
    return {
        "message": "Если аккаунт с таким email существует, ссылка для восстановления уже отправлена."
    }


async def _deliver_password_reset(service: AuthService, email: str, public_url: str):
    try:
        await service.request_password_reset(email, public_url, reserve_limit=False)
    except Exception as exc:
        # No email, reset URL, SMTP config or token in logs/responses.
        logger.warning("Password reset delivery failed (%s)", type(exc).__name__)


@router.post("/password/reset")
async def reset_password(data: ResetPasswordRequest):
    if data.new_password != data.password_confirmation:
        raise _auth_http_error(InvalidInput("Пароли не совпадают"))
    try:
        await get_auth_service().reset_password(data.token, data.new_password)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    return {"message": "Пароль изменён. Теперь можно войти с новым паролем."}


@router.post("/password/change")
async def change_password(
    data: ChangePasswordRequest,
    session: WebSessionContext = Depends(require_web_session),
):
    if data.new_password != data.password_confirmation:
        raise _auth_http_error(InvalidInput("Пароли не совпадают"))
    try:
        await get_auth_service().change_password(
            int(session.user["id"]),
            data.current_password,
            data.new_password,
            session.user["session_token_hash"],
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    return {"message": "Пароль успешно изменён."}


@router.post("/logout", status_code=204)
async def logout(response: Response, session: WebSessionContext = Depends(require_web_session)):
    await get_auth_service().logout(session.raw_token)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.delete("/account", status_code=204)
async def delete_account(
    data: DeleteAccountRequest,
    response: Response,
    session: WebSessionContext = Depends(require_web_session),
):
    try:
        await get_auth_service().delete_account(
            int(session.user["id"]),
            data.current_password,
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
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
