import pytest

from app.services import user_profiles as profiles


async def participant(database, name='Гонщик', telegram_id=2099386):
    cursor = await database.conn.execute(
        'INSERT INTO users(email,email_verified,telegram_id,display_name) VALUES (?,1,?,?)',
        (f'{telegram_id}@example.test', telegram_id, name))
    await database.conn.execute('INSERT INTO prediction_profiles(user_id,display_name) VALUES (?,?)', (cursor.lastrowid, name))
    await database.conn.commit()
    return cursor.lastrowid


async def membership(database, user_id, level):
    await database.conn.execute("INSERT OR REPLACE INTO boosty_memberships VALUES (?,'turbotears',1,1,?,1)", (user_id, level))
    await database.conn.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('level,tier', [('На старт', 1), ('Свой стиль', 2), ('Полный газ', 3), ('Неизвестный', 1)])
async def test_membership_rights(db_session, level, tier):
    user_id = await participant(db_session)
    await membership(db_session, user_id, level)
    person = (await profiles.identities())[user_id]
    assert person['tier'] == tier
    assert 'email' not in person and 'telegram_id' not in person
    if tier < 3:
        with pytest.raises(PermissionError):
            await profiles.save_style(user_id, dict(frame='gold', color='gold', background='champion'))
    if tier >= 2:
        await profiles.save_style(user_id, dict(frame='red', color='red', background='grid'))
        assert (await profiles.identities())[user_id]['style']['frame'] == 'red'


@pytest.mark.asyncio
async def test_style_downgrade_preserves_selection(db_session):
    user_id = await participant(db_session)
    await membership(db_session, user_id, 'Полный газ')
    selected = dict(frame='neon', color='mint', background='aurora')
    await profiles.save_style(user_id, selected)
    await membership(db_session, user_id, 'На старт')
    assert (await profiles.identities())[user_id]['style'] == dict(frame='classic', color='white', background='carbon')
    await membership(db_session, user_id, 'Полный газ')
    assert (await profiles.identities())[user_id]['style'] == selected
    with pytest.raises(ValueError):
        await profiles.save_style(user_id, dict(frame='url(evil)', color='white', background='carbon'))


@pytest.mark.asyncio
async def test_profile_hides_pending_and_private_records_and_selects_best(db_session):
    user_id = await participant(db_session)
    for season, round_num, points in [(2026, 1, 0), (2026, 2, 30), (2026, 3, 30), (2026, 4, None), (2025, 1, 39)]:
        await db_session.conn.execute('''INSERT INTO race_predictions(user_id,season,round,pole_driver,
            winner_driver,second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
            first_retirement_driver,safety_car,points,max_points) VALUES (?,?,?,'VER','VER','NOR','PIA','LEC','HAM','VER','SAI',1,?,40)''',
            (user_id, season, round_num, points))
    await db_session.conn.execute("INSERT INTO race_game_scores(telegram_id,time_ms) VALUES (2099386,50000),(2099386,40000)")
    await db_session.conn.commit()
    own = await profiles.profile(user_id, user_id, 2026)
    public = await profiles.profile(user_id, -1, 2026)
    assert own['best_prediction']['round'] == 2
    assert own['total_points'] == 60
    assert len(own['predictions']) == 4 and len(public['predictions']) == 3
    assert own['records'][0]['best_time_ms'] == 40000 and own['records'][0]['attempts'] == 2
    assert public['records'] == []
    assert (await profiles.profile(user_id, user_id, 2025))['best_prediction']['points'] == 39
    await db_session.conn.execute("INSERT INTO reaction_leaderboard_profiles(telegram_id,display_name,leaderboard_opt_in,prompt_seen) VALUES (2099386,'Test',1,1)")
    await db_session.conn.commit()
    assert len((await profiles.profile(user_id, -1, 2026))['records']) == 1
    await db_session.conn.execute('UPDATE users SET archived_at=CURRENT_TIMESTAMP WHERE id=?', (user_id,))
    await db_session.conn.commit()
    assert await profiles.profile(user_id, -1, 2026) is None


@pytest.mark.asyncio
async def test_supporter_league_access_and_manual_override(db_session):
    user_id = await participant(db_session)
    other_id = await participant(db_session, 'Без подписки', 4444)
    with pytest.raises(PermissionError):
        await profiles.supporter_league(user_id, 2026)
    await membership(db_session, user_id, 'На старт')
    assert [e['user_id'] for e in (await profiles.supporter_league(user_id, 2026))['entries']] == [user_id]
    await db_session.conn.execute("INSERT INTO premium_overrides VALUES (?,1,CURRENT_TIMESTAMP)", (other_id,))
    await db_session.conn.commit()
    assert (await profiles.identities())[other_id]['tier'] == 3
    assert len((await profiles.supporter_league(user_id, 2026))['entries']) == 2
    await db_session.conn.execute('UPDATE premium_overrides SET active=0 WHERE user_id=?', (other_id,))
    await db_session.conn.commit()
    assert (await profiles.identities())[other_id]['tier'] == 0


@pytest.mark.asyncio
async def test_profile_api_validation_and_server_authorization(api_client):
    me = await api_client.get('/api/profiles/me?season=2026')
    assert me.status_code == 200 and me.headers['cache-control'] == 'no-store'
    user_id = me.json()['user_id']
    assert (await api_client.get(f'/api/profiles/{user_id}')).status_code == 200
    assert (await api_client.get('/api/profiles/987654')).status_code == 404
    assert (await api_client.get('/api/profiles/me?season=0')).status_code == 422
    assert (await api_client.patch('/api/profiles/me/style', json=dict(frame='gold', color='white', background='carbon'))).status_code == 403
    assert (await api_client.patch('/api/profiles/me/style', json=dict(frame='classic', color='white', background='carbon', tier=3))).status_code == 422
    assert (await api_client.get('/api/profiles/supporters')).status_code == 403


@pytest.mark.asyncio
async def test_account_merge_keeps_style(db_session):
    from app.services.account_link_service import AccountLinkService
    source = await participant(db_session)
    target = await participant(db_session, 'Веб-аккаунт', 4444)
    await membership(db_session, source, 'Полный газ')
    await profiles.save_style(source, dict(frame='neon', color='mint', background='aurora'))
    await AccountLinkService._transfer_related_data(db_session.conn, source, target)
    await db_session.conn.commit()
    row = await (await db_session.conn.execute('SELECT frame,color,background FROM user_profile_styles WHERE user_id=?', (target,))).fetchone()
    assert tuple(row) == ('neon', 'mint', 'aurora')
