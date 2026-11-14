from app.services.standings_title import official_matches


def test_official_points_must_match_every_entrant():
    entries = [{'driverCode': 'AAA', 'points': 300}, {'driverCode': 'BBB', 'points': 200}]
    page = '<table><tbody><tr><td>1</td><td>First AAA</td><td>300</td></tr><tr><td>2</td><td>Second BBB</td><td>200</td></tr></tbody></table>'
    assert official_matches(page, entries, 'drivers')
    assert not official_matches(page.replace('200', '201'), entries, 'drivers')
    assert not official_matches(page, entries[:1], 'drivers')
    assert not official_matches('', entries, 'drivers')


def test_official_team_names_and_duplicate_matches():
    page = '<table><tbody><tr><td>1</td><td>McLaren</td><td>500</td></tr><tr><td>2</td><td>Ferrari</td><td>400</td></tr></tbody></table>'
    assert official_matches(page, [{'constructorName': 'McLaren', 'points': 500}, {'constructorName': 'Ferrari', 'points': 400}], 'constructors')
    assert not official_matches(page, [{'constructorName': 'McLaren', 'points': 500}]*2, 'constructors')


import pytest
import pandas as pd
from unittest.mock import AsyncMock
from app.services import standings_title as service


@pytest.mark.asyncio
async def test_title_requires_official_agreement_and_same_round(monkeypatch):
    frame = pd.DataFrame([{'driverCode': 'AAA', 'givenName': 'A', 'familyName': 'One', 'points': 100, 'wins': 4}, {'driverCode': 'BBB', 'givenName': 'B', 'familyName': 'Two', 'points': 10, 'wins': 0}])
    frame.attrs['round'] = 2
    monkeypatch.setattr(service, 'get_driver_standings_async', AsyncMock(return_value=frame))
    monkeypatch.setattr(service, 'get_season_schedule_short_async', AsyncMock(return_value=[{'round': 1}, {'round': 2}, {'round': 3}]))
    monkeypatch.setattr(service, '_load_finishes', AsyncMock())
    monkeypatch.setattr(service, '_formula1_get_text', AsyncMock(return_value='<table><tbody><tr><td>1</td><td>AAA</td><td>100</td></tr><tr><td>2</td><td>BBB</td><td>10</td></tr></tbody></table>'))
    call = service.standings_title.__wrapped__
    assert (await call(2026, 2, 'drivers'))['status'] == 'secured'
    monkeypatch.setattr(service, '_formula1_get_text', AsyncMock(return_value=''))
    assert (await call(2026, 2, 'drivers'))['status'] == 'unavailable'
    frame.attrs['round'] = 1
    assert (await call(2026, 2, 'drivers'))['status'] == 'unavailable'


@pytest.mark.asyncio
async def test_missing_calendar_and_unknown_rules_do_not_award_titles(monkeypatch):
    monkeypatch.setattr(service, 'get_season_schedule_short_async', AsyncMock(return_value=[]))
    assert (await service.standings_title.__wrapped__(2026, 2, 'drivers'))['status'] == 'unavailable'
    assert (await service.standings_title.__wrapped__(2024, 2, 'drivers'))['status'] == 'unavailable'
