"""Authorization, protected-account and analytics tests for the admin API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api import admin_api, auth_api
from app.api.miniapp_api import web_app
from app.admin_config import get_primary_admin_email, get_primary_admin_telegram_id
from app.db import Database
from app.emailer import MockMailer
from app.services.activity_service import is_primary_admin
from app.services.auth_service import AuthService


async def create_verified_session(auth: AuthService, mailer: MockMailer, email: str):
    await auth.register(email, "FormulaOne-2026-Secure")
    return await auth.verify_email(email, str(mailer.messages[-1]["code"]))


def configured_primary_admin() -> tuple[str, int]:
    email = get_primary_admin_email()
    telegram_id = get_primary_admin_telegram_id()
    assert email, "ADMIN_EMAIL must be configured in .env for admin tests"
    assert telegram_id, "ADMIN_TELEGRAM_ID must be configured in .env for admin tests"
    return email, telegram_id


def test_primary_admin_identity_is_loaded_from_environment(monkeypatch):
    configured_email, configured_telegram_id = configured_primary_admin()
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_TELEGRAM_ID", raising=False)
    monkeypatch.delenv("ADMIN_IDA", raising=False)
    assert get_primary_admin_email() is None
    assert get_primary_admin_telegram_id() is None
    assert not is_primary_admin(configured_email, configured_telegram_id)

    monkeypatch.setenv("ADMIN_EMAIL", configured_email.upper())
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", str(configured_telegram_id))
    assert get_primary_admin_email() == configured_email
    assert get_primary_admin_telegram_id() == configured_telegram_id
    assert is_primary_admin(configured_email.upper(), None)
    assert is_primary_admin(None, configured_telegram_id)


@pytest.mark.asyncio
async def test_admin_endpoints_require_role_and_protect_primary_superadmin(temp_db_path, monkeypatch):
    primary_email, _ = configured_primary_admin()
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="admin-test-pepper")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "db", database)
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://f1hub.example")

    primary = await create_verified_session(auth, mailer, primary_email.upper())
    regular = await create_verified_session(auth, mailer, "fan@example.com")
    assert primary.user["role"] == "superadmin"
    assert regular.user["role"] == "user"

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/admin/me")).status_code == 401

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as regular_client:
        regular_client.cookies.set("f1hub_session", regular.token)
        regular_client.cookies.set("f1hub_csrf", regular.csrf_token)
        assert (await regular_client.get("/api/admin/me")).status_code == 403

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.cookies.set("f1hub_session", primary.token)
        admin_client.cookies.set("f1hub_csrf", primary.csrf_token)
        me = await admin_client.get("/api/admin/me")
        assert me.status_code == 200
        assert me.json()["role"] == "superadmin"

        missing_csrf = await admin_client.patch(
            f"/api/admin/users/{regular.user['id']}/role",
            json={"role": "admin"},
        )
        assert missing_csrf.status_code == 403

        promoted = await admin_client.patch(
            f"/api/admin/users/{regular.user['id']}/role",
            headers={"X-CSRF-Token": primary.csrf_token},
            json={"role": "admin"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

        protected = await admin_client.patch(
            f"/api/admin/users/{primary.user['id']}/role",
            headers={"X-CSRF-Token": primary.csrf_token},
            json={"role": "user"},
        )
        assert protected.status_code == 403

        audit = await admin_client.get("/api/admin/audit-log")
        assert audit.status_code == 200
        assert audit.json()["items"][0]["action"] == "user.role_changed"

    await database.close()


@pytest.mark.asyncio
async def test_admin_metrics_split_site_bot_and_total(temp_db_path, monkeypatch):
    primary_email, _ = configured_primary_admin()
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="admin-test-pepper")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "db", database)

    primary = await create_verified_session(auth, mailer, primary_email)
    second = await create_verified_session(auth, mailer, "metrics@example.com")
    now = datetime.now(timezone.utc)
    await database.conn.executemany(
        "INSERT INTO user_activity_events(user_id, source, occurred_at) VALUES (?, ?, ?)",
        [
            (primary.user["id"], "site", now.isoformat()),
            (primary.user["id"], "bot", now.isoformat()),
            (second.user["id"], "bot", (now - timedelta(hours=2)).isoformat()),
        ],
    )
    await database.conn.commit()

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("f1hub_session", primary.token)
        client.cookies.set("f1hub_csrf", primary.csrf_token)
        response = await client.get("/api/admin/metrics", params={"period": "7d", "source": "all"})
        assert response.status_code == 200
        cards = response.json()["cards"]
        assert cards["site"]["dau"] == 1
        assert cards["bot"]["dau"] == 2
        assert cards["all"]["dau"] == 2
        assert response.json()["series"]

    await database.close()


@pytest.mark.asyncio
async def test_admin_users_supports_server_side_sorting(temp_db_path, monkeypatch):
    """Пагинация пользователей сортируется на сервере по разрешённым колонкам."""
    primary_email, _ = configured_primary_admin()
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="admin-sort-test-pepper")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "db", database)

    primary = await create_verified_session(auth, mailer, primary_email)
    regular = await create_verified_session(auth, mailer, "regular-sort@example.com")
    delegated = await create_verified_session(auth, mailer, "delegated-sort@example.com")
    await database.conn.executemany(
        "UPDATE users SET created_at = ?, role = ? WHERE id = ?",
        [
            ("2024-01-01T10:00:00+00:00", "superadmin", primary.user["id"]),
            ("2024-01-02T10:00:00+00:00", "user", regular.user["id"]),
            ("2024-01-03T10:00:00+00:00", "admin", delegated.user["id"]),
        ],
    )
    await database.conn.executemany(
        "INSERT INTO user_activity_events(user_id, source, occurred_at) VALUES (?, 'site', ?)",
        [
            (primary.user["id"], "2024-03-01T10:00:00+00:00"),
            (delegated.user["id"], "2024-02-01T10:00:00+00:00"),
        ],
    )
    await database.conn.commit()

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("f1hub_session", primary.token)
        client.cookies.set("f1hub_csrf", primary.csrf_token)

        created = await client.get(
            "/api/admin/users",
            params={"sortBy": "created_at", "sortOrder": "asc", "page_size": 10},
        )
        assert created.status_code == 200
        assert [user["email"] for user in created.json()["items"]] == [
            primary_email,
            "regular-sort@example.com",
            "delegated-sort@example.com",
        ]
        assert created.json()["sort_by"] == "created_at"
        assert created.json()["sort_order"] == "asc"

        active = await client.get(
            "/api/admin/users",
            params={"sortBy": "last_activity", "sortOrder": "desc", "page_size": 10},
        )
        assert active.status_code == 200
        assert [user["email"] for user in active.json()["items"]] == [
            primary_email,
            "delegated-sort@example.com",
            "regular-sort@example.com",
        ]

        roles = await client.get(
            "/api/admin/users",
            params={"sortBy": "role", "sortOrder": "asc", "page_size": 10},
        )
        assert roles.status_code == 200
        assert [user["role"] for user in roles.json()["items"]] == [
            "admin",
            "superadmin",
            "user",
        ]

    await database.close()
