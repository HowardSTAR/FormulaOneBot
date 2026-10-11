import pytest

from app.services import user_profiles as profiles


@pytest.mark.asyncio
async def test_profile_guide_is_per_account_private_and_survives_linking(db_session):
    ids=[]
    for telegram in [7777,8888]:
        cursor=await db_session.conn.execute('INSERT INTO users(telegram_id) VALUES (?)',(telegram,))
        ids.append(cursor.lastrowid)
    await db_session.conn.commit()
    first,second=ids
    assert (await profiles.profile(first,first))['profile_guide_seen'] is False
    await profiles.finish_profile_guide(first,'skipped')
    await profiles.finish_profile_guide(first,'completed')
    assert (await profiles.profile(first,first))['profile_guide_seen'] is True
    assert (await profiles.profile(second,second))['profile_guide_seen'] is False
    assert 'profile_guide_seen' not in await profiles.profile(first,second)
    assert 'profile_guide_seen' not in await profiles.profile(first,-1)
    from app.services.account_link_service import AccountLinkService
    await AccountLinkService._transfer_related_data(db_session.conn,first,second)
    await db_session.conn.commit()
    assert (await profiles.profile(second,second))['profile_guide_seen'] is True
    assert not await (await db_session.conn.execute('SELECT * FROM user_profile_guides WHERE user_id=?',(first,))).fetchall()


@pytest.mark.asyncio
async def test_profile_guide_endpoint_validates_receipt_and_uses_authenticated_owner(api_client):
    first=(await api_client.get('/api/profiles/me')).json()
    assert first['profile_guide_seen'] is False
    assert (await api_client.patch('/api/profiles/me/guide',json={'status':'completed','user_id':999})).status_code==422
    assert (await api_client.patch('/api/profiles/me/guide',json={'status':'unknown'})).status_code==422
    assert (await api_client.patch('/api/profiles/me/guide',json={'status':'skipped'})).status_code==200
    assert (await api_client.get('/api/profiles/me')).json()['profile_guide_seen'] is True
    assert (await api_client.patch('/api/profiles/me/guide',json={'status':'completed'})).status_code==200
