from unittest.mock import AsyncMock

import httpx
import pandas as pd
import pytest

from app.api import miniapp_api as api
from app.db import Database
from app.services import prediction_service as predictions
from app.services import prediction_social as social


@pytest.mark.asyncio
async def test_comparison_uses_championship_totals_and_keeps_official_zero(monkeypatch):
    monkeypatch.setattr(api, "get_season_schedule_short_async", AsyncMock(return_value=[{"round": 1, "event_name": "Test"}]))
    monkeypatch.setattr(api, "_get_passed_races", lambda schedule, now: schedule)
    monkeypatch.setattr(api, "get_race_results_async", AsyncMock(return_value=pd.DataFrame([
        {"Abbreviation": "ANT", "Points": 25, "Position": 1},
        {"Abbreviation": "RUS", "Points": 0, "Position": 10},
    ])))
    monkeypatch.setattr(api, "get_quali_for_round_async", AsyncMock(return_value=[]))
    standings = AsyncMock(return_value=pd.DataFrame([{"driverCode": "ANT", "points": 292}, {"driverCode": "RUS", "points": 211}]))
    monkeypatch.setattr(api, "get_driver_standings_async", standings)
    result = await api._build_driver_comparison(["ANT", "RUS"], 2026)
    assert [r["total_points"] for r in result["series"]] == [292, 211]
    assert result["series"][1]["history"] == [0]
    standings.assert_awaited_once_with(2026, None)
    standings.return_value = pd.DataFrame()
    assert "error" in await api._build_driver_comparison(["ANT"], 2026)


@pytest.mark.asyncio
async def test_team_totals_same_source_as_home(monkeypatch):
    monkeypatch.setattr(api, "get_season_schedule_short_async", AsyncMock(return_value=[{"round": 1}]))
    monkeypatch.setattr(api, "_get_passed_races", lambda schedule, now: schedule)
    monkeypatch.setattr(api, "get_race_results_async", AsyncMock(return_value=pd.DataFrame([{"TeamName": "Mercedes", "Points": 0, "Position": 1}])) )
    monkeypatch.setattr(api, "get_constructor_standings_async", AsyncMock(return_value=pd.DataFrame([{"constructorName": "Mercedes", "points": 503}])))
    result = await api._build_team_comparison(["Mercedes"], 2026)
    assert result["series"][0]["total_points"] == 503
    assert result["series"][0]["history"] == [0]


@pytest.mark.asyncio
async def test_public_preview_does_not_load_any_private_data(monkeypatch):
    monkeypatch.setattr(api, "get_prediction_context", AsyncMock(return_value={"status": "ok", "season": 2026, "round": 15}))
    monkeypatch.setattr(api, "get_prediction_drivers", AsyncMock(return_value=[{"code": "ANT"}]))
    private = AsyncMock(side_effect=AssertionError("Private data accessed"))
    monkeypatch.setattr(api, "get_user_prediction", private)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.web_app), base_url="http://test") as client:
        response = await client.get('/api/predictions/preview')
        assert response.status_code == 200
        assert response.json()["prediction"] is None
        assert (await client.post('/api/predictions/leagues', json={"name": "Test"})).status_code == 401
    private.assert_not_awaited()


@pytest.mark.asyncio
async def test_leagues_access_invites_and_idempotent_migration(temp_db_path, monkeypatch):
    db = Database(temp_db_path)
    await db.connect()
    try:
        await db.init_tables()
        await db.init_tables()
        monkeypatch.setattr(predictions, "db", db)
        await db.conn.executemany("INSERT INTO users(id,telegram_id) VALUES(?,?)", [(1, 10001), (2, 10002), (3, 10003)])
        await db.conn.executemany("INSERT INTO prediction_profiles(user_id,display_name) VALUES(?,?)", [(1, "One"), (2, "Two"), (3, "Three")])
        await db.conn.commit()
        league = await social.create_league(1, "Friends")
        listing = await social.list_leagues(1)
        token = listing[0]["invite_token"]
        assert len(token) >= 40
        assert await social.list_leagues(2) == []
        with pytest.raises(PermissionError):
            await social.league_scores(2, league["id"])
        await social.join_league(2, token)
        await social.join_league(2, token)
        assert (await social.list_leagues(2))[0]["invite_token"] is None
        board = {"season": 2026, "rounds": [], "entries": [{"user_id": i, "display_name": str(i), "total_points": 0, "history": []} for i in (1, 2, 3)]}
        monkeypatch.setattr(predictions, "get_prediction_leaderboard", AsyncMock(return_value=board))
        result = await social.league_scores(2, league["id"])
        assert [e["user_id"] for e in result["entries"]] == [1, 2]
        assert len(board["entries"]) == 3  # A private view must not mutate the shared board.
        with pytest.raises(PermissionError):
            await social.manage_league(2, league["id"], "rotate")
        await social.manage_league(1, league["id"], "rotate")
        with pytest.raises(ValueError):
            await social.join_league(3, token)
        await social.manage_league(2, league["id"], "leave")
        with pytest.raises(PermissionError):
            await social.league_scores(2, league["id"])
        api.web_app.dependency_overrides[api.get_prediction_user_id] = lambda: 3
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.web_app), base_url="http://test") as client:
            assert (await client.get(f'/api/predictions/leagues/{league["id"]}?user_id=1')).status_code == 403
    finally:
        api.web_app.dependency_overrides.pop(api.get_prediction_user_id, None)
        await db.close()


def test_previous_ranking_ignores_future_scores():
    entries = [{"user_id": 1, "display_name": "A", "history": [{"round": 1, "points": 5}, {"round": 2, "points": 30}]},
               {"user_id": 2, "display_name": "B", "history": [{"round": 1, "points": 10}]}]
    assert social.previous_places(entries, 2) == {2: 1, 1: 2}


def test_race_results_preserve_official_zero_and_missing_grid():
    result, _ = api._build_race_results(pd.DataFrame([
        {"Abbreviation": "ANT", "Points": 0, "Position": 1, "GridPosition": 0},
    ]), set(), set())
    assert result[0]["points"] == 0
    assert result[0]["grid_position"] is None


@pytest.mark.asyncio
async def test_league_survives_identity_merge_and_account_deletion(temp_db_path, monkeypatch):
    from app.services.account_link_service import AccountLinkService
    db = Database(temp_db_path)
    await db.connect()
    try:
        await db.init_tables()
        monkeypatch.setattr(predictions, "db", db)
        await db.conn.executemany("INSERT INTO users(id,telegram_id) VALUES(?,?)", [(1, 10001), (2, 10002)])
        await db.conn.executemany("INSERT INTO prediction_profiles(user_id,display_name) VALUES(?,?)", [(1, "One"), (2, "Two")])
        await db.conn.commit()
        league = await social.create_league(1, "Friends")
        token = (await social.list_leagues(1))[0]['invite_token']
        await social.join_league(2, token)
        await AccountLinkService._transfer_related_data(db.conn, 1, 2)
        await db.conn.execute("DELETE FROM users WHERE id=1")
        await db.conn.commit()
        listing = await social.list_leagues(2)
        assert listing[0]['id'] == league['id']
        assert listing[0]['owner']
        assert (await (await db.conn.execute("SELECT COUNT(*) FROM prediction_league_members")).fetchone())[0] == 1
        await db.conn.execute("DELETE FROM users WHERE id=2")
        await db.conn.commit()
        assert (await (await db.conn.execute("SELECT COUNT(*) FROM prediction_leagues")).fetchone())[0] == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_personal_season_excludes_unknown_and_uses_authenticated_identity(temp_db_path, monkeypatch):
    db = Database(temp_db_path)
    await db.connect()
    try:
        await db.init_tables()
        monkeypatch.setattr(predictions, "db", db)
        history = [{"season": 2026, "round": 1, "points": 5, "max_points": 20},
                   {"season": 2026, "round": 2, "points": 15, "max_points": 20}]
        own = {"user_id": 1, "display_name": "One", "total_points": 20, "place": 1,
               "best_points": 15, "average_points": 10, "history": history}
        monkeypatch.setattr(predictions, "get_prediction_leaderboard", AsyncMock(return_value={
            "season": 2026, "rounds": [{"round": 1}, {"round": 2}], "entries": [own]}))
        reviews = AsyncMock(side_effect=lambda uid, season, rnd: {
            **history[rnd - 1], "items": [
                {"key": "winner_driver", "label": "Победитель", "status": "exact" if rnd == 2 else "miss"},
                {"key": "safety_car", "label": "SC", "status": "unavailable"},
            ]})
        monkeypatch.setattr(predictions, "get_personal_prediction_review", reviews)
        api.web_app.dependency_overrides[api.get_prediction_user_id] = lambda: 1
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.web_app), base_url="http://test") as client:
            response = await client.get('/api/predictions/personal-season?user_id=2')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'private, no-store'
            data = response.json()
            assert data['categories'] == [{"label": "Победитель", "exact": 1, "known": 2}]
            assert data['previous_points'] == 5
            assert data['average_points'] == 10
            assert all(call.args[0] == 1 for call in reviews.await_args_list)
            api.web_app.dependency_overrides.pop(api.get_prediction_user_id)
            assert (await client.get('/api/predictions/personal-season')).status_code == 401
    finally:
        api.web_app.dependency_overrides.pop(api.get_prediction_user_id, None)
        await db.close()
