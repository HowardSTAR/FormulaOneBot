"""HTTP integration test for the FastAPI authentication surface."""

from __future__ import annotations

import httpx
import pytest

from app.api import auth_api
from app.api.miniapp_api import web_app
from app.db import Database
from app.emailer import MockMailer
from app.services.account_link_service import AccountLinkService
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_email_session_csrf_and_link_endpoint(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="test-pepper-with-enough-entropy")
    links = AccountLinkService(database, pepper="test-pepper-with-enough-entropy")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(auth_api, "get_link_service", lambda: links)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "formula_test_bot")

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await client.post(
            "/api/auth/register",
            json={"email": "api@example.com", "password": "FormulaOne-2026-Secure"},
        )
        assert registered.status_code == 202
        code = str(mailer.messages[-1]["code"])

        verified = await client.post(
            "/api/auth/verify-email", json={"email": "api@example.com", "code": code}
        )
        assert verified.status_code == 200
        payload = verified.json()
        assert client.cookies.get("f1hub_session")
        assert client.cookies.get("f1hub_csrf") == payload["csrf_token"]

        rejected = await client.post("/api/auth/telegram/link-sessions")
        assert rejected.status_code == 403

        created = await client.post(
            "/api/auth/telegram/link-sessions",
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert created.status_code == 201
        assert created.json()["deep_link"].startswith("https://t.me/formula_test_bot?start=link_")
        qr = await client.get(created.json()["qr_url"])
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")

        logged_out = await client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert logged_out.status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401

    await database.close()
