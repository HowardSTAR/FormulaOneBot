"""Async-friendly SMTP integration with a deterministic test double."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Protocol

import aiohttp

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class VerificationMailer(Protocol):
    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None: ...

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None: ...


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    use_ssl: bool = False
    start_tls: bool = True
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        host = os.getenv("SMTP_HOST", "").strip()
        from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
        if not host or not from_email:
            raise EmailDeliveryError("SMTP_HOST and SMTP_FROM_EMAIL must be configured")
        use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
        default_port = 465 if use_ssl else 587
        username = os.getenv("SMTP_USERNAME") or None
        password = os.getenv("SMTP_PASSWORD") or None
        if bool(username) != bool(password):
            raise EmailDeliveryError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        return cls(
            host=host,
            port=int(os.getenv("SMTP_PORT", str(default_port))),
            username=username,
            password=password,
            from_email=from_email,
            use_ssl=use_ssl,
            start_tls=os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"},
            timeout_seconds=float(os.getenv("SMTP_TIMEOUT_SECONDS", "15")),
        )


class SMTPMailer:
    def __init__(self, config: SMTPConfig):
        self.config = config

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        message = EmailMessage()
        message["Subject"] = "FormulaOne Hub: подтверждение email"
        message["From"] = self.config.from_email
        message["To"] = email
        message.set_content(
            "Код подтверждения FormulaOne Hub: "
            f"{code}\n\nКод действует {expires_minutes} минут. "
            "Если вы не запрашивали код, проигнорируйте это письмо."
        )
        await asyncio.to_thread(self._send, email, message)

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None:
        message = EmailMessage()
        message["Subject"] = "FormulaOne Hub: восстановление пароля"
        message["From"] = self.config.from_email
        message["To"] = email
        message.set_content(
            "Вы запросили смену пароля FormulaOne Hub.\n\n"
            f"Откройте ссылку: {reset_url}\n\n"
            f"Ссылка действует {expires_minutes} минут и может быть использована один раз. "
            "Если вы не запрашивали восстановление, проигнорируйте это письмо."
        )
        await asyncio.to_thread(self._send, email, message)

    def _send(self, email: str, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        # Yandex Cloud Postbox supports TLS 1.2/1.3; never negotiate an older protocol.
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            if self.config.use_ssl:
                with smtplib.SMTP_SSL(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout_seconds,
                    context=context,
                ) as client:
                    self._authenticate_and_send(client, message)
            else:
                with smtplib.SMTP(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout_seconds,
                ) as client:
                    client.ehlo()
                    if self.config.start_tls:
                        client.starttls(context=context)
                        client.ehlo()
                    self._authenticate_and_send(client, message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.exception("SMTP delivery failed for %s", email)
            raise EmailDeliveryError("Почтовый сервер недоступен. Попробуйте ещё раз позже") from exc

    def _authenticate_and_send(self, client: smtplib.SMTP, message: EmailMessage) -> None:
        if self.config.username:
            if self.config.password is None:
                raise EmailDeliveryError("SMTP_PASSWORD is required when SMTP_USERNAME is set")
            client.login(self.config.username, self.config.password)
        client.send_message(message)


@dataclass(frozen=True)
class YandexPostboxAPIConfig:
    access_key_id: str
    secret_access_key: str
    from_email: str
    endpoint: str = "https://postbox.cloud.yandex.net/v2/email/outbound-emails"
    region: str = "ru-central1"
    service: str = "ses"
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "YandexPostboxAPIConfig":
        access_key_id = os.getenv("YANDEX_POSTBOX_ACCESS_KEY_ID", "").strip()
        secret_access_key = os.getenv("YANDEX_POSTBOX_SECRET_ACCESS_KEY", "").strip()
        from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
        if not access_key_id or not secret_access_key or not from_email:
            raise EmailDeliveryError(
                "Для HTTPS-отправки задайте YANDEX_POSTBOX_ACCESS_KEY_ID, "
                "YANDEX_POSTBOX_SECRET_ACCESS_KEY и SMTP_FROM_EMAIL"
            )
        return cls(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            from_email=from_email,
            timeout_seconds=float(os.getenv("SMTP_TIMEOUT_SECONDS", "15")),
        )


class YandexPostboxAPIMailer:
    """Yandex Postbox HTTPS transport for networks that block SMTP ports."""

    def __init__(self, config: YandexPostboxAPIConfig):
        self.config = config

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        await self._send_simple(
            email,
            "FormulaOne Hub: подтверждение email",
            "Код подтверждения FormulaOne Hub: "
            f"{code}\n\nКод действует {expires_minutes} минут. "
            "Если вы не запрашивали код, проигнорируйте это письмо.",
        )

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None:
        await self._send_simple(
            email,
            "FormulaOne Hub: восстановление пароля",
            "Вы запросили смену пароля FormulaOne Hub.\n\n"
            f"Откройте ссылку: {reset_url}\n\n"
            f"Ссылка действует {expires_minutes} минут и может быть использована один раз. "
            "Если вы не запрашивали восстановление, проигнорируйте это письмо.",
        )

    @staticmethod
    def _sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()

    def _headers(self, payload: bytes, now: datetime) -> dict[str, str]:
        host = "postbox.cloud.yandex.net"
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest()
        canonical_headers = (
            "content-type:application/json\n"
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            "POST\n/v2/email/outbound-emails\n\n"
            f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        scope = f"{date_stamp}/{self.config.region}/{self.config.service}/aws4_request"
        string_to_sign = (
            "AWS4-HMAC-SHA256\n"
            f"{amz_date}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        date_key = self._sign(("AWS4" + self.config.secret_access_key).encode("utf-8"), date_stamp)
        region_key = self._sign(date_key, self.config.region)
        service_key = self._sign(region_key, self.config.service)
        signing_key = self._sign(service_key, "aws4_request")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "Host": host,
            "X-Amz-Content-Sha256": payload_hash,
            "X-Amz-Date": amz_date,
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self.config.access_key_id}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }

    async def _send_simple(self, email: str, subject: str, body: str) -> None:
        payload = json.dumps(
            {
                "FromEmailAddress": self.config.from_email,
                "Destination": {"ToAddresses": [email]},
                "Content": {
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                    }
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = self._headers(payload, datetime.now(timezone.utc))
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.config.endpoint, data=payload, headers=headers) as response:
                    if response.status == 200:
                        return
                    try:
                        error = await response.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError):
                        error = {}
                    code = str(error.get("Code") or error.get("code") or "postbox_error")
                    logger.error("Yandex Postbox API rejected email to %s: HTTP %s %s", email, response.status, code)
                    raise EmailDeliveryError(f"Yandex Postbox отклонил письмо ({code})")
        except EmailDeliveryError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.exception("Yandex Postbox API delivery failed for %s", email)
            raise EmailDeliveryError("Yandex Postbox API недоступен") from exc


class MockMailer:
    """In-memory mailer for tests and explicit local mock mode."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str | int]] = []

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        self.messages.append({"email": email, "code": code, "expires_minutes": expires_minutes})

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None:
        self.messages.append(
            {"email": email, "reset_url": reset_url, "expires_minutes": expires_minutes}
        )


class ConsoleMailer:
    """Development-only delivery mode; never enabled implicitly."""

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        logger.warning("DEV EMAIL for %s: code=%s expires=%sm", email, code, expires_minutes)

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None:
        logger.warning("DEV PASSWORD RESET for %s: url=%s expires=%sm", email, reset_url, expires_minutes)


class EnvironmentMailer:
    """Resolve SMTP/mock configuration only when an email actually has to be sent.

    This keeps login and existing-session validation operational when SMTP is
    temporarily unavailable or has not been configured yet.
    """

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        await build_mailer().send_verification_code(email, code, expires_minutes)

    async def send_password_reset(self, email: str, reset_url: str, expires_minutes: int) -> None:
        await build_mailer().send_password_reset(email, reset_url, expires_minutes)


def build_mailer() -> VerificationMailer:
    mode = os.getenv("EMAIL_DELIVERY_MODE", "smtp").strip().lower()
    if mode == "mock":
        return MockMailer()
    if mode == "console":
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise EmailDeliveryError("Console email mode is forbidden in production")
        return ConsoleMailer()
    if mode in {"yandex_postbox_api", "postbox_api"}:
        return YandexPostboxAPIMailer(YandexPostboxAPIConfig.from_env())
    if mode != "smtp":
        raise EmailDeliveryError(f"Unsupported EMAIL_DELIVERY_MODE: {mode}")
    return SMTPMailer(SMTPConfig.from_env())
