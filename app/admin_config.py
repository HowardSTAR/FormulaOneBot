"""Environment-backed identity of the protected primary administrator."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_primary_admin_email() -> str | None:
    value = os.getenv("ADMIN_EMAIL", "").strip().lower()
    return value or None


def get_primary_admin_telegram_id() -> int | None:
    # ADMIN_IDA is accepted as a compatibility alias for existing deployments.
    raw_value = (
        os.getenv("ADMIN_TELEGRAM_ID", "").strip()
        or os.getenv("ADMIN_IDA", "").strip()
    )
    if not raw_value:
        return None
    try:
        telegram_id = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("ADMIN_TELEGRAM_ID must be an integer") from exc
    if telegram_id <= 0:
        raise RuntimeError("ADMIN_TELEGRAM_ID must be positive")
    return telegram_id
