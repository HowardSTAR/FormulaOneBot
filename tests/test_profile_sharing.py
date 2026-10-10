import io
import json
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.db import db
from app.api.engagement_api import optional_account
from app.api.miniapp_api import web_app
from app.services import engagement


@pytest.mark.asyncio
async def test_share_profile_curates_server_data_and_opens_for_guest(api_client, monkeypatch):
    monkeypatch.setattr(engagement, 'bot_username', AsyncMock(return_value=None))
    user_id = (await (await db.conn.execute('SELECT id FROM users WHERE telegram_id=999888')).fetchone())[0]
    web_app.dependency_overrides[optional_account] = lambda: user_id
    await db.conn.execute("INSERT INTO prediction_profiles(user_id,display_name) VALUES (?,'Turbo Racer')", (user_id,))
    for round_num, points, driver in [(1, 27, 'VER'), (2, None, 'SECRET')]:
        await db.conn.execute('''INSERT INTO race_predictions(user_id,season,round,pole_driver,
            winner_driver,second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
            first_retirement_driver,safety_car,points,max_points) VALUES (?,2026,?,?,?,'NOR','PIA','LEC','HAM','VER','SAI',1,?,40)''',
            (user_id, round_num, driver, driver, points))
    await db.conn.execute("INSERT INTO reaction_leaderboard_profiles(telegram_id,display_name,leaderboard_opt_in,prompt_seen) VALUES (999888,'Turbo Racer',1,1)")
    await db.conn.execute("INSERT INTO race_game_scores(telegram_id,time_ms,track_id) VALUES (999888,98432,'emerald-loop-v2')")
    await db.conn.commit()
    response = await api_client.post('/api/engagement/shares', json={'kind':'profile','season':2026,'consent':True,'total_points':9999,'profile_style':{'color':'gold'}})
    assert response.status_code == 200, response.text
    card = response.json()
    assert card['total_points'] == card['best_points'] == 27
    assert card['profile_style']['color'] == 'white'
    assert card['records'][0] == {'name':'Emerald Loop','time':'01:38.432'}
    assert not {'email','telegram_id','user_id','owner_id','predictions'} & card.keys()
    assert 'SECRET' not in json.dumps(card)
    image = await api_client.get(f"/api/engagement/shares/{card['token']}/image.jpg")
    assert image.status_code == 200 and Image.open(io.BytesIO(image.content)).size == (1200,630)
    html = (await api_client.get(f"/share/{card['token']}")).text
    assert 'og:image' in html and 'Профиль Turbo Racer' in html
    destination = (await api_client.get(f"/api/engagement/shares/{card['token']}/destination")).json()['path']
    assert destination.startswith(f'/profile/{user_id}?season=2026&via=')
    web_app.dependency_overrides[optional_account] = lambda: None
    public = await api_client.get(f'/api/profiles/{user_id}?season=2026')
    assert public.status_code == 200
    assert public.json()['is_owner'] is False and len(public.json()['predictions']) == 1
    assert (await api_client.post('/api/engagement/shares',json={'kind':'profile','consent':True})).status_code == 401
    await db.conn.execute('UPDATE reaction_leaderboard_profiles SET leaderboard_opt_in=0 WHERE telegram_id=999888')
    await db.conn.commit()
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}/image.jpg")).status_code == 404


@pytest.mark.asyncio
async def test_empty_profile_share_revocation_and_archive(api_client, monkeypatch):
    monkeypatch.setattr(engagement, 'bot_username', AsyncMock(return_value=None))
    user_id = (await (await db.conn.execute('SELECT id FROM users WHERE telegram_id=999888')).fetchone())[0]
    web_app.dependency_overrides[optional_account] = lambda: user_id
    create = lambda: api_client.post('/api/engagement/shares',json={'kind':'profile','consent':True})
    card = (await create()).json()
    assert card['best_points'] is None and card['records'] == []
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}/image.jpg")).status_code == 200
    assert (await api_client.post(f"/api/engagement/shares/{card['token']}/revoke")).status_code == 200
    assert (await api_client.get(f"/share/{card['token']}")).status_code == 404
    card = (await create()).json()
    await db.conn.execute('UPDATE users SET archived_at=CURRENT_TIMESTAMP WHERE id=?', (user_id,))
    await db.conn.commit()
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}")).status_code == 404
