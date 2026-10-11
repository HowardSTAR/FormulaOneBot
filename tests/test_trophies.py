from datetime import datetime, timezone

import pytest

from app.services import trophies


NOW = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()


async def user(database, telegram=7777):
    cursor = await database.conn.execute('INSERT INTO users(telegram_id) VALUES (?)', (telegram,))
    await database.conn.commit()
    return cursor.lastrowid


def calendar(size):
    return [{'round': n, 'race_start_utc': '2026-10-01T12:00:00+00:00'} for n in range(1, size+1)]


async def prediction(database, user_id, round_num, *, season=2026, winner='VER', second='NOR', third='PIA', points=10):
    await database.conn.execute('''INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,
        second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,first_retirement_driver,safety_car,points)
        VALUES (?,?,?,'VER',?,?,?,'LEC','HAM','NOR','SAI',1,?)''', (user_id,season,round_num,winner,second,third,points))
    await database.conn.execute('''INSERT OR IGNORE INTO prediction_round_results(season,round,event_name,
        winner_driver,second_driver,third_driver,max_points) VALUES (?,?,'Гран-при','VER','NOR','PIA',40)''', (season,round_num))


def family(data, name):
    return next(item for item in data['families'] if item['id']==name)


@pytest.mark.asyncio
async def test_season_thresholds_cancellation_expansion_and_permanent_awards(db_session):
    uid = await user(db_session)
    for n in range(1,12):
        await prediction(db_session, uid, n)
    await prediction(db_session, uid, 12, season=2025)
    await db_session.conn.commit()
    first = await trophies.collection(uid, True, schedule=calendar(24), now=NOW)
    rhythm = family(first,'rhythm')['levels']
    assert [level['target'] for level in rhythm] == [3,12,24]
    assert [level['progress'] for level in rhythm] == [11,11,11]
    assert rhythm[0]['earned_at'] and not rhythm[1]['earned_at']
    smaller = await trophies.collection(uid, True, schedule=calendar(22), now=NOW)
    assert family(smaller,'rhythm')['levels'][1]['earned_at']
    expanded = await trophies.collection(uid, True, schedule=calendar(25), now=NOW)
    assert family(expanded,'rhythm')['levels'][1]['target']==13
    assert family(expanded,'rhythm')['levels'][1]['earned_at']
    cancelled = calendar(22)
    cancelled[0]['is_cancelled']=True
    reduced = await trophies.collection(uid, True, schedule=cancelled, now=NOW)
    assert family(reduced,'rhythm')['levels'][2]['target']==21
    assert family(reduced,'rhythm')['levels'][2]['progress']==10
    unknown = await trophies.collection(uid, True, schedule=[], now=NOW)
    assert family(unknown,'rhythm')['levels'][1]['target'] is None
    assert family(unknown,'rhythm')['levels'][1]['earned_at']


@pytest.mark.asyncio
async def test_gold_waits_for_season_end_and_new_season_does_not_inherit_progress(db_session):
    uid = await user(db_session)
    for n in range(1,7):
        await prediction(db_session,uid,n)
    await db_session.conn.commit()
    future = calendar(6)
    future[-1]['race_start_utc']='2026-10-11T12:00:00+00:00'
    before = await trophies.collection(uid,True,schedule=future,now=NOW)
    assert not family(before,'rhythm')['levels'][2]['earned_at']
    after = await trophies.collection(uid,True,schedule=calendar(6),now=NOW)
    assert family(after,'rhythm')['levels'][2]['earned_at']
    next_year = await trophies.collection(uid,True,schedule=calendar(24),now=datetime(2027,1,1,tzinfo=timezone.utc).timestamp())
    assert family(next_year,'rhythm')['levels'][0]['progress']==0
    assert not family(next_year,'rhythm')['levels'][0]['earned_at']
    assert any(award['family']=='rhythm' and award['season']==2026 and award['level']==2 for award in next_year['earned'])


@pytest.mark.asyncio
async def test_correct_predictions_and_real_game_modes(db_session):
    uid=await user(db_session)
    await prediction(db_session,uid,1)
    await prediction(db_session,uid,2,second='PIA',third='NOR')
    await prediction(db_session,uid,3,winner='NOR')
    await prediction(db_session,uid,4,points=None)
    await db_session.conn.executemany('INSERT INTO reaction_leaderboard_scores(telegram_id,time_ms) VALUES (7777,?)',[(220,),(280,),(350,)])
    # Full repeated races remain attainable; each track establishes its own baseline.
    await db_session.conn.executemany('INSERT INTO race_game_scores(telegram_id,time_ms,track_id,telemetry_json) VALUES (7777,?,?,?)',[
        (60000,'track-a','[]'),(63000,'track-a','[]'),(63001,'track-a','[]'),
        (59000,'track-a','[]'),(61000,'track-a','[]'),(70000,'track-b','[]'),(70000,'track-b','[]'),
        (15000,'track-a',None)])
    await db_session.conn.executemany('INSERT INTO reflex_grid_scores(telegram_id,mode,difficulty,score,time_ms) VALUES (7777,?,?,?,?)',[
        ('timed','medium',18,10000),('timed','easy',50,10000),('endless','medium',40,10000),('timed','medium',40,9999)])
    await db_session.conn.commit()
    data=await trophies.collection(uid,True,schedule=calendar(24),now=NOW)
    assert family(data,'oracle')['levels'][0]['progress']==2
    assert family(data,'podium')['levels'][0]['progress']==1
    assert [level['progress'] for level in family(data,'lights')['levels']]==[3,2,1]
    assert family(data,'ghost')['levels'][0]['progress']==4
    assert [level['target'] for level in family(data,'ghost')['levels']]==[3,10,25]
    assert family(data,'atlas')['levels'][2]['earned_at']
    assert [level['target'] for level in family(data,'grid')['levels']]==[10,15,20]
    assert family(data,'grid')['levels'][0]['progress']==18
    assert family(data,'grid')['levels'][1]['earned_at'] and not family(data,'grid')['levels'][2]['earned_at']


@pytest.mark.asyncio
async def test_acknowledgment_badge_authorization_privacy_and_merge(db_session):
    uid=await user(db_session)
    other=await user(db_session,8888)
    for n in range(1,6):
        await prediction(db_session,uid,n)
    await db_session.conn.commit()
    data=await trophies.collection(uid,True,schedule=calendar(24),now=NOW)
    assert data['pending']
    receipt='oracle:0:0'
    with pytest.raises(PermissionError):
        await trophies.select_badge(other,receipt)
    with pytest.raises(PermissionError):
        await trophies.select_badge(uid,'oracle:0:2')
    await trophies.select_badge(uid,receipt)
    await trophies.acknowledge(other,[receipt])
    assert receipt in [r['id'] for r in (await trophies.collection(uid,True,schedule=calendar(24),now=NOW))['pending']]
    await trophies.acknowledge(uid,[receipt])
    await trophies.acknowledge(uid,[receipt])
    repeat=await trophies.collection(uid,True,schedule=calendar(24),now=NOW)
    assert receipt not in [r['id'] for r in repeat['pending']]
    public=await trophies.collection(uid)
    assert public['pending']==[] and public['badge']['id']==receipt
    assert all(level['earned_at'] and 'progress' not in level and 'rule' not in level for f in public['families'] for level in f['levels'])
    assert 'heart' not in [f['id'] for f in public['families']]
    async with db_session.write_lock:
        await trophies.transfer(db_session.conn,uid,other)
        await db_session.conn.commit()
    merged=await trophies.collection(other)
    assert merged['badge']['id']==receipt and len(merged['earned'])==len(public['earned'])
    assert (await trophies.collection(uid))['earned']==[]


def test_support_days_merge_overlaps_ignore_future_and_keep_pauses():
    day=86400
    assert trophies.support_days([(0,40*day),(30*day,60*day),(70*day,100*day)],90*day)==80
    assert trophies.support_days([(100*day,120*day)],90*day)==0


@pytest.mark.asyncio
async def test_api_receipts_and_locked_badges(api_client,monkeypatch):
    async def no_schedule(season):
        return []
    monkeypatch.setattr(trophies,'calendar_for',no_schedule)
    data=(await api_client.get('/api/profiles/me/trophies')).json()
    assert len(data['families'])==8 and not data['calendar_known']
    assert (await api_client.patch('/api/profiles/me/trophy-badge',json={'id':'oracle:0:2'})).status_code==403
    assert (await api_client.post('/api/profiles/me/trophies/seen',json={'ids':['oracle:0:2'],'user_id':123})).status_code==422
    assert (await api_client.post('/api/profiles/me/trophies/seen',json={'ids':[]})).status_code==200
