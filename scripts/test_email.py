"""Send one verification-style email using the current .env SMTP settings."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.emailer import build_mailer  # noqa: E402


async def main(recipient: str) -> None:
    await build_mailer().send_verification_code(recipient, "123456", 10)
    print(f"SMTP accepted the test message for {recipient}. Check Inbox/Spam and Resend Logs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("recipient", help="For onboarding@resend.dev use your Resend account email")
    args = parser.parse_args()
    asyncio.run(main(args.recipient))
