"""
Тесты функций f1_data.
"""
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.f1_data import (
    _fill_drivers_headshots,
    get_driver_details_async,
    get_sprint_quali_results_async,
    sort_standings_zero_last,
)


def test_sort_standings_zero_last_normal():
    """sort_standings_zero_last — обычная сортировка по позициям."""
    df = pd.DataFrame([
        {"position": 2, "points": 50},
        {"position": 1, "points": 100},
        {"position": 3, "points": 30},
    ])
    result = sort_standings_zero_last(df, "position")
    assert list(result["position"]) == [1, 2, 3]


def test_sort_standings_zero_last_zero_last():
    """sort_standings_zero_last — пилоты с 0/NaN в конце."""
    df = pd.DataFrame([
        {"position": 0, "points": 0},
        {"position": 1, "points": 100},
        {"position": float("nan"), "points": 0},
        {"position": 2, "points": 50},
    ])
    result = sort_standings_zero_last(df, "position")
    # 1 и 2 должны быть первыми
    first_positions = list(result["position"].head(2))
    assert 1 in first_positions
    assert 2 in first_positions
    # 0 и NaN в конце
    last_positions = list(result["position"].tail(2))
    assert 0 in last_positions or any(pd.isna(p) for p in last_positions)


def test_sort_standings_zero_last_empty():
    """sort_standings_zero_last — пустой DataFrame."""
    df = pd.DataFrame(columns=["position", "points"])
    result = sort_standings_zero_last(df)
    assert result.empty


def test_sort_standings_zero_last_none_handling():
    """sort_standings_zero_last — None/отсутствие колонки."""
    assert sort_standings_zero_last(None) is None
    df = pd.DataFrame([{"x": 1}])
    result = sort_standings_zero_last(df, "position")
    assert result is not None
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_driver_details_uses_wiki_thumbnail_when_openf1_unavailable():
    """Если OpenF1 недоступен, карточка пилота получает headshot из Wikipedia thumbnail."""
    with patch("app.f1_data._try_bases", new_callable=AsyncMock) as try_bases_mock, \
            patch("app.f1_data._fetch_driver_season_results", new_callable=AsyncMock) as season_results_mock, \
            patch("app.f1_data._fetch_driver_career_results", new_callable=AsyncMock) as career_results_mock, \
            patch("app.f1_data._fetch_wiki_bio", new_callable=AsyncMock) as wiki_bio_mock, \
            patch("app.f1_data._fetch_driver_headshot", new_callable=AsyncMock) as openf1_headshot_mock, \
            patch("app.f1_data._fetch_wiki_thumbnail", new_callable=AsyncMock) as wiki_thumb_mock, \
            patch("app.f1_data.get_driver_standings_async", new_callable=AsyncMock) as standings_mock, \
            patch("app.f1_data._count_driver_championships", new_callable=AsyncMock) as championships_mock:
        try_bases_mock.return_value = {
            "MRData": {
                "DriverTable": {
                    "Drivers": [{
                        "driverId": "verstappen",
                        "code": "VER",
                        "givenName": "Max",
                        "familyName": "Verstappen",
                        "url": "https://en.wikipedia.org/wiki/Max_Verstappen",
                    }]
                }
            }
        }
        season_results_mock.return_value = []
        career_results_mock.return_value = []
        wiki_bio_mock.return_value = "bio"
        openf1_headshot_mock.return_value = ""
        wiki_thumb_mock.return_value = "https://upload.wikimedia.org/max.png"
        standings_mock.return_value = pd.DataFrame()
        championships_mock.return_value = 0

        details = await get_driver_details_async("verstappen", 2026)

    assert details is not None
    assert details["headshot_url"] == "https://upload.wikimedia.org/max.png"


@pytest.mark.asyncio
async def test_fill_drivers_headshots_uses_wiki_thumbnail_when_openf1_unavailable():
    """Для состава команды при пустом OpenF1 берется Wikipedia thumbnail."""
    season_drivers = [{
        "code": "VER",
        "givenName": "Max",
        "familyName": "Verstappen",
        "nationality": "",
        "url": "https://en.wikipedia.org/wiki/Max_Verstappen",
    }]

    class FakeSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("OpenF1 unavailable in test")

    with patch("app.f1_data._fetch_wiki_thumbnail", new_callable=AsyncMock) as wiki_thumb_mock, \
            patch("app.f1_data._fetch_json", new_callable=AsyncMock) as fetch_json_mock:
        wiki_thumb_mock.return_value = "https://upload.wikimedia.org/max-team.png"
        fetch_json_mock.return_value = None

        await _fill_drivers_headshots(FakeSession(), season_drivers, 2026)

    assert season_drivers[0]["headshot_url"] == "https://upload.wikimedia.org/max-team.png"


@pytest.mark.asyncio
async def test_get_sprint_quali_results_async_falls_back_to_openf1_when_fastf1_empty():
    """Если FastF1 не дал SQ, используем OpenF1 fallback по дате sprint_quali."""
    fallback_results = [
        {"position": 1, "driver": "RUS", "name": "George Russell", "best": "1:31.0", "gap": "1:31.0"}
    ]
    with patch("app.f1_data._run_sync", new_callable=AsyncMock) as run_sync_mock, \
            patch("app.f1_data.openf1_get_sprint_quali_for_round", new_callable=AsyncMock) as openf1_sq_mock:
        run_sync_mock.return_value = []
        openf1_sq_mock.return_value = (2, fallback_results)

        res = await get_sprint_quali_results_async(2026, 99, limit=20)

    assert res == fallback_results
