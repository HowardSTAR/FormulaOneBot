"""Public interaction counting and durable, pseudonymous PostHog forwarding."""
import json
import uuid

import pytest


@pytest.mark.asyncio
async def test_ui_events_deduplicate_and_report_real_opens(api_client, monkeypatch):
    from app.db import db
    from app.services.product_analytics import report
    monkeypatch.delenv('POSTHOG_HOST', raising=False)
    monkeypatch.delenv('POSTHOG_PROJECT_KEY', raising=False)
    await api_client.post('/api/analytics/visit', json={'path': '/'})
    event = {'event':'screen_view','path':'/','action':'screen','event_id':str(uuid.uuid4())}
    for _ in range(3):
        assert (await api_client.post('/api/analytics/event',json=event)).status_code == 200
    assert (await api_client.post('/api/analytics/event',json={**event,'event_id':str(uuid.uuid4())})).status_code == 200
    click = {**event,'event':'click','action':'calendar_open','destination':'/season','event_id':str(uuid.uuid4())}
    assert (await api_client.post('/api/analytics/event',json=click)).status_code == 200
    data = await report(db.conn,0)
    assert data['screens'] == [{'path':'/','views':2,'browsers':1}]
    assert data['actions'] == [{'path':'/','action':'calendar_open','destination':'/season','clicks':1,'browsers':1}]
    assert not data['posthog']['configured']
    assert data['posthog']['pending'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('patch,headers,status',[
    pytest.param({'path':'/admin'},{},400,id='private-admin'),
    pytest.param({'path':'/share/private-token'},{},400,id='private-share-token'),
    pytest.param({'destination':'/user/private-name'},{},400,id='private-user-name'),
    pytest.param({'path':'/?email=secret'},{},422,id='query-with-private-data'),
    pytest.param({'action':'secret form text'},{},422,id='arbitrary-action-text'),
    pytest.param({}, {'sec-fetch-site':'cross-site'},403,id='cross-site'),
])
async def test_ui_events_reject_private_routes_and_arbitrary_action_text(api_client,patch,headers,status):
    body = {'event':'click','path':'/','action':'button','event_id':str(uuid.uuid4())}
    assert (await api_client.post('/api/analytics/event',json={**body,**patch},headers=headers)).status_code == status
    from app.db import db
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM ui_events')).fetchone())[0] == 0


async def test_ui_event_missing_identity_is_rejected(api_client):
    assert (await api_client.post('/api/analytics/event',json={'event':'click','path':'/'})).status_code == 400


@pytest.mark.asyncio
async def test_posthog_queue_retries_without_exposing_identity(api_client,monkeypatch):
    from app.db import db
    from app.services.posthog_bridge import flush, status
    monkeypatch.setenv('POSTHOG_HOST','https://analytics.example.test')
    monkeypatch.setenv('POSTHOG_PROJECT_KEY','phc_test_public_project_key')
    await api_client.post('/api/analytics/visit',json={'path':'/'})
    event_id = str(uuid.uuid4())
    body={'event':'click','path':'/','action':'results_open','destination':'/race-results','event_id':event_id}
    for _ in range(2):
        assert (await api_client.post('/api/analytics/event',json=body)).status_code == 200
    row = await (await db.conn.execute('SELECT * FROM posthog_outbox')).fetchone()
    payload=json.loads(row['payload'])
    assert payload['event']=='button_clicked'
    assert payload['distinct_id'] != api_client.cookies['turbotears_visitor']
    assert len(payload['distinct_id'])==64
    assert payload['properties']['$process_person_profile'] is False
    assert payload['properties']['$geoip_disable'] is True
    assert 'api_key' not in payload and 'user_id' not in payload
    assert (await status(db.conn))['pending']==1

    class Response:
        def __init__(self,code): self.status=code
        async def __aenter__(self): return self
        async def __aexit__(self,*_): return False

    class Session:
        def __init__(self,code): self.code=code; self.calls=[]
        def post(self,url,**kwargs):
            self.calls.append((url,kwargs))
            return Response(self.code)

    failed=Session(503)
    await flush(db,failed)
    row=await (await db.conn.execute('SELECT attempts,sent,next_attempt FROM posthog_outbox')).fetchone()
    assert row['attempts']==1 and row['sent'] is None and row['next_attempt']>0
    await flush(db,failed)
    assert len(failed.calls)==1  # Backoff prevents an immediate repeat.
    await db.conn.execute('UPDATE posthog_outbox SET next_attempt=0')
    await db.conn.commit()
    delivered=Session(200)
    await flush(db,delivered)
    assert (await status(db.conn))['pending']==0
    assert (await status(db.conn))['last_sent'] is not None
    assert delivered.calls[0][0]=='https://analytics.example.test/i/v0/e/'
    assert delivered.calls[0][1]['allow_redirects'] is False
    assert delivered.calls[0][1]['json']['api_key']=='phc_test_public_project_key'


def test_best_grid_ignores_pit_lane_and_invalid_positions():
    from app.f1_data import _highest_grid
    assert _highest_grid([{'grid':'0'},{'grid':'3'},{'grid':'3'},{'grid':'8'}]) == {'position':3,'count':2}
    assert _highest_grid([{'grid':'0'},{'grid':None}]) == {'position':'-','count':0}
    assert _highest_grid([{'grid':3},{'grid':'3'},{'grid':0}]) == {'position':3,'count':2}


@pytest.mark.asyncio
@pytest.mark.parametrize('configured', [True, False])
async def test_posthog_expired_events_are_removed_before_delivery(api_client, monkeypatch, configured):
    import time
    from app.db import db
    from app.services.posthog_bridge import enqueue, flush
    monkeypatch.setenv('POSTHOG_HOST', 'https://analytics.example.test')
    monkeypatch.setenv('POSTHOG_PROJECT_KEY', 'phc_test_key')
    await enqueue(db.conn, str(uuid.uuid4()), str(uuid.uuid4()), None, '$pageview',
                  {'path': '/'}, time.time() - 31 * 86400)
    await db.conn.commit()
    if not configured:
        monkeypatch.delenv('POSTHOG_PROJECT_KEY')

    class Session:
        def post(self, *_args, **_kwargs):
            pytest.fail('Expired analytics must never be transmitted')

    await flush(db, Session())
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM posthog_outbox')).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_latest_practice_retains_previous_p3_when_current_p3_is_future(api_client):
    from datetime import datetime,timedelta,timezone
    from unittest.mock import AsyncMock,patch
    now=datetime.now(timezone.utc)
    events=[{'round':1,'event_name':'Previous','practice1_start_utc':(now-timedelta(days=7)).isoformat(),
             'practice3_start_utc':(now-timedelta(days=6)).isoformat(),'quali_start_utc':(now-timedelta(days=6)).isoformat()},
            {'round':2,'event_name':'Current','practice1_start_utc':(now-timedelta(hours=1)).isoformat(),
             'practice3_start_utc':(now+timedelta(days=1)).isoformat(),'quali_start_utc':(now+timedelta(days=1)).isoformat()}]
    with patch('app.api.miniapp_api.get_season_schedule_short_async',new_callable=AsyncMock) as schedule, \
         patch('app.api.miniapp_api.get_practice_results_async',new_callable=AsyncMock) as results:
        schedule.return_value=events
        results.return_value=[{'position':1,'driver':'VER','name':'Max Verstappen','best':'1:29.000'}]
        response=await api_client.get('/api/practice-results',params={'season':now.year,'session':3})
    assert response.status_code==200
    data=response.json()
    assert data['round']==1 and data['session']==3 and data['data_fallback'] is True
    assert len(data['results'])==1
    results.assert_awaited_once_with(now.year,1,3,limit=100)


@pytest.mark.asyncio
async def test_posthog_prediction_save_is_confirmed_and_deduplicated(api_client,monkeypatch):
    from unittest.mock import AsyncMock,patch
    from app.db import db,get_or_create_user
    from app.services.prediction_service import save_prediction_profile
    user_id=await get_or_create_user(999888)
    await save_prediction_profile(user_id,'Test participant')
    monkeypatch.setenv('POSTHOG_HOST','https://analytics.example.test')
    monkeypatch.setenv('POSTHOG_PROJECT_KEY','phc_test_key')
    await api_client.post('/api/analytics/visit',json={'path':'/predictions'})
    picks={'pole_driver':'VER','winner_driver':'VER','second_driver':'NOR','third_driver':'PIA',
           'fourth_driver':'LEC','fifth_driver':'HAM','fastest_lap_driver':'NOR',
           'first_retirement_driver':'SAI','safety_car':True}
    with patch('app.api.miniapp_api.get_prediction_context',new_callable=AsyncMock) as context, \
         patch('app.api.miniapp_api.get_prediction_drivers',new_callable=AsyncMock) as drivers:
        context.return_value={'status':'ok','season':2026,'round':16,'is_open':False}
        assert (await api_client.post('/api/predictions/current',json=picks)).status_code==409
        assert (await (await db.conn.execute('SELECT COUNT(*) FROM posthog_outbox')).fetchone())[0]==0
        context.return_value['is_open']=True
        drivers.return_value=[{'code':c} for c in ['VER','NOR','PIA','LEC','HAM','SAI']]
        for _ in range(2):
            response=await api_client.post('/api/predictions/current',json=picks)
            assert response.status_code==200,response.text
    rows=await (await db.conn.execute('SELECT payload FROM posthog_outbox')).fetchall()
    assert len(rows)==1
    payload=json.loads(rows[0]['payload'])
    assert payload['event']=='prediction_saved'
    assert set(payload['properties'])=={'path','season','round','$process_person_profile','$geoip_disable'}
    assert (await (await db.conn.execute('SELECT COUNT(*) FROM race_predictions')).fetchone())[0]==1
