"""Home selections stay separate from following and are scoped to the account."""
import pytest


@pytest.mark.asyncio
async def test_home_selection_save_validate_and_remove(api_client):
    for code in ['VER', 'NOR', 'LEC']:
        assert (await api_client.post('/api/favorites/driver', json={'id': code})).status_code == 200
    for team in ['Ferrari', 'McLaren']:
        await api_client.post('/api/favorites/team', json={'id': team})
    chosen = {'drivers': ['LEC', 'VER'], 'teams': ['McLaren']}
    assert (await api_client.post('/api/favorites/home', json=chosen)).status_code == 200
    result = (await api_client.get('/api/favorites')).json()
    assert result['home'] == chosen
    assert set(result['drivers']) == {'LEC', 'VER', 'NOR'}
    assert set(result['teams']) == {'Ferrari', 'McLaren'}
    for invalid in [
        {'drivers': ['VER', 'VER'], 'teams': ['Ferrari']},
        {'drivers': ['OLD', 'NOR'], 'teams': ['Ferrari']},
        {'drivers': ['VER'], 'teams': ['Ferrari']},
        {'drivers': ['VER', 'NOR'], 'teams': ['Other']},
        {'drivers': ['VER', 'NOR', 'LEC'], 'teams': ['Ferrari']},
    ]:
        assert (await api_client.post('/api/favorites/home', json=invalid)).status_code == 422
        assert (await api_client.get('/api/favorites')).json()['home'] == chosen
    await api_client.post('/api/favorites/driver', json={'id': 'LEC'})
    await api_client.post('/api/favorites/team', json={'id': 'McLaren'})
    result = (await api_client.get('/api/favorites')).json()
    assert result['home'] == {'drivers': ['VER', 'NOR'], 'teams': ['Ferrari']}


@pytest.mark.asyncio
async def test_home_empty_and_account_isolation(api_client):
    assert (await api_client.get('/api/favorites')).json()['home'] == {'drivers': [], 'teams': []}
    assert (await api_client.post('/api/favorites/home', json={'drivers': [], 'teams': []})).status_code == 200
    from app.db import db, get_or_create_user
    other = await get_or_create_user(12345678)
    await db.conn.execute('INSERT INTO favorite_drivers VALUES (?,?)', (other, 'OTHER'))
    await db.conn.commit()
    assert (await api_client.post('/api/favorites/home', json={'drivers': ['OTHER'], 'teams': []})).status_code == 422
