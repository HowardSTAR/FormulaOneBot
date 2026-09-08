import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.prediction_model import simulate, evaluate


def sample():
    roster = [{"code": f"D{i}", "name": f"Driver {i}", "team": f"Team {i // 2}"} for i in range(20)]
    rows = [{**d, "position": i + 1, "dnf": i == 19} for i, d in enumerate(roster)]
    history = [{"rows": rows, "weight": .85 ** i, "circuit": i == 2} for i in range(6)]
    return roster, rows, history


@pytest.mark.parametrize("session", ["race", "qualifying"])
def test_model_probabilities_and_reproducibility(session):
    roster, rows, history = sample()
    forecast = simulate(roster, history, session, rows, .3)
    assert forecast == simulate(roster, history, session, rows, .3)
    drivers = forecast["drivers"]
    assert sum(d["win"] for d in drivers) == pytest.approx(1)
    assert sum(d["podium"] for d in drivers) == pytest.approx(3)
    assert sum(d["top10"] for d in drivers) == pytest.approx(10)
    assert sum(s["probability"] for s in forecast["scenarios"]) == pytest.approx(1)
    assert all(0 <= d["win"] <= d["podium"] <= d["top10"] <= 1 for d in drivers)
    assert all(1 <= d["expected"] <= 20 for d in drivers)
    if session == "qualifying":
        assert all(d["dnf"] == 0 for d in drivers)
    assert len(json.dumps(forecast, allow_nan=False)) > 100


def test_model_weather_changes_risk_and_sparse_drivers_stay_finite():
    roster, rows, history = sample()
    roster[0]["code"] = "NEW"
    dry = simulate(roster, history, "race", [], 0)
    wet = simulate(roster, history, "race", [], 1)
    assert sum(d["dnf"] for d in wet["drivers"]) > sum(d["dnf"] for d in dry["drivers"])
    assert all(d["expected"] > 0 for d in dry["drivers"])
    assert evaluate(dry, rows)["matched"] == 19


def test_model_refuses_missing_data():
    with pytest.raises(ValueError):
        simulate([], [], "race", [], None)


def test_news_risk_is_explained_and_deduplicated():
    roster, _, history = sample()
    roster[0]["name"] = "Test Drivername"
    news = [{"title": "Drivername engine damage concern", "url": "https://www.bbc.com/sport/test"}]
    one = simulate(roster, history, "race", [], None, news=news)
    duplicate = simulate(roster, history, "race", [], None, news=news * 4)
    first = next(d for d in one["drivers"] if d["code"] == "D0")
    second = next(d for d in duplicate["drivers"] if d["code"] == "D0")
    assert first["win"] == second["win"]
    assert any("разброс +5%" in reason for reason in first["reasons"])


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [10, 20])
async def test_classification_rejects_partial_and_mismatched_event(size):
    from app.services.prediction_analytics import classification
    results = [{"position": str(i + 1), "Driver": {"code": f"D{i}", "givenName": "Driver", "familyName": str(i)}, "Constructor": {"name": "Team"}, "status": "Finished"} for i in range(size)]
    race = {"season": "2026", "round": "4", "Results": results}
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={"MRData": {"RaceTable": {"Races": [race]}}}, request=httpx.Request("GET", "https://example.test"))
    assert len(await classification(client, 2026, 4, "race")) == (20 if size == 20 else 0)
    assert await classification(client, 2026, 5, "race") == []
    results[-1]["position"] = "1"
    client.get.return_value = httpx.Response(200, json={"MRData": {"RaceTable": {"Races": [race]}}}, request=httpx.Request("GET", "https://example.test"))
    assert await classification(client, 2026, 4, "race") == []


@pytest.mark.asyncio
async def test_past_session_refused_before_fetching_results(monkeypatch):
    from app.services import prediction_analytics as service
    monkeypatch.setattr(service, "get_season_schedule_short_async", AsyncMock(return_value=[{"round": 1, "race_start_utc": "2020-01-01T00:00:00Z"}]))
    with pytest.raises(ValueError, match="Сессия началась"):
        await service.build_forecast(2020, 1, "race")


@pytest.mark.asyncio
async def test_build_uses_only_past_sessions_and_preserves_sources(monkeypatch):
    from datetime import datetime, timezone
    from app.services import prediction_analytics as service
    now = time.time()
    iso = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat()
    past = [{"round": i + 1, "event_name": f"Past {i}", "location": "Monza", "race_start_utc": iso(now - (i + 3) * 86400)} for i in range(4)]
    target = {"round": 10, "event_name": "Future", "location": "Monza", "race_start_utc": iso(now + 86400), "quali_start_utc": iso(now - 3 * 3600)}
    future = {"round": 11, "event_name": "Later", "race_start_utc": iso(now + 8 * 86400)}
    monkeypatch.setattr(service, "get_season_schedule_short_async", AsyncMock(side_effect=lambda y: past + [target, future] if y == 2026 else []))
    roster, rows, _ = sample()
    classify = AsyncMock(return_value=rows)
    monkeypatch.setattr(service, "classification", classify)
    context = {"weather": {"available": False}, "news": [], "news_available": False}
    monkeypatch.setattr(service, "context_data", AsyncMock(return_value=context))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = httpx.Response(200, json={"MRData": {"DriverTable": {"Drivers": []}}}, request=httpx.Request("GET", "https://example.test"))
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: client)
    result = await service.build_forecast(2026, 10, "race")
    assert result["inputs"]["weather"]["available"] is False
    assert len(result["inputs"]["roster"]) == len(roster)
    assert result["warnings"]
    assert len(result["inputs"]["history"]) == 4
    assert all(call.args[2] != 11 for call in classify.await_args_list)
    assert all(call.args[3] == "qualifying" for call in classify.await_args_list if call.args[2] == 10)
    assert result["cutoff"] < result["start_at"]


@pytest.mark.asyncio
async def test_weather_and_news_outage_is_explicit(monkeypatch):
    from app.services.prediction_analytics import context_data
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("offline")
    result = await context_data(client, {"location": "Monza"}, time.time() + 86400, time.time())
    assert not result["weather"]["available"]
    assert "rain" not in result["weather"]
    assert not result["news_available"]
    assert result["news"] == []


@pytest.mark.asyncio
async def test_forecast_routes_reject_guest_and_regular_user(app_with_overrides, monkeypatch):
    from app.api import admin_api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_with_overrides), base_url="http://test") as client:
        assert (await client.get("/api/admin/prediction-analytics?season=2026")).status_code == 401
        assert (await client.get("/api/admin/prediction-analytics/secret")).status_code == 401
        assert (await client.post("/api/admin/prediction-analytics", json={"season": 2026, "round": 2, "session": "race"})).status_code == 401
        monkeypatch.setattr(admin_api, "require_web_session", AsyncMock(return_value=SimpleNamespace(user={"id": 1, "role": "user"})))
        assert (await client.get("/api/admin/prediction-analytics?season=2026")).status_code == 403
        assert (await client.get("/api/admin/prediction-analytics/secret")).status_code == 403
        assert (await client.post("/api/admin/prediction-analytics", json={"season": 2026, "round": 2, "session": "race"})).status_code == 403


@pytest.mark.asyncio
async def test_snapshot_save_idempotent_and_settle_without_rewriting_forecast(app_with_overrides, monkeypatch):
    from app.api.admin_api import require_admin_session, AdminContext
    from app.services import prediction_analytics as service
    from app.db import db
    roster, actual, history = sample()
    payload = {"model": simulate(roster, history, "race", [], None), "start_at": time.time() - 20000, "cutoff": time.time() - 30000}
    app_with_overrides.dependency_overrides[require_admin_session] = lambda: AdminContext(id=1, role="admin")
    monkeypatch.setattr(service, "build_forecast", AsyncMock(return_value=payload))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_with_overrides), base_url="http://test") as client:
        url = "/api/admin/prediction-analytics"
        response = await client.post(url, json={"season": 2026, "round": 4, "session": "race"})
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert (await client.post(url, json={"season": 2026, "round": 4, "session": "race"})).json()["id"] == job_id
        before = (await client.get(f"{url}/{job_id}")).json()
        assert before["status"] == "ready" and before["actual"] is None
        monkeypatch.setattr(service, "classification", AsyncMock(return_value=[]))
        await service.settle_forecasts()
        assert (await client.get(f"{url}/{job_id}")).json()["actual"] is None
        monkeypatch.setattr(service, "classification", AsyncMock(return_value=actual))
        await service.settle_forecasts()
        after = (await client.get(f"{url}/{job_id}")).json()
        assert after["payload"] == before["payload"]
        assert after["actual"]["metrics"]["matched"] == 20
        await service.settle_forecasts()
        assert (await client.get(f"{url}/{job_id}")).json() == after
        count = await (await db.conn.execute("SELECT COUNT(*) FROM prediction_analytics")).fetchone()
        assert count[0] == 1


@pytest.mark.asyncio
async def test_failed_job_is_persisted_and_restart_job_expires(app_with_overrides, monkeypatch):
    from app.db import db
    from app.services import prediction_analytics as service
    await db.conn.execute("INSERT INTO prediction_analytics(id,season,round,session,created_at,created_by) VALUES('test',2026,1,'race',?,1)", (time.time(),))
    await db.conn.commit()
    monkeypatch.setattr(service, "build_forecast", AsyncMock(side_effect=ValueError("Нет данных")))
    await service.run_job("test")
    row = await (await db.conn.execute("SELECT status,error,payload FROM prediction_analytics WHERE id='test'")).fetchone()
    assert tuple(row) == ("error", "Нет данных", None)
    await db.conn.execute("UPDATE prediction_analytics SET status='pending',created_at=?", (time.time() - 1000,))
    await db.conn.commit()
    await service.settle_forecasts()
    row = await (await db.conn.execute("SELECT status,error FROM prediction_analytics WHERE id='test'")).fetchone()
    assert row[0] == "error" and "прерван" in row[1]
