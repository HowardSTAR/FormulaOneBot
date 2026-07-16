"""Async-friendly SMTP integration with a deterministic test double."""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class VerificationMailer(Protocol):
    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None: ...


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
        return cls(
            host=host,
            port=int(os.getenv("SMTP_PORT", str(default_port))),
            username=os.getenv("SMTP_USERNAME") or None,
            password=os.getenv("SMTP_PASSWORD") or None,
            from_email=from_email,
            use_ssl=use_ssl,
            start_tls=os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"},
            timeout_seconds=float(os.getenv("SMTP_TIMEOUT_SECONDS", "15")),
        )


class SMTPMailer:
    def __init__(self, config: SMTPConfig):
        self.config = config

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        await asyncio.to_thread(self._send, email, code, expires_minutes)

    def _send(self, email: str, code: str, expires_minutes: int) -> None:
        message = EmailMessage()
        message["Subject"] = "FormulaOne Hub: email verification"
        message["From"] = self.config.from_email
        message["To"] = email
        message.set_content(
            "Your FormulaOne Hub verification code is: "
            f"{code}\n\nThe code expires in {expires_minutes} minutes. "
            "If you did not request it, ignore this message."
        )

        context = ssl.create_default_context()
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
            raise EmailDeliveryError("Verification email could not be delivered") from exc

    def _authenticate_and_send(self, client: smtplib.SMTP, message: EmailMessage) -> None:
        if self.config.username:
            if self.config.password is None:
                raise EmailDeliveryError("SMTP_PASSWORD is required when SMTP_USERNAME is set")
            client.login(self.config.username, self.config.password)
        client.send_message(message)


class MockMailer:
    """In-memory mailer for tests and explicit local mock mode."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str | int]] = []

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        self.messages.append({"email": email, "code": code, "expires_minutes": expires_minutes})


class ConsoleMailer:
    """Development-only delivery mode; never enabled implicitly."""

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        logger.warning("DEV EMAIL for %s: code=%s expires=%sm", email, code, expires_minutes)


class EnvironmentMailer:
    """Resolve SMTP/mock configuration only when an email actually has to be sent.

    This keeps login and existing-session validation operational when SMTP is
    temporarily unavailable or has not been configured yet.
    """

    async def send_verification_code(self, email: str, code: str, expires_minutes: int) -> None:
        await build_mailer().send_verification_code(email, code, expires_minutes)


def build_mailer() -> VerificationMailer:
    mode = os.getenv("EMAIL_DELIVERY_MODE", "smtp").strip().lower()
    if mode == "mock":
        return MockMailer()
    if mode == "console":
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise EmailDeliveryError("Console email mode is forbidden in production")
        return ConsoleMailer()
    if mode != "smtp":
        raise EmailDeliveryError(f"Unsupported EMAIL_DELIVERY_MODE: {mode}")
    return SMTPMailer(SMTPConfig.from_env())
