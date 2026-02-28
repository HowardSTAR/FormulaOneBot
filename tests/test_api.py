"""
Тесты API эндпоинтов (Mini App).
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_season_schedule(api_client: AsyncClient):
    """GET /api/season — расписание сезона."""
    with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = [
            {"round": 1, "date": "2024-03-02", "event_name": "Bahrain GP", "country": "Bahrain", "location": "Sakhir"},
        ]
        r = await api_client.get("/api/season", params={"season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert data["season"] == 2024
    assert "races" in data
    assert len(data["races"]) >= 1


@pytest.mark.asyncio
async def test_api_season_default_year(api_client: AsyncClient):
    """GET /api/season без season — текущий год."""
    with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = []
        r = await api_client.get("/api/season")
    assert r.status_code == 200
    assert r.json()["season"] == datetime.now().year


@pytest.mark.asyncio
async def test_api_drivers(api_client: AsyncClient):
    """GET /api/drivers — список пилотов."""
    with patch("app.api.miniapp_api.get_driver_standings_async", new_callable=AsyncMock) as m:
        m.return_value = pd.DataFrame([
            {"position": 1, "points": 100, "driverCode": "VER", "givenName": "Max", "familyName": "Verstappen",
             "constructorId": "red_bull", "constructorName": "Red Bull", "driverId": "verstappen", "permanentNumber": "1"},
        ])
        r = await api_client.get("/api/drivers", params={"season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert data["season"] == 2024
    assert "drivers" in data
    assert len(data["drivers"]) >= 1
    assert data["drivers"][0]["code"] == "VER"


@pytest.mark.asyncio
async def test_api_constructors(api_client: AsyncClient):
    """GET /api/constructors — список команд."""
    with patch("app.api.miniapp_api.get_constructor_standings_async", new_callable=AsyncMock) as m:
        m.return_value = pd.DataFrame([
            {"position": 1, "points": 180, "constructorId": "red_bull", "constructorName": "Red Bull"},
        ])
        r = await api_client.get("/api/constructors", params={"season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert "constructors" in data
    assert any(c["name"] == "Red Bull" for c in data["constructors"])


@pytest.mark.asyncio
async def test_api_driver_details_400(api_client: AsyncClient):
    """GET /api/driver-details без code/driverId — 400."""
    r = await api_client.get("/api/driver-details")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_api_driver_details_404(api_client: AsyncClient):
    """GET /api/driver-details — пилот не найден."""
    with patch("app.api.miniapp_api.get_driver_details_async", new_callable=AsyncMock) as m:
        m.return_value = None
        r = await api_client.get("/api/driver-details", params={"code": "XXX"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_driver_details_ok(api_client: AsyncClient):
    """GET /api/driver-details — успешный ответ."""
    with patch("app.api.miniapp_api.get_driver_details_async", new_callable=AsyncMock) as m:
        m.return_value = {
            "driver_id": "verstappen",
            "code": "VER",
            "name": "Max Verstappen",
            "nationality": "Dutch",
            "season_stats": [],
        }
        r = await api_client.get("/api/driver-details", params={"code": "VER", "season": 2024})
    assert r.status_code == 200
    assert r.json()["code"] == "VER"


@pytest.mark.asyncio
async def test_api_constructor_details_400(api_client: AsyncClient):
    """GET /api/constructor-details без constructorId — 400."""
    r = await api_client.get("/api/constructor-details")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_api_constructor_details_ok(api_client: AsyncClient):
    """GET /api/constructor-details — успешный ответ."""
    with patch("app.api.miniapp_api.get_constructor_details_async", new_callable=AsyncMock) as m:
        m.return_value = {
            "constructor_id": "ferrari",
            "name": "Ferrari",
            "nationality": "Italian",
            "season_drivers": [],
        }
        r = await api_client.get("/api/constructor-details", params={"constructorId": "ferrari", "season": 2024})
    assert r.status_code == 200
    assert "ferrari" in r.json().get("constructor_id", "").lower()


@pytest.mark.asyncio
async def test_api_settings_get(api_client: AsyncClient):
    """GET /api/settings — настройки (с подменой auth)."""
    r = await api_client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert "timezone" in data
    assert "notify_before" in data


@pytest.mark.asyncio
async def test_api_settings_save(api_client: AsyncClient):
    """POST /api/settings — сохранение настроек."""
    r = await api_client.post(
        "/api/settings",
        json={"timezone": "Europe/Moscow", "notify_before": 60, "notifications_enabled": True},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_favorites(api_client: AsyncClient):
    """GET /api/favorites — список избранного."""
    r = await api_client.get("/api/favorites")
    assert r.status_code == 200
    data = r.json()
    assert "drivers" in data
    assert "teams" in data


@pytest.mark.asyncio
async def test_api_toggle_favorite_driver(api_client: AsyncClient):
    """POST /api/favorites/driver — добавить/удалить пилота."""
    r = await api_client.post("/api/favorites/driver", json={"id": "VER"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("added", "removed")
    assert data["id"] == "VER"


@pytest.mark.asyncio
async def test_api_toggle_favorite_team(api_client: AsyncClient):
    """POST /api/favorites/team — добавить/удалить команду."""
    r = await api_client.post("/api/favorites/team", json={"id": "Red Bull"})
    assert r.status_code == 200
    assert r.json()["status"] in ("added", "removed")


@pytest.mark.asyncio
async def test_api_next_race(api_client: AsyncClient):
    """GET /api/next-race — ближайшая гонка."""
    with patch("app.api.miniapp_api.build_next_race_payload", new_callable=AsyncMock) as m:
        m.return_value = {
            "status": "ok",
            "season": 2024,
            "round": 1,
            "event_name": "Bahrain GP",
            "country": "Bahrain",
            "location": "Sakhir",
            "date": "2024-03-02",
        }
        r = await api_client.get("/api/next-race", params={"season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["round"] == 1


@pytest.mark.asyncio
async def test_api_weekend_schedule(api_client: AsyncClient):
    """GET /api/weekend-schedule — расписание уикенда."""
    with patch("app.api.miniapp_api.get_weekend_schedule") as m:
        m.return_value = [
            {"name": "Practice 1", "utc_iso": "2024-03-01T10:00:00Z"},
            {"name": "Qualifying", "utc_iso": "2024-03-02T15:00:00Z"},
        ]
        r = await api_client.get("/api/weekend-schedule", params={"round_number": 1, "season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert "sessions" in data
    assert len(data["sessions"]) >= 2


@pytest.mark.asyncio
async def test_api_votes_race(api_client: AsyncClient):
    """POST /api/votes/race — оценка гонки."""
    r = await api_client.post("/api/votes/race", json={"season": 2024, "round": 1, "rating": 5})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_api_votes_race_invalid_rating(api_client: AsyncClient):
    """POST /api/votes/race — невалидный rating."""
    r = await api_client.post("/api/votes/race", json={"season": 2024, "round": 1, "rating": 10})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_api_votes_me(api_client: AsyncClient):
    """GET /api/votes/me — голоса пользователя."""
    r = await api_client.get("/api/votes/me", params={"season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert "race_votes" in data
    assert "driver_votes" in data


@pytest.mark.asyncio
async def test_api_votes_stats(api_client: AsyncClient):
    """GET /api/votes/stats — статистика оценок гонок."""
    with patch("app.api.miniapp_api.get_race_vote_stats", new_callable=AsyncMock) as m:
        m.return_value = [(1, 4.5, 10), (2, 4.2, 8)]
        r = await api_client.get("/api/votes/stats", params={"season": 2024})
    assert r.status_code == 200
    assert "stats" in r.json()


@pytest.mark.asyncio
async def test_api_votes_driver_stats(api_client: AsyncClient):
    """GET /api/votes/driver-stats — голоса за пилотов дня."""
    with patch("app.api.miniapp_api.get_driver_vote_stats", new_callable=AsyncMock) as m:
        m.return_value = [("VER", 50), ("NOR", 30)]
        r = await api_client.get("/api/votes/driver-stats", params={"season": 2024})
    assert r.status_code == 200
    assert "stats" in r.json()


@pytest.mark.asyncio
async def test_api_compare(api_client: AsyncClient):
    """GET /api/compare — сравнение пилотов."""
    with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = [
            {"round": 1, "event_name": "Bahrain GP", "date": "2024-03-02"},
        ]
        with patch("app.api.miniapp_api.get_race_results_async", new_callable=AsyncMock) as m2:
            m2.return_value = pd.DataFrame([
                {"Abbreviation": "VER", "Points": 25},
                {"Abbreviation": "NOR", "Points": 18},
            ])
            r = await api_client.get("/api/compare", params={"d1": "VER", "d2": "NOR", "season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert "labels" in data
    assert "data1" in data
    assert "data2" in data
    assert data["data1"]["code"] == "VER"


@pytest.mark.asyncio
async def test_api_compare_teams(api_client: AsyncClient):
    """GET /api/compare/teams — сравнение команд."""
    with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = [{"round": 1, "event_name": "Bahrain GP", "date": "2024-03-02"}]
        with patch("app.api.miniapp_api.get_race_results_async", new_callable=AsyncMock) as m2:
            m2.return_value = pd.DataFrame([
                {"TeamName": "Red Bull", "Points": 43},
                {"TeamName": "McLaren", "Points": 30},
            ])
            r = await api_client.get("/api/compare/teams", params={"c1": "Red Bull", "c2": "McLaren", "season": 2024})
    assert r.status_code == 200
    data = r.json()
    assert "data1" in data
    assert "data2" in data


@pytest.mark.asyncio
async def test_api_race_details(api_client: AsyncClient):
    """GET /api/race-details — детали этапа."""
    with patch("app.api.miniapp_api.get_event_details_async", new_callable=AsyncMock) as m:
        m.return_value = {
            "event_name": "Bahrain GP",
            "country": "Bahrain",
            "sessions": [{"name": "Race", "utc_iso": "2024-03-02T15:00:00Z"}],
        }
        r = await api_client.get("/api/race-details", params={"season": 2024, "round": 1})
    assert r.status_code == 200
    data = r.json()
    assert "event_name" in data


@pytest.mark.asyncio
async def test_api_race_details_404(api_client: AsyncClient):
    """GET /api/race-details — этап не найден."""
    with patch("app.api.miniapp_api.get_event_details_async", new_callable=AsyncMock) as m:
        m.return_value = None
        r = await api_client.get("/api/race-details", params={"season": 2024, "round": 99})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_quali_results(api_client: AsyncClient):
    """GET /api/quali-results — результаты квалификации."""
    with patch("app.api.miniapp_api._get_latest_quali_async", new_callable=AsyncMock) as m:
        m.return_value = (
            1,
            [
                {"position": 1, "driver": "VER", "name": "Max Verstappen", "best": "1:29.0"},
            ],
        )
        with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m2:
            m2.return_value = [{"round": 1, "event_name": "Bahrain GP"}]
            r = await api_client.get("/api/quali-results")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data


@pytest.mark.asyncio
async def test_api_notifications_get(api_client: AsyncClient):
    """GET /api/settings/notifications."""
    r = await api_client.get("/api/settings/notifications")
    assert r.status_code == 200
    assert "is_enabled" in r.json()


@pytest.mark.asyncio
async def test_api_notifications_post(api_client: AsyncClient):
    """POST /api/settings/notifications."""
    r = await api_client.post("/api/settings/notifications", json={"is_enabled": True})
    assert r.status_code == 200
    assert r.json()["is_enabled"] is True


@pytest.mark.asyncio
async def test_api_race_results(api_client: AsyncClient):
    """GET /api/race-results — результаты последней гонки."""
    with patch("app.api.miniapp_api.get_season_schedule_short_async", new_callable=AsyncMock) as m:
        m.return_value = [
            {"round": 1, "date": "2024-03-02", "event_name": "Bahrain GP"},
        ]
        with patch("app.api.miniapp_api.get_race_results_async", new_callable=AsyncMock) as m2:
            m2.return_value = pd.DataFrame([
                {"Position": 1, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull", "Points": 25},
            ])
            r = await api_client.get("/api/race-results")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "race_info" in data


@pytest.mark.asyncio
async def test_api_car_image_404(api_client: AsyncClient):
    """GET /api/car-image — машина не найдена."""
    with patch("app.api.miniapp_api.get_car_image_path") as m:
        m.return_value = None
        r = await api_client.get("/api/car-image", params={"team": "UnknownTeam"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_team_logo_404(api_client: AsyncClient):
    """GET /api/team-logo — логотип не найден."""
    with patch("app.api.miniapp_api._get_team_logo") as m:
        m.return_value = None
        r = await api_client.get("/api/team-logo", params={"team": "Unknown"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_static_not_api_route(api_client: AsyncClient):
    """Запрос api/xxx без реального эндпоинта — 404."""
    r = await api_client.get("/api/nonexistent")
    assert r.status_code == 404
