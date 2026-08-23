"""
Тесты функций f1_data.
"""
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastf1.exceptions import DataNotLoadedError

from app.f1_data import (
    _extract_team_principal_from_html,
    _fill_drivers_headshots,
    _openf1_get_drivers_for_session,
    _parse_formula1_practice_table,
    _shorten_wiki_bio,
    formula1_get_practice_for_round,
    get_driver_details_async,
    get_practice_results,
    get_practice_results_async,
    get_season_schedule_short,
    get_sprint_quali_results_async,
    openf1_get_practice_for_round,
    sort_standings_zero_last,
)


@pytest.mark.asyncio
async def test_openf1_driver_lookup_fills_session_placeholders_from_meeting():
    """Временный пустой /drivers для сессии не должен превращать всех пилотов в '?'."""
    with patch("app.f1_data._openf1_get", new_callable=AsyncMock) as request:
        request.side_effect = [
            [{"driver_number": 1, "name_acronym": "", "full_name": ""}],
            [{"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"}],
            [],
        ]
        drivers = await _openf1_get_drivers_for_session(9001, meeting_key=42)

    assert drivers[1] == {"code": "VER", "name": "Max Verstappen"}
    assert request.await_args_list[1].kwargs == {"meeting_key": 42}


def test_shorten_wiki_bio_keeps_complete_sentences():
    text = "Первый факт. Второй факт. Третий факт. Четвертый факт. Пятый факт."
    assert _shorten_wiki_bio(text, max_chars=200, max_sentences=3) == (
        "Первый факт. Второй факт. Третий факт."
    )


def test_shorten_wiki_bio_removes_disambiguation_notice():
    text = (
        "Эта общая статья о выступлениях Mercedes. О старой команде см. другую статью. "
        "Mercedes участвует в Формуле-1 как заводская команда и поставщик двигателей."
    )
    assert _shorten_wiki_bio(text) == (
        "Mercedes участвует в Формуле-1 как заводская команда и поставщик двигателей."
    )


def test_extract_team_principal_from_infobox():
    parsed_html = """
      <table class="infobox vcard">
        <tr><th>Team principal(s)</th><td><a href="/wiki/Toto_Wolff">Toto Wolff</a></td></tr>
      </table>
    """
    assert _extract_team_principal_from_html(parsed_html) == {
        "name": "Toto Wolff",
        "page_title": "Toto_Wolff",
    }


def test_extract_team_principal_ignores_missing_infobox_row():
    assert _extract_team_principal_from_html("<table><tr><td>No principal</td></tr></table>") == {}


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


def test_get_season_schedule_short_marks_cancelled_event():
    """Если EventFormat содержит cancelled/canceled, этап помечается is_cancelled=True."""
    df = pd.DataFrame([
        {
            "RoundNumber": 3,
            "EventName": "Emilia Romagna Grand Prix",
            "OfficialEventName": "FORMULA 1 GRAN PREMIO DELL'EMILIA ROMAGNA 2026",
            "Country": "Italy",
            "Location": "Imola",
            "EventDate": pd.Timestamp("2026-05-17"),
            "EventFormat": "cancelled",
            "Session1": "Practice 1",
            "Session1DateUtc": pd.Timestamp("2026-05-15T11:30:00Z"),
            "Session2": "Qualifying",
            "Session2DateUtc": pd.Timestamp("2026-05-16T14:00:00Z"),
            "Session3": "Race",
            "Session3DateUtc": pd.Timestamp("2026-05-17T13:00:00Z"),
        }
    ])
    with patch("app.f1_data.fastf1.get_event_schedule") as sched_mock:
        sched_mock.return_value = df
        schedule = get_season_schedule_short(2026)

    assert len(schedule) == 1
    assert schedule[0]["round"] == 3
    assert schedule[0]["is_cancelled"] is True


def test_get_practice_results_returns_empty_when_laps_were_not_loaded():
    """Неполная сессия FastF1 не должна превращаться в HTTP 500."""

    class IncompleteSession:
        def load(self, **_kwargs):
            return None

        @property
        def laps(self):
            raise DataNotLoadedError("laps are unavailable")

    with patch("app.f1_data.fastf1.get_session", return_value=IncompleteSession()):
        results = get_practice_results(2026, 11, 1)

    assert results == []


def test_get_practice_results_includes_fastest_lap_sector_times():
    """FastF1-сектора быстрейшего круга безопасно попадают в API-классификацию."""

    class PracticeSession:
        def __init__(self):
            self.laps = pd.DataFrame([
                {
                    "Driver": "NOR",
                    "Team": "McLaren",
                    "LapTime": pd.Timedelta(minutes=1, seconds=30),
                    "Sector1Time": pd.Timedelta(seconds=29),
                    "Sector2Time": pd.Timedelta(seconds=31),
                    "Sector3Time": pd.Timedelta(seconds=30),
                },
                {
                    "Driver": "NOR",
                    "Team": "McLaren",
                    "LapTime": pd.Timedelta(minutes=1, seconds=31),
                    "Sector1Time": pd.Timedelta(seconds=30),
                    "Sector2Time": pd.Timedelta(seconds=31),
                    "Sector3Time": pd.Timedelta(seconds=30),
                },
            ])
            self.results = pd.DataFrame([
                {
                    "Abbreviation": "NOR",
                    "FirstName": "Lando",
                    "LastName": "Norris",
                    "TeamName": "McLaren",
                },
            ])

        def load(self, **_kwargs):
            return None

    with patch("app.f1_data.fastf1.get_session", return_value=PracticeSession()):
        results = get_practice_results(2026, 4, 1)

    assert results[0]["sector1"] == "0:29.000"
    assert results[0]["sector2"] == "0:31.000"
    assert results[0]["sector3"] == "0:30.000"


@pytest.mark.asyncio
async def test_openf1_practice_results_include_classification_details():
    """OpenF1 fallback builds the same practice payload as the FastF1 provider."""
    schedule = [{
        "round": 12,
        "date": "2026-08-23",
        "location": "Zandvoort",
        "practice1_start_utc": "2026-08-21T10:30:00+00:00",
    }]
    sessions = [{
        "session_key": 11343,
        "session_type": "Practice",
        "session_name": "Practice 1",
        "date_start": "2026-08-21T10:30:00+00:00",
        "location": "Zandvoort",
    }]
    laps = [
        {
            "driver_number": 4,
            "lap_number": 1,
            "lap_duration": 72.5,
            "duration_sector_1": 23.1,
            "duration_sector_2": 25.2,
            "duration_sector_3": 24.2,
            "is_pit_out_lap": False,
        },
        {
            "driver_number": 63,
            "lap_number": 1,
            "lap_duration": 73.0,
            "duration_sector_1": 23.2,
            "duration_sector_2": 25.3,
            "duration_sector_3": 24.5,
            "is_pit_out_lap": False,
        },
    ]
    drivers = [
        {"driver_number": 4, "name_acronym": "NOR", "full_name": "Lando Norris", "team_name": "McLaren"},
        {"driver_number": 63, "name_acronym": "RUS", "full_name": "George Russell", "team_name": "Mercedes"},
    ]

    with patch("app.f1_data.get_season_schedule_short_async", new_callable=AsyncMock, return_value=schedule), \
            patch("app.f1_data._openf1_get", new_callable=AsyncMock) as request:
        request.side_effect = [sessions, laps, drivers]
        results = await openf1_get_practice_for_round(2026, 12, 1)

    assert [row["driver"] for row in results] == ["NOR", "RUS"]
    assert results[0] == {
        "position": 1,
        "driver": "NOR",
        "name": "Lando Norris",
        "team": "McLaren",
        "best": "1:12.500",
        "gap": "1:12.500",
        "laps": 1,
        "sector1": "0:23.100",
        "sector2": "0:25.200",
        "sector3": "0:24.200",
    }
    assert results[1]["gap"] == "+0.500"


@pytest.mark.asyncio
async def test_practice_results_async_prefers_openf1_and_skips_fastf1():
    """A populated OpenF1 response avoids the slower FastF1 fallback."""
    openf1_rows = [{"position": 1, "driver": "NOR"}]
    with patch(
        "app.f1_data.openf1_get_practice_for_round",
        new_callable=AsyncMock,
        return_value=openf1_rows,
    ), patch("app.f1_data._run_sync", new_callable=AsyncMock) as run_sync:
        results = await get_practice_results_async.__wrapped__(2026, 12, 1)

    assert results == openf1_rows
    run_sync.assert_not_awaited()


def test_formula1_practice_parser_builds_shared_result_shape():
    page_html = """
        <table>
          <thead><tr><th>Pos.</th><th>No.</th><th>Driver</th><th>Team</th><th>Time / Gap</th><th>Laps</th></tr></thead>
          <tbody>
            <tr><td>1</td><td>3</td><td>Max VerstappenVER</td><td>Red Bull Racing</td><td>1:47.070</td><td>24</td></tr>
            <tr><td>2</td><td>44</td><td>Lewis HamiltonHAM</td><td>Ferrari</td><td>+0.145s</td><td>22</td></tr>
          </tbody>
        </table>
    """

    results = _parse_formula1_practice_table(page_html)

    assert results == [
        {
            "position": 1,
            "driver": "VER",
            "name": "Max Verstappen",
            "team": "Red Bull Racing",
            "best": "1:47.070",
            "gap": "—",
            "laps": 24,
            "sector1": "—",
            "sector2": "—",
            "sector3": "—",
        },
        {
            "position": 2,
            "driver": "HAM",
            "name": "Lewis Hamilton",
            "team": "Ferrari",
            "best": "—",
            "gap": "+0.145s",
            "laps": 22,
            "sector1": "—",
            "sector2": "—",
            "sector3": "—",
        },
    ]


@pytest.mark.asyncio
async def test_formula1_practice_fallback_uses_calendar_round_link():
    index_html = """
        <a href="/en/results/2026/races/1001/australia/race-result">Australia</a>
        <a href="/en/results/2026/races/1002/china/race-result">China</a>
    """
    results_html = """
        <table><thead><tr><th>Pos.</th><th>No.</th><th>Driver</th><th>Team</th><th>Time / Gap</th><th>Laps</th></tr></thead>
        <tbody><tr><td>1</td><td>12</td><td>Kimi AntonelliANT</td><td>Mercedes</td><td>1:31.001</td><td>20</td></tr></tbody></table>
    """
    with patch("app.f1_data._formula1_get_text", new_callable=AsyncMock) as request:
        request.side_effect = [index_html, results_html]

        results = await formula1_get_practice_for_round(2026, 2, 1)

    assert results[0]["driver"] == "ANT"
    assert request.await_args_list[1].args[0].endswith("/1002/china/practice/1")
