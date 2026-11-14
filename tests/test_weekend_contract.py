"""Native weekend contract: HTTP serialization, source failures and legacy compatibility."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import weekend_api, miniapp_api

RACE = {
    "round": 1, "event_name": "Australian Grand Prix", "country": "Australia",
    "location": "Melbourne", "date": "2026-03-08",
    "race_start_utc": "2026-03-08T15:00:00+11:00",
}


@pytest.mark.asyncio
async def test_public_weekend_serialization_and_legacy_compatibility(monkeypatch):
    """Anonymous clients get UTC dates and codes; old clients still get Russian labels."""
    source = [{"name": "Race", "utc_iso": "2026-03-08T15:00:00+11:00"},
              {"name": "Future Session", "utc_iso": None}]
    original = deepcopy(source)
    monkeypatch.setattr(weekend_api, "get_season_schedule_short_async", AsyncMock(return_value=[RACE]))
    monkeypatch.setattr(weekend_api, "get_weekend_schedule", lambda *_: source)
    monkeypatch.setattr(miniapp_api, "get_weekend_schedule", lambda *_: deepcopy(source))
    async with AsyncClient(transport=ASGITransport(app=miniapp_api.web_app), base_url="http://test") as client:
        response = await client.get("/api/v1/weekend?season=2026&round=1")
        assert response.status_code == 200
        data = response.json()
        assert data["event"]["id"] == "2026:1"
        assert data["event"]["date"] == "2026-03-08"
        assert data["event"]["starts_at"] == "2026-03-08T04:00:00Z"
        assert data["sessions"] == [
            {"code": "race", "source_name": "Race", "starts_at": "2026-03-08T04:00:00Z"},
            {"code": "unknown", "source_name": "Future Session", "starts_at": None},
        ]
        assert data["schedule_status"] == "available"
        legacy = await client.get("/api/weekend-schedule?season=2026&round_number=1")
        assert legacy.status_code == 200
        assert legacy.json()["sessions"][0]["name"] == "Гонка"
    assert source == original


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["no_schedule", "season_finished"])
async def test_next_weekend_uses_shared_empty_states(api_client, monkeypatch, status):
    next_race = AsyncMock(return_value={"status": status, "season": 2026})
    monkeypatch.setattr(weekend_api, "build_next_race_payload", next_race)
    response = await api_client.get("/api/v1/weekend?season=2026")
    assert response.status_code == 200
    assert response.json() == {"status": status, "season": 2026, "event": None,
                               "sessions": [], "schedule_status": "not_applicable"}
    next_race.assert_awaited_once_with(2026)


@pytest.mark.asyncio
async def test_next_weekend_uses_shared_event_selection(api_client, monkeypatch):
    monkeypatch.setattr(weekend_api, "build_next_race_payload", AsyncMock(return_value={"status": "ok", **RACE}))
    monkeypatch.setattr(weekend_api, "get_weekend_schedule", lambda *_: [])
    response = await api_client.get("/api/v1/weekend?season=2026")
    assert response.status_code == 200
    assert response.json()["event"]["id"] == "2026:1"
    assert response.json()["schedule_status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_missing_times_and_cancelled_event(api_client, monkeypatch, cancelled):
    race = {**RACE, "race_start_utc": None, "is_cancelled": cancelled}
    monkeypatch.setattr(weekend_api, "get_season_schedule_short_async", AsyncMock(return_value=[race]))
    def unavailable(*_):
        assert not cancelled, "Cancelled events must not load sessions"
        return []
    monkeypatch.setattr(weekend_api, "get_weekend_schedule", unavailable)
    response = await api_client.get("/api/v1/weekend?season=2026&round=1")
    assert response.status_code == 200
    data = response.json()
    assert data["event"]["starts_at"] is None
    assert data["event"]["date"] == "2026-03-08"
    assert data["sessions"] == []
    assert data["schedule_status"] == ("cancelled" if cancelled else "unavailable")


@pytest.mark.asyncio
async def test_absent_event_and_missing_season_data(api_client, monkeypatch):
    schedule = AsyncMock(return_value=[RACE])
    monkeypatch.setattr(weekend_api, "get_season_schedule_short_async", schedule)
    response = await api_client.get("/api/v1/weekend?season=2026&round=2")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "weekend_not_found"
    schedule.return_value = []
    response = await api_client.get("/api/v1/weekend?season=2026&round=2")
    assert response.status_code == 200
    assert response.json()["status"] == "no_schedule"


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "season=1949", "season=2101", "season=2026&round=0", "season=2026&round=101", "season=no"])
async def test_invalid_weekend_parameters(api_client, query):
    response = await api_client.get(f"/api/v1/weekend?{query}")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_weekend_openapi_contract():
    """Swift generators see required nullable fields, date formats and operation ID."""
    schema = miniapp_api.web_app.openapi()
    operation = schema["paths"]["/api/v1/weekend"]["get"]
    assert operation["operationId"] == "getWeekend"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/WeekendResponse")
    session = schema["components"]["schemas"]["WeekendSession"]
    assert "starts_at" in session["required"]
    assert {"type": "string", "format": "date-time"} in session["properties"]["starts_at"]["anyOf"]
    assert "unknown" in session["properties"]["code"]["enum"]
