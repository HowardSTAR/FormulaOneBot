"""Send registration/reset smoke emails using the configured production transport."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.emailer import build_mailer  # noqa: E402


async def main(recipient: str, kind: str, public_url: str) -> None:
    mailer = build_mailer()
    if kind in {"registration", "both"}:
        await mailer.send_verification_code(recipient, "123456", 10)
    if kind in {"reset", "both"}:
        await mailer.send_password_reset(
            recipient,
            f"{public_url.rstrip('/')}/reset-password?token=production-smoke-test",
            30,
        )
    mode = os.getenv("EMAIL_DELIVERY_MODE", "smtp").strip().lower()
    if mode == "mock":
        print(f"Mock mailer rendered '{kind}' message(s) for {recipient} successfully.")
    elif mode == "console":
        print(f"Console mailer rendered '{kind}' message(s) for {recipient} successfully.")
    else:
        print(
            f"Email transport '{mode}' accepted '{kind}' smoke message(s) for {recipient}. "
            "Check Inbox/Spam and the provider delivery log."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("recipient", help="Email address that should receive the Postbox test")
    parser.add_argument(
        "--kind",
        choices=("registration", "reset", "both"),
        default="both",
        help="Which application email template to send",
    )
    parser.add_argument(
        "--public-url",
        default="https://f1hub.ru",
        help="Public website origin used in the reset smoke link",
    )
    args = parser.parse_args()
    asyncio.run(main(args.recipient, args.kind, args.public_url))
