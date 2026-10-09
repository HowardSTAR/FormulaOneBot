"""Broadcast attribution is inert on reads, private in reports and replay-safe."""
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException

from app.api import site_analytics as api, admin_tools_api as admin
from app.db import Database
from app.services import notification_clicks as clicks, telegram_outbox as outbox, web_notifications as web
from app.utils.mini_app_links import mini_app_button
from app.utils.telegram_presentation import personal_buttons


@pytest_asyncio.fixture
async def tracking(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    await database.init_tables()
    for module in (clicks, outbox, web, api, admin):
        monkeypatch.setattr(module, 'db', database)
    monkeypatch.setenv('MINI_APP_URL', 'https://example.test/?source=telegram')
    await database.conn.executemany('INSERT INTO users(id,telegram_id) VALUES(?,?)', [(1, 101), (2, 102)])
    await database.conn.executemany('INSERT INTO web_notification_members VALUES(?,?)', [(1, time.time()-60), (2, time.time()-60)])
    await database.conn.commit()
    auth = AsyncMock(return_value=1)
    monkeypatch.setattr(api, 'require_hybrid_user_id', auth)
    app = FastAPI(); app.include_router(api.router); app.include_router(admin.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield database, client, auth
    await database.close()


async def prediction_keyboard():
    return personal_buttons(2026, 16, await mini_app_button(None, 'Таблица прогнозов', '/predictions',
                                                          tab='leaderboard', season=2026, round=16))


@pytest.mark.asyncio
async def test_queue_freezes_tracked_links_without_changing_destination(tracking):
    database, _, _ = tracking
    original = await prediction_keyboard()
    key = 'prediction:results:2026:16'
    for _ in range(2):
        await outbox.enqueue(key, 'Results', original, [(101, 'UTC')], time.time()+3600)
    batch = await (await database.conn.execute('SELECT keyboard FROM telegram_delivery_batches')).fetchone()
    keyboard = json.loads(batch['keyboard'])['inline_keyboard']
    parts = urlsplit(keyboard[0][0]['web_app']['url'])
    query = parse_qs(parts.query)
    token = query.pop('nb')[0]
    assert len(token) == 32
    assert parts.path == '/predictions'
    assert query == {'source': ['telegram'], 'tab': ['leaderboard'], 'season': ['2026'], 'round': ['16']}
    assert keyboard[1][0]['callback_data'] == 'personal:review:2026:16'
    assert 'nb=' not in original.inline_keyboard[0][0].web_app.url
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM notification_button_links')).fetchone())[0] == 3


@pytest.mark.asyncio
async def test_web_and_telegram_arrivals_are_distinct_and_replays_count_once(tracking):
    database, client, _ = tracking
    await outbox.enqueue('prediction:results:2026:16', 'Results', await prediction_keyboard(), [(101, 'UTC')], time.time()+3600)
    await web.publish('prediction-results:2026:16', 'Results', 'Body', '/predictions?tab=leaderboard&season=2026&round=16')
    links = await (await database.conn.execute("SELECT token,channel FROM notification_button_links WHERE button='leaderboard'")).fetchall()
    for link in links:
        body = {'token': link['token'], 'path': '/predictions', 'event_id': str(uuid.uuid4())}
        for _ in range(3):
            response = await client.post('/api/analytics/notification-entry', json=body)
            assert response.status_code == 200
    report = await clicks.report(database.conn, 0)
    assert report['summary'] == {'interactions': 2, 'unique_users': 1, 'callbacks': 0, 'arrivals': 2}
    leaderboard = [item for item in report['items'] if item['button'] == 'leaderboard']
    assert {item['channel'] for item in leaderboard} == {'telegram', 'web'}
    assert {item['campaign'] for item in leaderboard} == {'prediction:results:2026:16'}
    assert all(item['clicks'] == item['unique_users'] == 1 for item in leaderboard)
    assert all(item['metric'] == 'arrival' for item in leaderboard)
    report_text = json.dumps(report)
    assert links[0]['token'] not in report_text and 'viewer' not in report_text and 'user_id' not in report_text
    before = (await (await database.conn.execute('SELECT COUNT(*) FROM notification_button_events')).fetchone())[0]
    await clicks.report(database.conn, 0)
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM notification_button_events')).fetchone())[0] == before
    assert not (await clicks.report(database.conn, time.time()+10))['items']


@pytest.mark.asyncio
async def test_callback_attribution_matches_actual_delivered_message(tracking):
    database, _, _ = tracking
    key = 'prediction:results:2026:16'
    await outbox.enqueue(key, 'Results', await prediction_keyboard(), [(101, 'UTC')], time.time()+3600)
    await database.conn.execute("UPDATE telegram_deliveries SET status='sent',message_id=10")
    await database.conn.commit()
    callback = SimpleNamespace(id='real-callback', message=SimpleNamespace(chat=SimpleNamespace(id=101), message_id=10),
                               from_user=SimpleNamespace(id=101))
    for _ in range(2):
        await clicks.record_callback(callback, 'review', 1)
    callback.id = 'second-callback'
    await clicks.record_callback(callback, 'review', 1)
    callback.message.message_id = 99
    await clicks.record_callback(callback, 'leagues', 1)
    data = await clicks.report(database.conn, 0)
    item = next(item for item in data['items'] if item['button'] == 'review')
    assert item['clicks'] == 2 and item['unique_users'] == 1 and item['metric'] == 'callback'
    assert data['summary']['callbacks'] == 2
    assert next(item for item in data['items'] if item['button'] == 'leagues')['clicks'] == 0


@pytest.mark.asyncio
async def test_unregistered_wrong_destination_and_cross_site_entries_rejected(tracking):
    database, client, _ = tracking
    await outbox.enqueue('prediction:results:2026:16', 'Results', await prediction_keyboard(), [(101, 'UTC')], time.time()+3600)
    token = (await (await database.conn.execute("SELECT token FROM notification_button_links WHERE button='leaderboard'")).fetchone())[0]
    body = {'token': token, 'path': '/predictions', 'event_id': str(uuid.uuid4())}
    for bad in ({'token': 'x'*32}, {'path': '/community'}, {'path': '/admin'}):
        assert (await client.post('/api/analytics/notification-entry', json={**body, **bad})).status_code == 400
    for bad in ({'token': 'bad'}, {'path': '/predictions?secret=123'}, {'event_id': 'bad'}):
        assert (await client.post('/api/analytics/notification-entry', json={**body, **bad})).status_code == 422
    assert (await client.post('/api/analytics/notification-entry', json=body, headers={'sec-fetch-site': 'cross-site'})).status_code == 403
    assert (await client.get('/api/analytics/notification-entry')).status_code == 405
    review_token = (await (await database.conn.execute("SELECT token FROM notification_button_links WHERE button='review'")).fetchone())[0]
    assert (await client.post('/api/analytics/notification-entry', json={**body, 'token': review_token})).status_code == 400
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM notification_button_events')).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_anonymous_browser_identifier_is_stable_and_rate_limited(tracking):
    database, client, auth = tracking
    auth.side_effect = HTTPException(401, 'Guest')
    await web.publish('weekly-race:2026-10-05', 'Week', 'Winner', '/community?weekly=previous&week=2026-09-28')
    token = (await (await database.conn.execute('SELECT token FROM notification_button_links')).fetchone())[0]
    body = {'token': token, 'path': '/community', 'event_id': str(uuid.uuid4())}
    assert (await client.post('/api/analytics/notification-entry', json=body)).status_code == 200
    assert client.cookies.get('turbotears_visitor')
    assert (await client.post('/api/analytics/notification-entry', json={**body, 'event_id': str(uuid.uuid4())})).status_code == 200
    data = await clicks.report(database.conn, 0)
    assert data['summary']['interactions'] == 2 and data['summary']['unique_users'] == 1
    viewer = (await (await database.conn.execute('SELECT viewer FROM notification_button_events LIMIT 1')).fetchone())[0]
    await database.conn.executemany('INSERT INTO notification_button_events VALUES(?,?,?,?,?)',
                                    [(str(uuid.uuid4()), token, viewer, None, time.time()) for _ in range(118)])
    await database.conn.commit()
    assert (await client.post('/api/analytics/notification-entry', json={**body, 'event_id': str(uuid.uuid4())})).status_code == 429


@pytest.mark.asyncio
async def test_read_only_admin_report_is_private_and_contains_zero_click_buttons(tracking):
    database, client, _ = tracking
    await outbox.enqueue('prediction:results:2026:16', 'Results', await prediction_keyboard(), [(101, 'UTC')], time.time()+3600)
    assert (await client.get('/api/admin/tools/product-analytics')).status_code in {401, 403}
    # Use the normal protected report with only its identity dependency replaced.
    client._transport.app.dependency_overrides[admin.require_admin_session] = lambda: admin.AdminContext(id=1, role='admin')
    response = await client.get('/api/admin/tools/product-analytics')
    assert response.status_code == 200
    assert len(response.json()['notification_buttons']['items']) == 3
    assert all(item['clicks'] == 0 for item in response.json()['notification_buttons']['items'])
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
async def test_manual_broadcast_tracks_both_channels(tracking, monkeypatch):
    from app.services import prediction_broadcasts as manual
    database, _, _ = tracking
    monkeypatch.setattr(manual, 'db', database)
    await database.conn.execute("INSERT INTO prediction_round_results(season,round,event_name) VALUES(2026,16,'Test')")
    await database.conn.commit()
    preview = await manual.preview(2026, 16)
    await manual.send(2026, 16, preview['fingerprint'], 1)
    data = await clicks.report(database.conn, 0)
    assert len(data['items']) == 4
    assert len({item['campaign'] for item in data['items']}) == 1
    url = (await (await database.conn.execute('SELECT url FROM web_notifications LIMIT 1')).fetchone())[0]
    assert len(parse_qs(urlsplit(url).query)['nb'][0]) == 32


@pytest.mark.asyncio
async def test_bot_menu_and_future_buttons_are_discovered_and_replay_safe(tracking):
    from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
    from app.middlewares.button_analytics import track_keyboard, record_button
    database, _, _ = tracking
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Новая кнопка', callback_data='future:secret-value'),
    ]])
    await track_keyboard(database.conn, keyboard, 101)
    await track_keyboard(database.conn, ReplyKeyboardMarkup(keyboard=[[
        KeyboardButton(text='Новое меню'),
    ]]), 101)
    await database.conn.commit()
    message = Message.model_validate({'message_id': 12, 'date': int(time.time()),
        'chat': {'id': 101, 'type': 'private'}, 'from': {'id': 101, 'is_bot': False, 'first_name': 'Test'},
        'text': 'Новое меню'})
    callback = CallbackQuery.model_validate({'id': 'new-button-click', 'chat_instance': 'x',
        'from': {'id': 101, 'is_bot': False, 'first_name': 'Test'}, 'data': 'future:secret-value',
        'message': {**message.model_dump(by_alias=True), 'reply_markup': keyboard.model_dump()}})
    for event in (message, callback, message, callback):
        await record_button(event)
    await record_button(message.model_copy(update={'message_id': 13, 'text': 'Личный текст'}))
    report = await clicks.report(database.conn, 0)
    assert report['summary'] == {'interactions': 2, 'unique_users': 1, 'callbacks': 2, 'arrivals': 0}
    assert {item['label'] for item in report['items']} == {'Новое меню', 'Новая кнопка'}
    assert 'secret-value' not in json.dumps(report)


@pytest.mark.asyncio
async def test_my_prediction_and_new_f1hub_destinations_are_tracked(tracking):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.middlewares.button_analytics import track_keyboard
    database, client, _ = tracking
    original = await mini_app_button(None, '🔮 Мой прогноз', '/predictions', tab='form')
    tracked = await track_keyboard(database.conn, original, 101)
    again = await track_keyboard(database.conn, tracked, 101)
    await database.conn.commit()
    url = again.inline_keyboard[0][0].web_app.url
    assert url == tracked.inline_keyboard[0][0].web_app.url
    assert 'nb=' not in original.inline_keyboard[0][0].web_app.url
    query = parse_qs(urlsplit(url).query)
    assert query['tab'] == ['form']
    body = {'token': query['nb'][0], 'path': '/predictions', 'event_id': str(uuid.uuid4())}
    assert (await client.post('/api/analytics/notification-entry', json=body)).status_code == 200
    assert (await client.post('/api/analytics/notification-entry', json=body)).status_code == 200
    assert (await client.post('/api/analytics/notification-entry', json={**body, 'path': '/wiki'})).status_code == 400
    report = await clicks.report(database.conn, 0)
    assert report['summary']['arrivals'] == 1
    assert report['items'][0]['label'].startswith('🔮 Мой прогноз')
    external = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Внешний сайт', url='https://external.test/wiki'),
    ]])
    assert (await track_keyboard(database.conn, external)).inline_keyboard[0][0].url == 'https://external.test/wiki'


@pytest.mark.asyncio
async def test_global_middleware_keeps_broadcast_callback_counted_once(tracking):
    from aiogram.types import CallbackQuery
    from app.middlewares.button_analytics import record_button
    database, _, _ = tracking
    keyboard = await prediction_keyboard()
    await outbox.enqueue('prediction:results:2026:16', 'Results', keyboard, [(101, 'UTC')], time.time()+3600)
    await database.conn.execute("UPDATE telegram_deliveries SET status='sent',message_id=10")
    await database.conn.commit()
    callback = CallbackQuery.model_validate({'id': 'broadcast-click', 'chat_instance': 'x',
        'from': {'id': 101, 'is_bot': False, 'first_name': 'Test'}, 'data': 'personal:review:2026:16',
        'message': {'message_id': 10, 'date': int(time.time()), 'chat': {'id': 101, 'type': 'private'},
                    'reply_markup': keyboard.model_dump()}})
    await record_button(callback)
    await clicks.record_callback(callback, 'review', 1)
    report = await clicks.report(database.conn, 0)
    assert report['summary']['callbacks'] == 1
    assert next(item for item in report['items'] if item['button'] == 'review')['clicks'] == 1


@pytest.mark.asyncio
async def test_tracking_failure_does_not_block_bot_handlers_or_sends(monkeypatch):
    from aiogram.methods import SendMessage
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.middlewares.button_analytics import IncomingButtonAnalytics, OutgoingButtonAnalytics
    monkeypatch.setattr(clicks, 'connection', lambda: (_ for _ in ()).throw(RuntimeError('database unavailable')))
    handler = AsyncMock(return_value='handled')
    assert await IncomingButtonAnalytics()(handler, SimpleNamespace(from_user=SimpleNamespace(is_bot=False)), {}) == 'handled'
    send = AsyncMock(return_value='sent')
    method = SendMessage(chat_id=101, text='Hi', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Button', callback_data='new'),
    ]]))
    assert await OutgoingButtonAnalytics()(send, None, method) == 'sent'
    assert send.call_args.args[1] is method


@pytest.mark.asyncio
async def test_outgoing_middleware_tracks_app_menu_and_preserves_broadcast_links(tracking):
    from aiogram.methods import SetChatMenuButton, SendMessage
    from aiogram.types import MenuButtonWebApp, WebAppInfo
    from app.middlewares.button_analytics import OutgoingButtonAnalytics
    database, _, _ = tracking
    send = AsyncMock(return_value=True)
    menu = SetChatMenuButton(menu_button=MenuButtonWebApp(text='F1Hub', web_app=WebAppInfo(url='https://example.test')))
    await OutgoingButtonAnalytics()(send, None, menu)
    assert 'nb=' in send.call_args.args[1].menu_button.web_app.url
    assert 'nb=' not in menu.menu_button.web_app.url
    original = await prediction_keyboard()
    key = 'prediction:results:2026:16'
    tracked = await clicks.tracked_keyboard(database.conn, key, original)
    await database.conn.commit()
    await OutgoingButtonAnalytics()(send, None, SendMessage(chat_id=101, text='Results', reply_markup=tracked))
    assert send.call_args.args[1].reply_markup == tracked
    report = await clicks.report(database.conn, 0)
    assert len(report['items']) == 4  # Three campaign buttons plus the app menu.
