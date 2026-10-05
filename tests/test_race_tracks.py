import math

import pytest

from app.race_rules import TRACKS, validate_race_path
from tests.support import replay


@pytest.mark.parametrize("track_id", TRACKS)
def test_three_laps_validate_for_every_track(track_id):
    payload = replay(track_id)
    validate_race_path(track_id, payload["telemetry"])


@pytest.mark.asyncio
async def test_records_ghosts_and_personal_progress_are_scoped_to_track(api_client):
    for index, track_id in enumerate(TRACKS):
        payload = replay(track_id, speed=200 + index * 10)
        response = await api_client.post("/api/race-game-leaderboard/score", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["saved"]
        board = response.json()["leaderboard"]
        assert board["track_id"] == track_id
        assert board["me"]["time_ms"] == payload["time_ms"]
        assert board["progress"]["attempts"] == 1
        for stored, sent in zip(board["ghost"]["samples"], payload["telemetry"]):
            assert (stored["t"], stored["x"], stored["y"]) == (sent["t"], sent["x"], sent["y"])
            assert math.cos(stored["rotation"]) == pytest.approx(math.cos(sent["rotation"]), abs=0.0001)
            assert math.sin(stored["rotation"]) == pytest.approx(math.sin(sent["rotation"]), abs=0.0001)
    for track_id in TRACKS:
        board = (await api_client.get("/api/race-game-leaderboard", params={"track_id": track_id})).json()
        assert len(board["entries"]) == 1
        assert board["progress"]["attempts"] == 1
        ghost = (await api_client.get("/api/race-game/ghost", params={"track_id": track_id})).json()
        assert ghost["track_id"] == track_id
        assert ghost["ghost"]["samples"][0]["y"] == TRACKS[track_id]["centerLine"][0][1]
    assert (await api_client.get("/api/race-game-leaderboard")).json()["entries"] == []


@pytest.mark.asyncio
async def test_legacy_records_are_preserved_and_not_used_on_updated_emerald(api_client):
    legacy = await api_client.post("/api/race-game-leaderboard/score", json={"time_ms": 80000})
    assert legacy.json()["saved"]
    board = (await api_client.get("/api/race-game-leaderboard", params={"track_id": "emerald-loop-v2"})).json()
    assert board["entries"] == []
    assert board["ghost"] is None
    assert (await api_client.get("/api/race-game-leaderboard")).json()["me"]["time_ms"] == 80000


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/api/race-game/ghost", "/api/race-game-leaderboard"])
async def test_unknown_circuit_is_rejected_on_read(api_client, endpoint):
    response = await api_client.get(endpoint, params={"track_id": "not-a-track"})
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["empty", "stationary", "teleport", "one-lap", "wrong-track", "unknown"])
async def test_invalid_new_track_records_are_rejected(api_client, variant):
    payload = replay("emerald-loop-v2", laps=1 if variant == "one-lap" else 3)
    if variant == "empty":
        payload["telemetry"] = []
    elif variant == "stationary":
        for sample in payload["telemetry"]:
            sample["x"], sample["y"] = 875, 660
    elif variant == "teleport":
        payload["telemetry"][2]["x"] = 1400
    elif variant == "wrong-track":
        payload["track_id"] = "harbor-sprint-v1"
    elif variant == "unknown":
        payload["track_id"] = "not-a-track"
    response = await api_client.post("/api/race-game-leaderboard/score", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_new_track_improvement_does_not_change_other_tracks(api_client):
    for track_id in ["sunset-speedway-v1", "harbor-sprint-v1"]:
        await api_client.post("/api/race-game-leaderboard/score", json=replay(track_id, speed=200))
    response = await api_client.post("/api/race-game-leaderboard/score", json=replay("sunset-speedway-v1", speed=220))
    assert response.json()["leaderboard"]["progress"]["attempts"] == 2
    assert response.json()["leaderboard"]["progress"]["improvement_ms"] > 0
    other = (await api_client.get("/api/race-game-leaderboard", params={"track_id": "harbor-sprint-v1"})).json()
    assert other["progress"]["attempts"] == 1
