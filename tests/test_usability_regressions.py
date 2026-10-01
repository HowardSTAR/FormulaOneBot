from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app import f1_data
from app.services import web_notifications


@pytest.mark.asyncio
@pytest.mark.parametrize('points, expected, source', [(378, 378, 'standings'), (0, 0, 'standings'), (None, 330, 'grand_prix')])
async def test_constructor_profile_uses_standings_points_not_gp_only(points, expected, source):
    standings = pd.DataFrame([{'constructorId': 'ferrari', 'position': 2, 'points': points}])
    standings.attrs['round'] = 15
    rows = [{'season': '2026', 'round': '15', 'points': 200, 'position': '2', 'grid': '2'},
            {'season': '2026', 'round': '15', 'points': 130, 'position': '3', 'grid': '3'}]
    with patch.object(f1_data, '_try_bases', AsyncMock(return_value={'MRData': {'ConstructorTable': {'Constructors': [{'constructorId': 'ferrari', 'name': 'Ferrari'}]}}})), \
         patch.object(f1_data, '_fetch_constructor_season_results', AsyncMock(return_value=(rows, 1))), \
         patch.object(f1_data, '_fetch_constructor_career_results', AsyncMock(return_value=rows)), \
         patch.object(f1_data, '_fetch_constructor_drivers', AsyncMock(return_value=[])), \
         patch.object(f1_data, '_fetch_wiki_bio', AsyncMock(return_value='')), \
         patch.object(f1_data, '_fetch_team_principal', AsyncMock(return_value=None)), \
         patch.object(f1_data, '_fill_drivers_headshots', AsyncMock(return_value=[])), \
         patch.object(f1_data, 'get_constructor_standings_async', AsyncMock(return_value=standings)), \
         patch.object(f1_data, '_count_constructor_championships', AsyncMock(return_value=16)):
        result = await f1_data.get_constructor_details_async.__wrapped__('ferrari', 2026)
    assert result['season_stats']['points'] == expected
    assert result['season_stats']['points_source'] == source
    assert result['season_stats']['grand_prix_points'] == 330
    assert result['season_stats']['standings_round'] == 15
    assert result['career_stats']['grand_prix_entered'] == 2  # Car entries, legacy API preserved.
    assert result['career_stats']['grand_prix_events'] == 1


@pytest.mark.asyncio
async def test_classification_preserves_real_zero_but_not_missing_or_provisional_points():
    rows = [{'position': 1, 'name': 'A', 'points': 0, 'data_complete': False},
            {'position': 2, 'name': 'B', 'points': None},
            {'position': 3, 'name': 'C', 'points': 0}]
    with patch.object(web_notifications, 'publish_safely', AsyncMock()) as publish:
        await web_notifications.classification(2026, 15, 'Race', 'race-results', rows)
    body = publish.await_args.args[2].splitlines()
    assert body[0].endswith(' · —')
    assert body[1].endswith(' · —')
    assert body[2].endswith(' · 0')
    assert publish.await_args.kwargs['rows'] == rows


@pytest.mark.asyncio
async def test_constructor_career_keeps_rounds_to_count_events_not_cars():
    payload = {'MRData': {'total': '2', 'RaceTable': {'Races': [
        {'season': '2026', 'round': '15', 'Results': [
            {'position': '2', 'points': '18', 'grid': '2'},
            {'position': '3', 'points': '15', 'grid': '3'}]},
    ]}}}
    with patch.object(f1_data, '_fetch_json', AsyncMock(return_value=payload)):
        rows = await f1_data._fetch_constructor_career_results(None, 'ferrari')
    assert len(rows) == 2
    assert {(row['season'], row['round']) for row in rows} == {('2026', '15')}
