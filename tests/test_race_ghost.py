"""Regression for the real Phaser angle format and public ghost playback."""
import math

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.miniapp_api import get_current_user_id


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_angles", [False, True])
async def test_recorded_trajectory_is_saved_and_available_to_guests(api_client, app_with_overrides, legacy_angles):
    await api_client.post("/api/reaction-leaderboard/profile", json={
        "display_name": "Record Pilot", "participate": True, "prompt_seen": True,
    })
    samples = []
    for t in range(0, 75_001, 100):
        angle = -math.pi / 2 - t / 75_000 * 6 * math.pi
        rotation = angle % (2 * math.pi) if legacy_angles else math.atan2(math.sin(angle), math.cos(angle))
        samples.append({
            "t": t, "x": round(750 + 300 * math.cos(angle), 2),
            "y": round(500 + 200 * math.sin(angle), 2), "rotation": round(rotation, 4),
        })
    response = await api_client.post("/api/race-game-leaderboard/score", json={
        "time_ms": 75_000, "telemetry": samples,
    })
    assert response.status_code == 200, response.text
    assert response.json()["saved"] is True
    # Separate HTTP client: no login, no dependency providing a viewer identity.
    async with AsyncClient(transport=ASGITransport(app=app_with_overrides), base_url="http://guest") as guest:
        loaded = await guest.get("/api/race-game/ghost")
        assert loaded.status_code == 200
        assert loaded.headers["cache-control"] == "no-store"
        ghost = loaded.json()["ghost"]
        assert ghost["name"] == "Record Pilot"
        assert ghost["time_ms"] == 75_000
        assert len(ghost["samples"]) == len(samples)
        for recorded, replayed in zip(samples, ghost["samples"]):
            assert (recorded["t"], recorded["x"], recorded["y"]) == (replayed["t"], replayed["x"], replayed["y"])
            assert -3.142 <= replayed["rotation"] <= 3.142
            assert math.cos(recorded["rotation"]) == pytest.approx(math.cos(replayed["rotation"]), abs=0.0001)
            assert math.sin(recorded["rotation"]) == pytest.approx(math.sin(replayed["rotation"]), abs=0.0001)


@pytest.mark.asyncio
async def test_public_ghost_switches_to_faster_driver_and_clears_with_records(api_client, app_with_overrides):
    from app.db import db

    async def submit(time_ms, name):
        await api_client.post("/api/reaction-leaderboard/profile", json={
            "display_name": name, "participate": True, "prompt_seen": True,
        })
        response = await api_client.post("/api/race-game-leaderboard/score", json={
            "time_ms": time_ms, "telemetry": [
                {"t": 0, "x": 875, "y": 660, "rotation": -1.5708},
                {"t": time_ms, "x": 880, "y": 660, "rotation": -1.5708},
            ],
        })
        assert response.status_code == 200
        assert response.json()["saved"]

    await submit(80_000, "First")
    app_with_overrides.dependency_overrides[get_current_user_id] = lambda: 1234567
    await submit(75_000, "Faster")
    app_with_overrides.dependency_overrides[get_current_user_id] = lambda: 2345678
    await submit(85_000, "Slower")
    ghost = (await api_client.get("/api/race-game/ghost")).json()["ghost"]
    assert ghost["name"] == "Faster"
    assert ghost["time_ms"] == 75_000
    await db.conn.execute("DELETE FROM race_game_scores")
    await db.conn.commit()
    assert (await api_client.get("/api/race-game/ghost")).json()["ghost"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["race", "all"])
async def test_admin_wipe_removes_every_role_and_public_ghost(api_client, app_with_overrides, scope):
    from app.api.admin_api import AdminContext, require_superadmin
    from app.db import db, get_or_create_user

    admin_id = None
    for index, role in enumerate(["user", "admin", "superadmin"]):
        telegram_id = 810_000 + index
        user_id = await get_or_create_user(telegram_id)
        await db.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        app_with_overrides.dependency_overrides[get_current_user_id] = lambda tid=telegram_id: tid
        await api_client.post("/api/reaction-leaderboard/profile", json={
            "display_name": role, "participate": True, "prompt_seen": True,
        })
        time_ms = 80_000 - index * 1000
        response = await api_client.post("/api/race-game-leaderboard/score", json={
            "time_ms": time_ms, "telemetry": [
                {"t": 0, "x": 875, "y": 660, "rotation": 0},
                {"t": time_ms, "x": 875, "y": 660, "rotation": 0},
            ],
        })
        assert response.status_code == 200, response.text
        assert response.json()["saved"]
        admin_id = user_id
    await db.conn.commit()
    assert (await api_client.get("/api/race-game/ghost")).json()["ghost"]["name"] == "superadmin"
    app_with_overrides.dependency_overrides[require_superadmin] = lambda: AdminContext(id=admin_id, role="superadmin")
    wiped = await api_client.delete(f"/api/admin/game-records/{scope}")
    assert wiped.status_code == 200, wiped.text
    assert wiped.json()["deleted"]["race"] == 3
    async with db.conn.execute("SELECT COUNT(*) FROM race_game_scores") as cursor:
        assert (await cursor.fetchone())[0] == 0
    assert (await api_client.get("/api/race-game-leaderboard")).json()["entries"] == []
    assert (await api_client.get("/api/race-game/ghost")).json()["ghost"] is None
    async with db.conn.execute("SELECT COUNT(*) FROM reaction_leaderboard_profiles") as cursor:
        assert (await cursor.fetchone())[0] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("start,end", [(100, 75_000), (0, 1000), (0, 76_000)])
async def test_incomplete_telemetry_is_rejected(api_client, start, end):
    response = await api_client.post("/api/race-game-leaderboard/score", json={
        "time_ms": 75_000, "telemetry": [
            {"t": start, "x": 875, "y": 660, "rotation": 0},
            {"t": end, "x": 875, "y": 660, "rotation": 0},
        ],
    })
    assert response.status_code == 422
