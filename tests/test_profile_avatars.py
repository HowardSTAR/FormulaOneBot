import io
from itertools import product

import pytest
from PIL import Image

from app.services import profile_avatar, user_profiles
from app.services.account_link_service import AccountLinkService
from test_user_profiles import participant


@pytest.mark.asyncio
async def test_avatar_save_public_read_validation_and_isolation(api_client):
    original = (await api_client.get('/api/profiles/me')).json()
    assert original['avatar'] == profile_avatar.DEFAULT
    choice = dict(helmet='cobalt', suit='mint', background='gold')
    assert (await api_client.patch('/api/profiles/me/avatar', json=choice)).status_code == 200
    public = (await api_client.get(f"/api/profiles/{original['user_id']}")).json()
    assert public['avatar'] == choice and public['style'] == original['style']
    for bad in [dict(choice, helmet='../../.env'), dict(choice, user_id=42), {'helmet': 'mint'}]:
        assert (await api_client.patch('/api/profiles/me/avatar', json=bad)).status_code == 422
    assert (await api_client.get('/api/profiles/me')).json()['avatar'] == choice
    response = await api_client.get('/api/profiles/avatar/v1.png', params=choice)
    assert response.status_code == 200 and 'immutable' in response.headers['cache-control']
    assert Image.open(io.BytesIO(response.content)).size == (384, 384)
    assert (await api_client.get('/api/profiles/avatar/v1.png?helmet=unknown')).status_code == 422


@pytest.mark.asyncio
async def test_account_merge_preserves_avatar_and_respects_target_choice(db_session):
    source = await participant(db_session)
    target = await participant(db_session, telegram_id=4444)
    choice = dict(helmet='mint', suit='cobalt', background='mint')
    await user_profiles.save_avatar(source, choice)
    await AccountLinkService._transfer_related_data(db_session.conn, source, target)
    assert (await user_profiles.identities())[target]['avatar'] == choice
    assert await (await db_session.conn.execute('SELECT 1 FROM user_profile_avatars WHERE user_id=?', (source,))).fetchone() is None
    await user_profiles.save_avatar(source, profile_avatar.DEFAULT)
    await AccountLinkService._transfer_related_data(db_session.conn, source, target)
    assert (await user_profiles.identities())[target]['avatar'] == choice


def test_all_modular_combinations_render_with_independent_regions():
    for helmet, suit, background in product(*profile_avatar.OPTIONS.values()):
        data = profile_avatar.render(helmet, suit, background)
        image = Image.open(io.BytesIO(data))
        assert image.size == (384, 384) and image.mode == 'RGB'
    def image(**values):
        return Image.open(io.BytesIO(profile_avatar.render(**{**profile_avatar.DEFAULT, **values})))
    original = image()
    assert original.crop((0, 0, 384, 238)).tobytes() == image(suit='mint').crop((0, 0, 384, 238)).tobytes()
    assert original.crop((0, 238, 384, 384)).tobytes() == image(helmet='mint').crop((0, 238, 384, 384)).tobytes()
    assert original.tobytes() != image(background='gold').tobytes()
