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
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://turbotears.example")

    primary = await create_verified_session(auth, mailer, primary_email.upper())
    regular = await create_verified_session(auth, mailer, "fan@example.com")
    assert primary.user["role"] == "superadmin"
    assert regular.user["role"] == "user"

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/admin/me")).status_code == 401

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as regular_client:
        regular_client.cookies.set("turbotears_session", regular.token)
        regular_client.cookies.set("turbotears_csrf", regular.csrf_token)
        assert (await regular_client.get("/api/admin/me")).status_code == 403

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.cookies.set("turbotears_session", primary.token)
        admin_client.cookies.set("turbotears_csrf", primary.csrf_token)
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
        client.cookies.set("turbotears_session", primary.token)
        client.cookies.set("turbotears_csrf", primary.csrf_token)
        response = await client.get("/api/admin/metrics", params={"period": "7d", "source": "all"})
        assert response.status_code == 200
        cards = response.json()["cards"]
        assert cards["site"]["dau"] == 1
        assert cards["bot"]["dau"] == 2
        assert cards["all"]["dau"] == 3
        assert cards["all"]["dau"] == cards["site"]["dau"] + cards["bot"]["dau"]
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
        client.cookies.set("turbotears_session", primary.token)
        client.cookies.set("turbotears_csrf", primary.csrf_token)

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


@pytest.mark.asyncio
async def test_admin_can_clear_all_game_records_or_only_one_users_records(temp_db_path, monkeypatch):
    """Game cleanup preserves profiles and never removes another player's rows by accident."""
    primary_email, _ = configured_primary_admin()
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    mailer = MockMailer()
    auth = AuthService(database, mailer, pepper="admin-game-records-test-pepper")
    monkeypatch.setattr(auth_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(admin_api, "db", database)

    primary = await create_verified_session(auth, mailer, primary_email)
    regular = await create_verified_session(auth, mailer, "game-player@example.com")
    delegated = await create_verified_session(auth, mailer, "game-admin@example.com")
    player_telegram_id = 710_001
    other_telegram_id = 710_002
    await database.conn.executemany(
        "UPDATE users SET telegram_id = ?, role = ? WHERE id = ?",
        [
            (player_telegram_id, "user", regular.user["id"]),
            (710_003, "admin", delegated.user["id"]),
        ],
    )
    await database.conn.executemany(
        "INSERT INTO reaction_leaderboard_profiles(telegram_id, display_name, leaderboard_opt_in) VALUES (?, ?, 1)",
        [
            (player_telegram_id, "Player One"),
            (other_telegram_id, "Player Two"),
        ],
    )
    await database.conn.executemany(
        "INSERT INTO reaction_leaderboard_scores(telegram_id, time_ms) VALUES (?, ?)",
        [
            (player_telegram_id, 250),
            (player_telegram_id, 230),
            (other_telegram_id, 240),
        ],
    )
    await database.conn.executemany(
        "INSERT INTO race_game_scores(telegram_id, time_ms, track_id) VALUES (?, ?, 'emerald-loop-v1')",
        [
            (player_telegram_id, 80_000),
            (other_telegram_id, 79_000),
        ],
    )
    await database.conn.executemany(
        "INSERT INTO reflex_grid_scores(telegram_id, mode, difficulty, score, time_ms) VALUES (?, 'timed', 'easy', ?, ?)",
        [
            (player_telegram_id, 8, 10_000),
            (other_telegram_id, 9, 9_000),
        ],
    )
    await database.conn.commit()

    transport = httpx.ASGITransport(app=web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("turbotears_session", primary.token)
        client.cookies.set("turbotears_csrf", primary.csrf_token)

        stats = await client.get("/api/admin/game-records")
        assert stats.status_code == 200
        assert stats.json()["total_records"] == 7
        assert stats.json()["total_players"] == 2

        client.cookies.set("turbotears_session", delegated.token)
        client.cookies.set("turbotears_csrf", delegated.csrf_token)
        deleted_user = await client.delete(
            f"/api/admin/users/{regular.user['id']}/game-records/all",
            headers={"X-CSRF-Token": delegated.csrf_token},
        )
        assert deleted_user.status_code == 200
        assert deleted_user.json()["deleted"] == {"reaction": 2, "race": 1, "reflex": 1}
        assert deleted_user.json()["total"] == 4

        for table in (
            "reaction_leaderboard_scores",
            "race_game_scores",
            "reflex_grid_scores",
        ):
            async with database.conn.execute(
                f'SELECT telegram_id FROM "{table}" ORDER BY id'
            ) as cursor:
                assert [row["telegram_id"] for row in await cursor.fetchall()] == [other_telegram_id]
        async with database.conn.execute(
            "SELECT display_name FROM reaction_leaderboard_profiles WHERE telegram_id = ?",
            (player_telegram_id,),
        ) as cursor:
            assert (await cursor.fetchone())["display_name"] == "Player One"

        forbidden = await client.delete(
            "/api/admin/game-records/all",
            headers={"X-CSRF-Token": delegated.csrf_token},
        )
        assert forbidden.status_code == 403

        client.cookies.set("turbotears_session", primary.token)
        client.cookies.set("turbotears_csrf", primary.csrf_token)
        deleted_all = await client.delete(
            "/api/admin/game-records/all",
            headers={"X-CSRF-Token": primary.csrf_token},
        )
        assert deleted_all.status_code == 200
        assert deleted_all.json()["deleted"] == {"reaction": 1, "race": 1, "reflex": 1}
        assert deleted_all.json()["total"] == 3

        after = await client.get("/api/admin/game-records")
        assert after.json()["total_records"] == 0
        audit = await client.get("/api/admin/audit-log")
        assert [item["action"] for item in audit.json()["items"][:2]] == [
            "game_records.cleared",
            "game_records.user_cleared",
        ]

    await database.close()
