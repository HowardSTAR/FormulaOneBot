"""Opt-in real HTTP recovery test against the local Postman fixture."""
import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.mark.skipif(not os.getenv('FORECAST_SIMULATION_URL'),reason='Start the local Postman forecast simulation first')
async def test_provider_outage_retries_same_job_over_real_http(db_session,monkeypatch):
    from app.services import prediction_analytics as service, prediction_history as history
    base=os.environ['FORECAST_SIMULATION_URL'].rstrip('/')+'/jolpica'
    monkeypatch.setattr(service,'RESULTS_URL',base)
    monkeypatch.setattr(history,'BASE',base)
    year=datetime.now(timezone.utc).year
    start=time.time()+86400
    event={'round':24,'event_name':'Synthetic future session','race_start_utc':datetime.fromtimestamp(start,timezone.utc).isoformat()}
    monkeypatch.setattr(service,'get_season_schedule_short_async',AsyncMock(return_value=[event]))
    monkeypatch.setattr(service,'context_data',AsyncMock(return_value={'weather':{'available':False},'news':[],'news_available':False}))
    await db_session.conn.execute("INSERT INTO prediction_analytics(id,season,round,session,created_at,created_by) VALUES('simulation',?,24,'race',?,1)",(year,time.time()))
    await db_session.conn.commit()
    async with httpx.AsyncClient() as client:
        await client.get(base+'/control/fail')
        await service.run_job()
        failed=await (await db_session.conn.execute("SELECT * FROM prediction_analytics WHERE id='simulation'")).fetchone()
        assert failed['status']=='pending' and failed['attempts']==1
        await client.get(base+'/control/recover')
        await db_session.conn.execute('UPDATE prediction_analytics SET next_attempt=0')
        await db_session.conn.commit()
        await service.run_job()
    ready=await (await db_session.conn.execute("SELECT * FROM prediction_analytics WHERE id='simulation'")).fetchone()
    assert ready['status']=='ready' and ready['attempts']==2
    payload=json.loads(ready['payload'])
    assert len(payload['model']['drivers'])==20
    assert payload['cutoff']==failed['created_at']
