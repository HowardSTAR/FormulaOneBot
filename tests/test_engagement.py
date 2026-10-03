"""Community functionality uses isolated data and never sends real Telegram messages."""
import io
import json
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.api.engagement_api import optional_account
from app.api.miniapp_api import web_app
from app.db import db
from app.race_rules import TRACKS
from app.services import engagement, prediction_service, prediction_social


async def account():
    return (await (await db.conn.execute('SELECT id FROM users WHERE telegram_id=999888')).fetchone())[0]


async def sign_in():
    user_id = await account()
    web_app.dependency_overrides[optional_account] = lambda: user_id
    return user_id


def replay(track_id, speed=220):
    points = TRACKS[track_id]['centerLine']
    samples = [{'t': 0, 'x': points[0][0], 'y': points[0][1], 'rotation': 0}]
    time = 0
    for _ in range(3):
        for index, (x, y) in enumerate(points):
            bx, by = points[(index + 1) % len(points)]
            distance = math.hypot(bx-x, by-y)
            steps = math.ceil(distance / 20)
            for step in range(1, steps+1):
                time += math.ceil(distance / steps / speed * 1000)
                samples.append({'t': time, 'x': round(x+(bx-x)*step/steps, 2), 'y': round(y+(by-y)*step/steps, 2), 'rotation': 0})
    return {'track_id': track_id, 'time_ms': time, 'telemetry': samples}


def review(provisional=False):
    return {'event_name': 'Test Grand Prix', 'points': 29, 'max_points': 37, 'complete': not provisional,
            'items': [{'key': 'winner_driver', 'label': 'Победитель', 'status': 'exact', 'predicted': 'SECRET_PRIVATE_CHOICE', 'actual': 'RUS'},
                      {'key': 'fastest_lap_driver', 'label': 'Лучший круг', 'status': 'unavailable' if provisional else 'miss'}]}


@pytest.mark.asyncio
async def test_card_is_opt_in_curated_and_revoke_is_owner_only(api_client, monkeypatch):
    user_id = await sign_in()
    monkeypatch.setattr(prediction_service, 'get_personal_prediction_review', AsyncMock(return_value=review()))
    await prediction_service.save_prediction_profile(user_id, 'Test Pilot')
    response = await api_client.post('/api/engagement/shares', json={'kind': 'prediction', 'season': 2026, 'round': 15, 'consent': False})
    assert response.status_code == 422
    before = await (await db.conn.execute('SELECT COUNT(*) FROM race_predictions')).fetchone()
    response = await api_client.post('/api/engagement/shares', json={'kind': 'prediction', 'season': 2026, 'round': 15, 'consent': True, 'points': 999, 'user_id': 999})
    assert response.status_code == 200, response.text
    card = response.json()
    assert card['headline'] == '29 / 37 очков'
    assert not card['provisional']
    assert 'SECRET_PRIVATE_CHOICE' not in json.dumps(card)
    assert not {'owner_id', 'email', 'telegram_id', 'invite_token', 'target'} & card.keys()
    assert len(card['token']) == 32
    image = await api_client.get(f"/api/engagement/shares/{card['token']}/image.jpg")
    assert image.headers['content-type'] == 'image/jpeg'
    assert Image.open(io.BytesIO(image.content)).size == (1200, 630)
    destination = await api_client.get(f"/api/engagement/shares/{card['token']}/destination")
    assert destination.json()['path'] == f"/predictions?via={card['token']}"
    after = await (await db.conn.execute('SELECT COUNT(*) FROM race_predictions')).fetchone()
    assert before[0] == after[0]  # sharing never recalculates/saves a forecast
    html = (await api_client.get(f"/share/{card['token']}")).text
    assert 'og:image' in html and 'SECRET_PRIVATE_CHOICE' not in html
    web_app.dependency_overrides[optional_account] = lambda: None
    web_app.dependency_overrides.pop(next(key for key in web_app.dependency_overrides if key.__name__ == 'require_hybrid_user_id'))
    assert (await api_client.post(f"/api/engagement/shares/{card['token']}/revoke")).status_code == 401
    from app.api.auth_api import require_hybrid_user_id
    web_app.dependency_overrides[require_hybrid_user_id] = lambda: user_id
    assert (await api_client.post(f"/api/engagement/shares/{card['token']}/revoke")).status_code == 200
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}")).status_code == 404
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}/image.jpg")).status_code == 404


@pytest.mark.asyncio
async def test_unfinished_and_provisional_predictions_are_not_final(api_client, monkeypatch):
    await sign_in()
    monkeypatch.setattr(prediction_service, 'get_personal_prediction_review', AsyncMock(return_value=None))
    assert (await api_client.post('/api/engagement/shares', json={'kind': 'prediction', 'consent': True})).status_code == 422
    monkeypatch.setattr(prediction_service, 'get_personal_prediction_review', AsyncMock(return_value=review(True)))
    card = (await api_client.post('/api/engagement/shares', json={'kind': 'prediction', 'consent': True})).json()
    assert card['provisional'] and 'Предварительный' in card['lines'][0]
    assert not any('лучший' in line.lower() or 'место' in line.lower() for line in card['lines'])


@pytest.mark.asyncio
async def test_guest_cannot_share_private_data_and_cross_site_is_rejected(api_client):
    web_app.dependency_overrides[optional_account] = lambda: None
    assert (await api_client.post('/api/engagement/shares', json={'kind': 'prediction', 'consent': True})).status_code == 401
    assert (await api_client.post('/api/engagement/shares', json={'kind': 'recap', 'consent': True}, headers={'Sec-Fetch-Site':'cross-site'})).status_code == 403
    assert (await api_client.post('/api/engagement/shares', json={'kind': 'race', 'track_id': 'emerald-loop-v1', 'consent': True})).status_code == 422


@pytest.mark.asyncio
async def test_racing_challenge_requires_saved_record_and_matching_track(api_client):
    await sign_in()
    assert (await api_client.post('/api/engagement/shares', json={'kind':'race','track_id':'sunset-speedway-v1','consent':True})).status_code == 422
    record = replay('sunset-speedway-v1')
    assert (await api_client.post('/api/race-game-leaderboard/score', json=record)).json()['saved']
    card = (await api_client.post('/api/engagement/shares', json={'kind':'race','track_id':record['track_id'],'consent':True})).json()
    data = (await api_client.get(f"/api/engagement/challenges/{card['token']}")).json()
    assert data['track_id'] == record['track_id']
    assert data['ghost']['samples'][-1]['t'] == record['time_ms']
    faster = replay(record['track_id'], speed=230)
    response = await api_client.post('/api/race-game-leaderboard/score', json={**faster,'challenge_token':card['token']})
    assert response.json()['saved'] and response.json()['challenge']['beaten']
    wrong = await api_client.post('/api/race-game-leaderboard/score', json={**replay('harbor-sprint-v1'),'challenge_token':card['token']})
    assert wrong.json()['saved'] and 'error' in wrong.json()['challenge']
    assert len((await api_client.get(f"/api/engagement/challenges/{card['token']}")).json()['entries']) == 1
    await api_client.post('/api/reaction-leaderboard/profile', json={'display_name':'Pilot','participate':False,'prompt_seen':True})
    assert (await api_client.get(f"/api/engagement/challenges/{card['token']}")).status_code == 404


def schedule():
    now = datetime.now(timezone.utc)
    return [{'round': 15+i, 'event_name':f'Future {i}', 'practice1_start_utc':(now+timedelta(days=7*i+1)).isoformat(),
             'quali_start_utc':(now+timedelta(days=7*i+2)).isoformat(), 'race_start_utc':(now+timedelta(days=7*i+3)).isoformat()} for i in range(4)]


@pytest.mark.asyncio
async def test_cup_counts_only_selected_future_rounds_and_invite_is_revocable(api_client, monkeypatch):
    user_id = await sign_in()
    await prediction_service.save_prediction_profile(user_id,'Owner')
    monkeypatch.setattr(prediction_service,'get_season_schedule_short_async',AsyncMock(return_value=schedule()))
    created = (await api_client.post('/api/predictions/leagues',json={'name':'New start','mode':'cup'})).json()
    league = (await api_client.get('/api/predictions/leagues')).json()['leagues'][0]
    assert [r['round'] for r in league['rounds']] == [15,16,17]
    board = {'season':2026,'rounds':[{'round':14},{'round':15}], 'entries':[{'user_id':user_id,'display_name':'Owner','total_points':104,'history':[{'round':14,'points':99},{'round':15,'points':5}]}]}
    monkeypatch.setattr(prediction_service,'get_prediction_leaderboard',AsyncMock(return_value=board))
    cup = (await api_client.get(f"/api/predictions/leagues/{created['id']}")).json()
    assert cup['entries'][0]['total_points'] == 5
    assert cup['entries'][0]['rounds_scored'] == 1
    assert cup['entries'][0]['wins'] == 1
    assert [h['round'] for h in cup['entries'][0]['history']] == [15]
    assert board['entries'][0]['total_points'] == 104
    card = (await api_client.post('/api/engagement/shares',json={'kind':'league','league_id':created['id'],'consent':True})).json()
    assert 'invite_token' not in card
    assert '#invite=' in (await api_client.get(f"/api/engagement/shares/{card['token']}/destination")).json()['path']
    await api_client.post(f"/api/predictions/leagues/{created['id']}",json={'action':'rotate'})
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}")).status_code == 404
    assert not (await api_client.get('/api/engagement/mine')).json()['shares'][0]['active']


@pytest.mark.asyncio
async def test_cup_cannot_use_closed_rounds_or_less_than_three_events(api_client, monkeypatch):
    user_id = await sign_in()
    await prediction_service.save_prediction_profile(user_id,'Owner')
    monkeypatch.setattr(prediction_service,'get_season_schedule_short_async',AsyncMock(return_value=schedule()[:2]))
    assert (await api_client.post('/api/predictions/leagues',json={'name':'Too short','mode':'cup'})).status_code == 422
    assert (await api_client.get('/api/predictions/leagues')).json()['leagues'] == []


@pytest.mark.asyncio
async def test_referral_only_activates_on_real_save_and_no_self_referrals(api_client, monkeypatch):
    owner = await sign_in()
    await prediction_service.save_prediction_profile(owner,'Owner')
    monkeypatch.setattr(prediction_service,'get_personal_prediction_review',AsyncMock(return_value=review()))
    token = (await api_client.post('/api/engagement/shares',json={'kind':'prediction','consent':True})).json()['token']
    await engagement.arrival(owner, token)
    assert (await engagement.personal_engagement(owner))['referrals']['arrived'] == 0
    await db.conn.execute("INSERT INTO users(id,telegram_id) VALUES(88,8888)")
    await db.conn.commit()
    await engagement.arrival(88, token)
    await engagement.arrival(88, token)
    assert (await engagement.personal_engagement(owner))['referrals'] == {'arrived':1,'activated':0,'returned':0}
    await prediction_service.save_prediction_profile(88,'Friend')
    prediction = {k: v for k,v in zip(prediction_service.PLACEMENT_FIELDS,['RUS','NOR','LEC','HAM','ANT'])}
    prediction.update({'pole_driver':'RUS','fastest_lap_driver':'RUS','first_retirement_driver':'ALO','safety_car':False})
    await prediction_service.save_user_prediction(88,2026,16,prediction)
    assert (await engagement.personal_engagement(owner))['referrals']['activated'] == 1
    await prediction_service.save_user_prediction(88,2026,16,prediction)
    assert (await engagement.personal_engagement(owner))['referrals']['returned'] == 0
    await prediction_service.save_user_prediction(88,2026,15,prediction)
    assert (await engagement.personal_engagement(owner))['referrals']['returned'] == 0
    await prediction_service.save_user_prediction(88,2026,17,prediction)
    assert (await engagement.personal_engagement(owner))['referrals']['returned'] == 1


@pytest.mark.asyncio
async def test_weekly_ranking_does_not_reset_all_time_records(api_client):
    weekly = (await api_client.get('/api/engagement/weekly')).json()
    record = replay(weekly['track_id'])
    await api_client.post('/api/race-game-leaderboard/score',json=record)
    assert len((await api_client.get('/api/engagement/weekly')).json()['entries']) == 1
    await db.conn.execute("UPDATE race_game_scores SET created_at='2000-01-01 00:00:00'")
    await db.conn.commit()
    assert (await api_client.get('/api/engagement/weekly')).json()['entries'] == []
    assert (await api_client.get('/api/race-game-leaderboard',params={'track_id':weekly['track_id']})).json()['me']['time_ms'] == record['time_ms']


@pytest.mark.asyncio
async def test_weekly_results_links_keep_the_requested_week(api_client):
    _, current_start, _ = engagement.weekly_period()
    start = current_start-timedelta(days=14)
    result = await api_client.get('/api/engagement/weekly', params={'week': start.date().isoformat()})
    assert result.status_code == 200
    assert result.json()['start'] == start.isoformat()
    assert result.json()['end'] == (start+timedelta(days=7)).isoformat()
    previous = await api_client.get('/api/engagement/weekly?period=previous')
    assert previous.json()['end'] == current_start.isoformat()
    for week in ['broken', current_start.date().isoformat(), (start+timedelta(days=1)).date().isoformat()]:
        assert (await api_client.get('/api/engagement/weekly', params={'week': week})).status_code == 422


@pytest.mark.asyncio
async def test_public_history_and_recap_share_exact_context_without_accounts(api_client, monkeypatch):
    web_app.dependency_overrides[optional_account] = lambda: None
    from app.services import race_recap, standings_history
    monkeypatch.setattr(race_recap,'get_race_recap',AsyncMock(return_value={'status':'partial','items':[{'title':'Отрыв сократился','text':'20 → 12 очков'}]}))
    recap = (await api_client.post('/api/engagement/shares',json={'kind':'recap','season':2026,'round':15,'consent':True})).json()
    assert recap['provisional']
    assert 'season=2026&round=15&mode=archive' in (await api_client.get(f"/api/engagement/shares/{recap['token']}/destination")).json()['path']
    monkeypatch.setattr(standings_history,'get_standings_history',AsyncMock(return_value={'series':[{'name':'Fernando Alonso','seasons':[{'season':2025,'standing':{'position':10}},{'season':2026,'standing':{'position':5}}]}]}))
    history = (await api_client.post('/api/engagement/shares',json={'kind':'history','ids':['alonso'],'start_year':2025,'end_year':2026,'consent':True})).json()
    assert history['chart'][0]['values'][-1]['position'] == 5
    assert 'ids=alonso' in (await api_client.get(f"/api/engagement/shares/{history['token']}/destination")).json()['path']
    assert (await api_client.post('/api/engagement/shares',json={'kind':'history','ids':['../etc'],'consent':True})).status_code == 422


@pytest.mark.asyncio
async def test_schema_migration_repeatable_and_expired_links_stop_working(api_client, monkeypatch):
    await sign_in()
    monkeypatch.setattr(prediction_service,'get_personal_prediction_review',AsyncMock(return_value=review()))
    card = (await api_client.post('/api/engagement/shares',json={'kind':'prediction','consent':True})).json()
    await db.init_tables(); await db.init_tables()
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}")).status_code == 200
    await db.conn.execute('UPDATE engagement_shares SET expires=0')
    await db.conn.commit()
    assert (await api_client.get(f"/api/engagement/shares/{card['token']}/destination")).status_code == 404
    expired = await api_client.get(f"/share/{card['token']}")
    assert expired.status_code == 404 and 'text/html' in expired.headers['content-type']
    assert 'id="root"' in expired.text


def test_deep_link_tokens_fit_telegram_and_preserve_destination(monkeypatch):
    monkeypatch.setenv('PUBLIC_WEB_URL','https://www.f1hub.ru/')
    monkeypatch.setenv('TELEGRAM_BOT_USERNAME','test_f1hub_bot')
    urls = engagement.links('a'*32)
    assert urls['mini_app_url'] == 'https://t.me/test_f1hub_bot?startapp=share_' + 'a'*32
    assert urls['image_url'].startswith('https://www.f1hub.ru/api/')
    assert len('share_' + 'a'*32) <= 64


@pytest.mark.asyncio
async def test_social_failure_does_not_invalidate_saved_scores_or_forecasts(api_client, monkeypatch):
    user_id = await sign_in()
    await prediction_service.save_prediction_profile(user_id,'Owner')
    monkeypatch.setattr(engagement,'activate',AsyncMock(side_effect=RuntimeError('bookkeeping unavailable')))
    record = replay('sunset-speedway-v1')
    response = await api_client.post('/api/race-game-leaderboard/score',json=record)
    assert response.status_code == 200 and response.json()['saved']
    prediction = {k:v for k,v in zip(prediction_service.PLACEMENT_FIELDS,['RUS','NOR','LEC','HAM','ANT'])}
    prediction.update(pole_driver='RUS',fastest_lap_driver='RUS',first_retirement_driver='ALO',safety_car=False)
    await prediction_service.save_user_prediction(user_id,2026,16,prediction)
    assert (await prediction_service.get_user_prediction(user_id,2026,16))['winner_driver'] == 'RUS'
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM race_game_scores')).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_failed_challenge_commit_rolls_back_only_its_entry(api_client, monkeypatch):
    await sign_in()
    record = replay('sunset-speedway-v1')
    assert (await api_client.post('/api/race-game-leaderboard/score', json=record)).json()['saved']
    card = (await api_client.post('/api/engagement/shares', json={
        'kind': 'race', 'track_id': record['track_id'], 'consent': True})).json()
    faster = replay(record['track_id'], speed=230)
    assert (await api_client.post('/api/race-game-leaderboard/score', json=faster)).json()['saved']
    score_id = (await (await db.conn.execute('SELECT MAX(id) FROM race_game_scores')).fetchone())[0]
    commit = db.conn.commit
    monkeypatch.setattr(db.conn, 'commit', AsyncMock(side_effect=RuntimeError('commit unavailable')))
    with pytest.raises(RuntimeError):
        await engagement.record_challenge(card['token'], 999888, score_id)
    monkeypatch.setattr(db.conn, 'commit', commit)
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM race_challenge_entries')).fetchone())[0] == 0
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM race_game_scores')).fetchone())[0] == 2
    assert (await engagement.record_challenge(card['token'], 999888, score_id))['beaten']
    assert len((await engagement.challenge(card['token']))['entries']) == 1


@pytest.mark.asyncio
async def test_referral_game_first_then_forecast_and_return(api_client, monkeypatch):
    owner = await sign_in()
    monkeypatch.setattr(prediction_service,'get_personal_prediction_review',AsyncMock(return_value=review()))
    token = (await api_client.post('/api/engagement/shares',json={'kind':'prediction','consent':True})).json()['token']
    await db.conn.execute('INSERT INTO users(id,telegram_id) VALUES(88,8888)'); await db.conn.commit()
    await engagement.arrival(88,token)
    await engagement.activate(88,'race')
    await engagement.activate(88,'prediction',2026,16)
    assert (await engagement.personal_engagement(owner))['referrals'] == {'arrived':1,'activated':1,'returned':0}
    await engagement.activate(88,'prediction',2026,17)
    assert (await engagement.personal_engagement(owner))['referrals']['returned'] == 1


@pytest.mark.asyncio
async def test_achievements_require_another_real_participant(api_client):
    user_id = await sign_in()
    await prediction_service.save_prediction_profile(user_id,'Owner')
    league = await prediction_social.create_league(user_id,'Friends')
    assert (await engagement.personal_engagement(user_id))['badges'] == []
    await db.conn.execute('INSERT INTO users(id,telegram_id) VALUES(88,8888)')
    await db.conn.execute('INSERT INTO prediction_league_members(league_id,user_id) VALUES(?,88)',(league['id'],))
    await db.conn.commit()
    assert (await engagement.personal_engagement(user_id))['badges'] == ['Собрал первую лигу']


@pytest.mark.asyncio
async def test_share_metrics_are_deduplicated_and_aggregate_only(api_client, monkeypatch):
    await sign_in()
    monkeypatch.setattr(prediction_service,'get_personal_prediction_review',AsyncMock(return_value=review()))
    token = (await api_client.post('/api/engagement/shares',json={'kind':'prediction','consent':True})).json()['token']
    for _ in range(3):
        assert (await api_client.post('/api/engagement/event',json={'token':token,'event':'share_sent'})).status_code == 200
    from app.services.product_analytics import report
    metrics = await report(db.conn,0)
    assert metrics['sharing'] == [{'kind':'prediction','event':'share_sent','events':1,'browsers':1}]
    assert 'telegram_id' not in json.dumps(metrics) and 'user_id' not in json.dumps(metrics)
    assert (await api_client.post('/api/engagement/event',json={'token':token,'event':'activated'})).status_code == 422


class TelegramResponse:
    def __init__(self, payload): self.payload = payload
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def json(self): return self.payload


@pytest.mark.asyncio
async def test_native_card_preparation_binds_verified_recipient_and_never_sends(api_client, monkeypatch):
    await sign_in()
    monkeypatch.setattr(prediction_service,'get_personal_prediction_review',AsyncMock(return_value=review()))
    monkeypatch.setenv('PUBLIC_WEB_URL','https://www.f1hub.ru')
    monkeypatch.setenv('TELEGRAM_BOT_USERNAME','test_f1hub_bot')
    monkeypatch.setenv('BOT_TOKEN','123456:dummy-test-credential')
    requests = []
    class Session:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        def post(self, url, json):
            requests.append((url,json))
            return TelegramResponse({'ok':True,'result':{'id':'prepared-id'}})
    monkeypatch.setattr(engagement.aiohttp,'ClientSession',Session)
    token = (await api_client.post('/api/engagement/shares',json={'kind':'prediction','consent':True})).json()['token']
    response = await api_client.post(f'/api/engagement/shares/{token}/telegram',json={'user_id':1234})
    assert response.json() == {'id':'prepared-id'}
    url, body = requests[0]
    assert url.endswith('/savePreparedInlineMessage') and 'sendMessage' not in url
    assert body['user_id'] == 999888  # only the authenticated account's linked Telegram
    assert body['result']['type'] == 'photo'
    assert body['result']['photo_url'].endswith('/image.jpg')
    assert len(body['result']['caption']) <= 950
    assert body['result']['reply_markup']['inline_keyboard'][0][0]['url'] == 'https://t.me/test_f1hub_bot?startapp=share_' + token
    assert 'dummy-test-credential' not in response.text
    monkeypatch.setenv('PUBLIC_WEB_URL','http://localhost')
    assert (await api_client.post(f'/api/engagement/shares/{token}/telegram')).status_code == 503
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_bot_name_discovery_is_cached_and_local_previews_stay_offline(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_USERNAME',raising=False)
    monkeypatch.delenv('BOT_USERNAME',raising=False)
    monkeypatch.setenv('BOT_TOKEN','123456:dummy')
    monkeypatch.setenv('PUBLIC_WEB_URL','https://www.f1hub.ru')
    monkeypatch.setattr(engagement,'_username_cache',(None,None,0))
    calls = []
    class Session:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        def get(self, url):
            calls.append(url)
            return TelegramResponse({'ok':True,'result':{'username':'test_f1hub_bot'}})
    monkeypatch.setattr(engagement.aiohttp,'ClientSession',Session)
    assert await engagement.bot_username() == 'test_f1hub_bot'
    assert await engagement.bot_username() == 'test_f1hub_bot'
    assert len(calls) == 1 and calls[0].endswith('/getMe')
    monkeypatch.setenv('PUBLIC_WEB_URL','http://127.0.0.1:8181')
    assert await engagement.bot_username() is None
    assert len(calls) == 1
