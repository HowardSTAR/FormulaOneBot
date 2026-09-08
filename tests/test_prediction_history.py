import time
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.prediction_factors import features
from app.services import prediction_history as archive_module
from app.services.prediction_analytics import normalize_classification, timestamp


def race(year=2025, number=1, date="2025-01-01"):
    return {"season": str(year), "round": str(number), "raceName": "Test GP", "date": date, "time": "12:00:00Z",
            "Circuit": {"circuitId": "test", "Location": {"locality": "Test"}},
            "Results": [{"position": str(i+1), "grid": str(20-i), "status": "Finished", "Driver": {"code": f"D{i}", "givenName": "Driver", "familyName": str(i)}, "Constructor": {"name": "Team", "constructorId": "team"}} for i in range(20)]}


@pytest.mark.asyncio
async def test_archive_merges_split_races_and_uses_persistent_cache(app_with_overrides, monkeypatch):
    monkeypatch.setattr(archive_module.asyncio, "sleep", AsyncMock())
    full = race()
    client = AsyncMock()
    client.get.side_effect = [httpx.Response(200, request=httpx.Request("GET", "https://example.test"), json={"MRData": {"total": "20", "RaceTable": {"Races": [{**full, "Results": full["Results"][start:end]}]}}}) for start, end in [(0, 12), (12, 20)]]
    result = await archive_module.archive(client, 2025, "race", time.time())
    assert len(result[0]["Results"]) == 20
    assert client.get.await_args_list[1].kwargs["params"]["offset"] == 12
    assert await archive_module.archive(client, 2025, "race", time.time()) == result
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_partial_download_is_not_cached(app_with_overrides, monkeypatch):
    from app.db import db
    monkeypatch.setattr(archive_module.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, request=httpx.Request("GET", "https://example.test"), json={"MRData": {"total": "20", "RaceTable": {"Races": []}}})
    with pytest.raises(ValueError):
        await archive_module.archive(client, 2024, "race", time.time())
    assert (await (await db.conn.execute("SELECT COUNT(*) FROM prediction_history_cache")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_five_seasons_both_sessions_and_cutoff(monkeypatch):
    async def fake(client, year, session, cutoff):
        old = race(year, 1, f"{year}-01-01")
        newer = race(year, 2, f"{year}-12-31")
        if session == "qualifying":
            for r in (old, newer):
                r["QualifyingResults"] = r.pop("Results")
        return [old, newer]
    source = AsyncMock(side_effect=fake)
    monkeypatch.setattr(archive_module, "archive", source)
    cutoff = timestamp("2026-09-01T00:00:00Z")
    history, coverage = await archive_module.load_history(None, 2026, {"round": 9, "location": "Test"}, cutoff, normalize_classification, timestamp)
    assert source.await_count == 10
    assert coverage["loaded_years"] == [2022, 2023, 2024, 2025, 2026]
    assert coverage["races"] == coverage["qualifying"] == 9
    assert all(h["ended_at"] < cutoff for h in history)
    assert all(h["circuit"] for h in history)
    assert all(not (h["season"] == 2026 and h["round"] == 2) for h in history)


def test_deep_factors_history_beyond_six_and_cross_session():
    driver = {"code": "D0", "name": "Driver 0", "team": "Team"}
    rows = normalize_classification(race(), "race")
    history = [{"rows": rows, "session": kind, "weight": .8, "circuit": True, "season": 2025, "round": i} for kind in ("race", "qualifying") for i in range(20)]
    data = features(driver, history, "race", [])
    factors = {f["key"]: f for f in data["factors"]}
    assert factors["long"]["samples"] == 20
    assert factors["recent"]["samples"] == 6
    assert factors["qualifying"]["samples"] == 20
    assert factors["gains"]["samples"] == 20
    assert sum(f["weight"] for f in data["factors"]) == pytest.approx(1)
    assert sum(f["contribution"] for f in data["factors"]) == pytest.approx(data["rating"] - .5)
    switched = features({**driver, "team": "New Team"}, history, "race", [])
    assert next(f for f in switched["factors"] if f["key"] == "long")["effective_samples"] < factors["long"]["effective_samples"]
    assert len(data["timeline"]) == 12
