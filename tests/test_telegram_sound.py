from unittest.mock import AsyncMock

import aiosqlite
import pytest
from aiogram.types import InputMediaPhoto


@pytest.fixture
async def sound_db(monkeypatch):
    from app.db import db
    async with aiosqlite.connect(':memory:') as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript('''
            CREATE TABLE users(id INTEGER, telegram_id INTEGER, timezone TEXT,
                notify_before INTEGER, notifications_enabled INTEGER,
                reminder_sessions INTEGER, archived_at TEXT);
            INSERT INTO users VALUES(1,101,'UTC',60,0,31,NULL);
            INSERT INTO users VALUES(2,102,'UTC',60,1,31,NULL);
            INSERT INTO users VALUES(3,103,'UTC',60,0,31,'archived');
            CREATE TABLE favorite_drivers(user_id INTEGER, driver_code TEXT);
            CREATE TABLE favorite_teams(user_id INTEGER, constructor_name TEXT);
            INSERT INTO favorite_drivers VALUES(1,'STR');
            INSERT INTO favorite_drivers VALUES(3,'VER');
        ''')
        monkeypatch.setattr(db, 'conn', conn)
        yield conn


@pytest.mark.asyncio
async def test_silent_users_remain_recipients(sound_db):
    from app.utils.notifications import get_users_with_settings
    from app.db import get_users_favorites_for_notifications
    assert {u[0] for u in await get_users_with_settings(True)} == {101, 102}
    assert set(await get_users_favorites_for_notifications(True)) == {101}


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['message', 'photo', 'media_group'])
@pytest.mark.parametrize('chat_id,quiet,expected', [(101,False,True),(102,False,False),(102,True,True),(-100,False,False)])
async def test_delivery_and_sound(sound_db, kind, chat_id, quiet, expected):
    from app.utils import safe_send as s
    bot = AsyncMock()
    options = {'disable_notification': quiet}
    if kind == 'message':
        success = await s.safe_send_message(bot, chat_id, 'New event', **options)
    elif kind == 'photo':
        success = await s.safe_send_photo(bot, chat_id, b'photo', **options)
    else:
        success = await s.safe_send_media_group(bot, chat_id, [InputMediaPhoto(media='a'), InputMediaPhoto(media='b')], **options)
    assert success
    method = getattr(bot, f'send_{kind}')
    method.assert_awaited_once()
    assert method.await_args.kwargs['disable_notification'] is expected
