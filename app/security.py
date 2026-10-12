"""Browser request boundaries and fail-closed production authentication config."""

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

TRUE_VALUES = {"1", "true", "yes"}
PRODUCTION_CSP = (
    "base-uri 'self'; object-src 'none'; form-action 'self'; "
    "script-src 'self' https://telegram.org; worker-src 'self' blob:; "
    "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
)


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def secure_cookies() -> bool:
    return is_production() or os.getenv("AUTH_COOKIE_SECURE", "false").lower() in TRUE_VALUES


def auth_secret(explicit: str | None = None) -> bytes:
    secret = explicit or os.getenv("AUTH_PEPPER")
    if is_production():
        if not secret or len(secret.encode("utf-8")) < 32 or secret == os.getenv("BOT_TOKEN"):
            raise RuntimeError("Production requires an independent AUTH_PEPPER of at least 32 bytes")
    secret = secret or os.getenv("BOT_TOKEN")
    if not secret:
        raise RuntimeError("AUTH_PEPPER (or local BOT_TOKEN fallback) must be configured")
    return secret.encode("utf-8")


def url_origin(value: str) -> str | None:
    try:
        if any(char.isspace() or ord(char) < 32 for char in value):
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return None
        port = parts.port
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        suffix = f":{port}" if port and port != (443 if parts.scheme == "https" else 80) else ""
        return f"{parts.scheme}://{host}{suffix}"
    except ValueError:
        return None


def validate_production_security() -> None:
    if not is_production():
        return
    auth_secret()
    if os.getenv("AUTH_COOKIE_SECURE", "true").lower() not in TRUE_VALUES:
        raise RuntimeError("AUTH_COOKIE_SECURE cannot be disabled in production")
    public_url = os.getenv("PUBLIC_WEB_URL", "")
    if not url_origin(public_url) or not public_url.startswith("https://") or urlsplit(public_url).query or urlsplit(public_url).fragment:
        raise RuntimeError("Production requires a trusted HTTPS PUBLIC_WEB_URL without query or fragment")
    origins = [value.strip() for value in os.getenv("WEB_ORIGINS", "").split(",") if value.strip()]
    if not origins or any(not origin.startswith("https://") or url_origin(origin) != origin for origin in origins):
        raise RuntimeError("Production requires explicit HTTPS WEB_ORIGINS; wildcards are forbidden")
    if os.getenv("EMAIL_DELIVERY_MODE", "smtp").strip().lower() in {"mock", "console"}:
        raise RuntimeError("Mock and console mail delivery are forbidden in production")
    if os.getenv("EMAIL_DELIVERY_MODE", "smtp").strip().lower() == "smtp":
        if os.getenv("SMTP_USE_SSL", "false").lower() not in TRUE_VALUES and os.getenv("SMTP_STARTTLS", "true").lower() not in TRUE_VALUES:
            raise RuntimeError("Production SMTP requires TLS")


def validate_request_origin(request: Request) -> None:
    """Protect public login and cookie writes; CORS alone is not CSRF protection."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    allowed = {
        url_origin(str(request.base_url)),
        url_origin(os.getenv("PUBLIC_WEB_URL", "")),
        *(url_origin(value.strip()) for value in os.getenv(
            "WEB_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",") if value.strip() != "*"),
    }
    allowed.discard(None)
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    source = origin if origin is not None else referer
    if source is not None:
        parsed = url_origin(source)
        if parsed not in allowed or (origin is not None and origin != parsed):
            raise HTTPException(403, detail={"code": "untrusted_origin", "message": "Источник запроса не разрешён"})
    elif request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        # Sibling subdomains are not automatically trusted.
        raise HTTPException(403, detail={"code": "untrusted_origin", "message": "Источник запроса не разрешён"})
    # Native API clients have no browser Origin/Fetch Metadata. Cookie writes
    # still require their session-bound CSRF token in require_web_session.


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_headers = dict(scope.get("headers", []))
        private = scope["path"].startswith(("/api/auth", "/api/admin", "/reset-password")) or any(
            name in request_headers for name in (b"cookie", b"authorization", b"x-telegram-init-data")
        )

        async def protected_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                protected = {b"x-content-type-options", b"referrer-policy", b"permissions-policy"}
                if private:
                    protected |= {b"cache-control", b"pragma"}
                headers = [(key, value) for key, value in headers if key.lower() not in protected]
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ])
                if private:
                    headers.extend([(b"cache-control", b"private, no-store"), (b"pragma", b"no-cache")])
                if is_production():
                    headers.append((b"content-security-policy", PRODUCTION_CSP.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, protected_send)
