"""No external API, production database, deliveries or AI calls in these tests."""
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.services import race_recap as recap, standings_history as history
from app.services.driver_guides import GUIDES, get_driver_guide
from app.api.f1_insights_api import router


def driver(identifier, position, points, wins=0):
    return {"driverId": identifier, "driverCode": identifier.upper(), "givenName": identifier, "familyName": "Driver",
            "position": position, "points": points, "wins": wins}


def team(identifier, position, points):
    return {"constructorId": identifier, "constructorName": identifier, "position": position, "points": points}


def race_rows():
    return [{"Position": i + 1, "Points": 25 if i == 0 else 0, "Abbreviation": identifier.upper(),
             "FullName": identifier + " Driver", "GridPosition": i + 1} for i, identifier in enumerate("abcde")]


def test_recap_prioritizes_leader_change_and_first_win():
    before = [driver("b", 1, 100), driver("a", 2, 90)]
    after = [driver("a", 1, 115, 1), driver("b", 2, 110)]
    result = recap.build_recap(race_rows(), before, after, [], [])
    assert result[0]["category"] == "championship"
    assert "Новый лидер" in result[0]["title"]
    assert "5 очк." in result[0]["text"]
    assert "Первая победа" in result[1]["title"]
    assert len(result) <= 3


def test_gap_compares_only_same_two_contenders():
    before = [driver("a", 1, 100), driver("b", 2, 80), driver("c", 3, 79)]
    after = [driver("a", 1, 125), driver("c", 2, 97), driver("b", 3, 90)]
    result = recap.build_recap(race_rows(), before, after, [], [])
    assert not any(item["category"] == "championship" for item in result)


@pytest.mark.parametrize("new_points,word", [(95, "сократился"), (70, "вырос")])
def test_gap_direction_and_amount(new_points, word):
    result = recap.build_recap(race_rows(), [driver("a", 1, 100), driver("b", 2, 80)],
                              [driver("a", 1, 110), driver("b", 2, new_points)], [], [])
    story = next(item for item in result if item["category"] == "championship")
    assert word in story["title"]
    assert f"20 → {110 - new_points} очк." in story["text"]


def test_constructor_leader_change():
    result = recap.build_recap(race_rows(), [], [], [team("old", 1, 100), team("new", 2, 99)],
                              [team("new", 1, 120), team("old", 2, 110)])
    assert result[0]["category"] == "constructors"
    assert "Кубок конструкторов" in result[0]["text"]


def test_missing_previous_standings_does_not_invent_first_win_or_clinch():
    result = recap.build_recap(race_rows(), [], [driver("a", 1, 500, 1)], [], [])
    assert result[0]["category"] == "winner"
    assert "Первая" not in result[0]["title"]
    assert "чемпион" not in result[0]["title"].lower()


def test_start_finish_gain_is_not_called_overtaking():
    rows = race_rows()
    rows[-1]["GridPosition"] = 20
    result = recap.build_recap(rows, [], [], [], [])
    story = next(item for item in result if item["category"] == "race_move")
    assert "+15" in story["title"]
    assert "не доказывает" in story["text"]


def test_classification_without_marker_is_valid_official_frame():
    assert len(recap.classified_rows(pd.DataFrame(race_rows()))) == 5


def test_zero_point_live_skeleton_cannot_generate_recap():
    frame = pd.DataFrame(race_rows())
    frame["Points"] = 0
    assert recap.classified_rows(frame) == []


@pytest.mark.parametrize("corruption", ["provisional", "points", "duplicate", "missing", "nan"])
def test_recap_rejects_unconfirmed_classification(corruption):
    frame = pd.DataFrame(race_rows())
    if corruption == "provisional":
        frame["DataComplete"] = False
    elif corruption == "points":
        frame.loc[0, "Points"] = float("nan")
    elif corruption == "duplicate":
        frame.loc[1, "Position"] = 1
    elif corruption == "nan":
        frame.loc[1, "GridPosition"] = float("nan")
        assert recap.classified_rows(frame)[1]["GridPosition"] == 0
        return
    else:
        frame = frame.drop(columns=["Points"])
    assert recap.classified_rows(frame) == []


def test_telegram_escapes_and_hides_spoilers_without_cutting_html():
    data = {"items": [{"title": "A & B <test>", "text": "10 → 5"}], "status": "ready"}
    text = recap.format_recap_telegram(data, spoiler=True)
    assert '&amp;' in text and '&lt;test&gt;' in text and 'tg-spoiler' in text
    assert len(recap.recap_caption(data, spoiler=True)) < 1024
    assert recap.recap_caption({**data, "status": "waiting"}) == ""


@pytest.mark.asyncio
async def test_waiting_recap_does_not_request_championship(monkeypatch):
    monkeypatch.setattr(recap, "get_race_results_async", AsyncMock(return_value=pd.DataFrame()))
    loader = AsyncMock(side_effect=AssertionError("must not load standings"))
    monkeypatch.setattr(recap, "get_driver_standings_async", loader)
    result = await recap.get_race_recap.__wrapped__(2025, 1)
    assert result["status"] == "waiting"
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_and_partial_recap_have_consistent_scope(monkeypatch):
    monkeypatch.setattr(recap, "driver_season_finishes", AsyncMock(return_value=[]))
    monkeypatch.setattr(recap, "get_race_results_async", AsyncMock(return_value=pd.DataFrame(race_rows())))
    monkeypatch.setattr(recap, "get_driver_standings_async", AsyncMock(return_value=pd.DataFrame([driver("a", 1, 100), driver("b", 2, 80)])))
    monkeypatch.setattr(recap, "get_constructor_standings_async", AsyncMock(return_value=pd.DataFrame([team("one", 1, 100), team("two", 2, 80)])))
    result = await recap.get_race_recap.__wrapped__(2025, 2)
    assert result["status"] == "ready"
    assert "включая спринт" in result["note"]
    monkeypatch.setattr(recap, "get_constructor_standings_async", AsyncMock(side_effect=RuntimeError("429")))
    result = await recap.get_race_recap.__wrapped__(2025, 2)
    assert result["status"] == "partial"
    assert not any(item["category"].startswith("constructors") for item in result["items"])


def test_history_preserves_fractional_points_and_stable_identity():
    payload = {"MRData": {"StandingsTable": {"StandingsLists": [{"season": "1984", "round": "16", "DriverStandings": [
        {"position": "1", "points": "72.5", "wins": "5", "Driver": {"driverId": "lauda", "givenName": "Niki", "familyName": "Lauda"}, "Constructors": [{"name": "McLaren"}]}]}]}}}
    result = history.parse_standings(payload, "drivers", 1984)
    assert result[0]["points"] == 72.5 and result[0]["id"] == "lauda"
    with pytest.raises(ValueError):
        history.parse_standings(payload, "drivers", 1985)


@pytest.mark.asyncio
async def test_history_distinguishes_absence_and_source_failure(monkeypatch):
    async def loader(kind, season):
        if season == 2007:
            raise RuntimeError("429")
        return [{"id": "alonso", "name": "Fernando Alonso", "position": 2, "points": 100, "wins": 3, "round": 18, "teams": []}]
    monkeypatch.setattr(history, "load_history_year", loader)
    monkeypatch.setattr(history.asyncio, "sleep", AsyncMock())
    result = await history.get_standings_history("drivers", ["alonso", "hamilton"], 2006, 2007)
    assert result["series"][1]["seasons"][0]["standing"] is None
    assert result["series"][1]["seasons"][0]["status"] == "available"
    assert result["series"][0]["seasons"][1]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_history_endpoint_validates_range_and_identifiers(monkeypatch):
    from app.api import f1_insights_api
    loader = AsyncMock(return_value={"series": []})
    monkeypatch.setattr(f1_insights_api, "get_standings_history", loader)
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for query in ["kind=drivers&ids=a&start_year=1950&end_year=2025", "kind=constructors&ids=a&start_year=1950&end_year=1955", "kind=drivers&ids=../x&start_year=2020&end_year=2025", "kind=drivers&ids=a,b,c,d&start_year=2020&end_year=2025"]:
            assert (await client.get("/api/standings-history?" + query)).status_code == 422
        assert (await client.get("/api/standings-history?kind=drivers&ids=alonso&start_year=2020&end_year=2025")).status_code == 200
    loader.assert_awaited_once()


def test_guides_source_linked_not_mutable_and_unknown_not_fabricated():
    assert len(GUIDES) == 22
    for guide in GUIDES.values():
        assert guide["source"].startswith("https://www.formula1.com/en/drivers/")
        assert guide["intro"] and guide["watch"] and guide["checked_at"]
    guide = get_driver_guide("perez")
    guide["intro"] = "changed"
    assert get_driver_guide("perez")["intro"] != "changed"
    assert get_driver_guide("unknown") is None


def test_history_retains_unranked_driver_without_inventing_position():
    payload = {"MRData": {"StandingsTable": {"StandingsLists": [{"season": "1984", "round": "16", "DriverStandings": [
        {"positionText": "-", "points": "0", "wins": "0", "Driver": {"driverId": "berger", "givenName": "Gerhard", "familyName": "Berger"}}]}]}}}
    row = history.parse_standings(payload, "drivers", 1984)[0]
    assert row["position"] is None and row["position_text"] == "-"
    assert row["points"] == 0


def test_first_podium_describes_season_not_career():
    result = recap.build_recap(race_rows(), [], [], [], [], first_podiums=["C"])
    story = next(item for item in result if item["category"] == "first_podium_C")
    assert "сезона" in story["title"] and "этого сезона" in story["text"]
    assert "карьере" not in story["title"]


@pytest.mark.asyncio
async def test_stale_driver_history_cannot_prove_first_podium(monkeypatch):
    monkeypatch.setattr(recap, "get_race_results_async", AsyncMock(return_value=pd.DataFrame(race_rows())))
    monkeypatch.setattr(recap, "get_driver_standings_async", AsyncMock(return_value=pd.DataFrame([driver("a", 1, 100), driver("b", 2, 80), driver("c", 3, 70)])))
    monkeypatch.setattr(recap, "get_constructor_standings_async", AsyncMock(return_value=pd.DataFrame()))
    monkeypatch.setattr(recap, "driver_season_finishes", AsyncMock(return_value=[{"round": 1, "position": 4, "id": "a"}]))
    result = await recap.get_race_recap.__wrapped__(2025, 2)
    assert not any(item["category"].startswith("first_podium") for item in result["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", ["get_driver_standings_async", "get_constructor_standings_async"])
async def test_historical_failure_never_returns_modern_zero_roster(monkeypatch, loader):
    from app import f1_data
    class Unavailable:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            raise RuntimeError("unavailable")
    monkeypatch.setattr(f1_data, "_profile_http_session", Unavailable)
    monkeypatch.setattr(f1_data, "_run_sync", AsyncMock(return_value=pd.DataFrame()))
    zero = AsyncMock(side_effect=AssertionError("must not substitute another season"))
    monkeypatch.setattr(f1_data, "_get_zero_point_driver_standings", zero)
    monkeypatch.setattr(f1_data, "_get_zero_point_constructor_standings", zero)
    result = await getattr(f1_data, loader).__wrapped__(1984)
    assert result.empty
    zero.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("loader,identifier", [("_fetch_driver_career_results", "alonso"), ("_fetch_constructor_career_results", "ferrari")])
async def test_career_pagination_does_not_skip_records(monkeypatch, loader, identifier):
    from app import f1_data
    urls = []
    async def fetch(session, url):
        urls.append(url)
        offset = int(url.rsplit("offset=", 1)[1])
        # Simulate a provider enforcing a smaller page than requested.
        races = [{"season": "2001", "Results": [{"position": "5", "points": "2"}]}] if offset < 3 else []
        return {"MRData": {"total": "3", "RaceTable": {"Races": races}}}
    monkeypatch.setattr(f1_data, "_fetch_json", fetch)
    monkeypatch.setattr(f1_data, "_ERGAST_BASES", ["https://test"])
    result = await getattr(f1_data, loader)(None, identifier)
    assert len(result) == 3
    assert [int(url.rsplit("offset=", 1)[1]) for url in urls] == [0, 1, 2]
    assert all("limit=100&" in url for url in urls)
