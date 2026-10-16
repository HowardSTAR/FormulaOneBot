"""Prediction results recover after downtime using durable queues and saved scores."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest
import pytest_asyncio

from app.services import prediction_notifications as n
from app.services.prediction_service import get_notification_state, mark_notification_state
from app.services.telegram_outbox import delivery_counts, drain, enqueue


@pytest_asyncio.fixture
async def prediction_delivery(db_session, monkeypatch):
    now = datetime.now(timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(n, 'datetime', FrozenDateTime)
    event = {'round': 17, 'event_name': 'Delivery GP',
             'race_start_utc': (now - timedelta(hours=4)).isoformat()}
    monkeypatch.setattr(n, 'get_season_schedule_short_async', AsyncMock(return_value=[event]))
    monkeypatch.setattr(n, 'get_users_with_settings', AsyncMock(return_value=[(12345, 'UTC')]))
    monkeypatch.setattr(n, 'mini_app_button', AsyncMock(return_value=None))
    codes = ['VER', 'NOR', 'PIA', 'LEC', 'HAM', 'RUS', 'ALO', 'SAI', 'STR', 'ANT']
    race = pd.DataFrame([{'Position': i + 1, 'Abbreviation': code,
                          'Points': 25 if i == 0 else 0, 'DataComplete': True}
                         for i, code in enumerate(codes)])
    monkeypatch.setattr(n, 'get_race_results_async', AsyncMock(return_value=race))
    monkeypatch.setattr(n, 'get_quali_for_round_async', AsyncMock(return_value=(None, [{'position': 1, 'driver': 'VER'}])))
    monkeypatch.setattr(n, 'get_prediction_race_facts', AsyncMock(return_value={
        'fastest_lap_driver': 'HAM', 'first_retirement_driver': 'STR', 'safety_car': 0}))
    await db_session.conn.execute('INSERT INTO users(id,telegram_id) VALUES(1,12345)')
    await db_session.conn.execute("INSERT INTO prediction_profiles(user_id,display_name) VALUES(1,'Test Fan')")
    await db_session.conn.execute(
        '''INSERT INTO race_predictions(user_id,season,round,pole_driver,winner_driver,
           second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
           first_retirement_driver,safety_car)
           VALUES(1,?,17,'VER','VER','NOR','PIA','LEC','HAM','HAM','STR',0)''', (now.year,))
    await db_session.conn.execute('INSERT INTO web_notification_members VALUES(1,?)', (now.timestamp() - 60,))
    await db_session.conn.commit()
    await mark_notification_state(now.year, 17, 'opened_sent')
    await mark_notification_state(now.year, 17, 'closing_sent')
    bot = AsyncMock()
    bot.send_message.return_value.message_id = 42
    return db_session, now, event, bot


async def saved_score(database, season, *, complete=True):
    await database.conn.execute(
        '''INSERT INTO prediction_round_results(season,round,event_name,pole_driver,winner_driver,
           second_driver,third_driver,fourth_driver,fifth_driver,fastest_lap_driver,
           first_retirement_driver,safety_car,max_points)
           VALUES(?,17,'Delivery GP','VER','VER','NOR','PIA','LEC','HAM',?,'STR',0,37)''',
        (season, 'HAM' if complete else None))
    # A historic total must not be replaced by today's scoring rules or API data.
    await database.conn.execute(
        'UPDATE race_predictions SET points=17,max_points=37,breakdown_json=?', ('[]',))
    await database.conn.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('age', [timedelta(hours=4), timedelta(days=7)])
async def test_recent_results_send_after_restart_once_in_both_channels(prediction_delivery, age):
    database, now, event, bot = prediction_delivery
    event['race_start_utc'] = (now - age).isoformat()
    for _ in range(2):
        await n.check_and_notify_predictions(bot, not_before=now - timedelta(minutes=1))
    bot.send_message.assert_awaited_once()
    assert 'Итоги прогнозов' in bot.send_message.await_args.kwargs['text']
    assert 'Test Fan' in bot.send_message.await_args.kwargs['text']
    assert (await get_notification_state(now.year, 17))['results_sent']
    assert await delivery_counts(f'prediction:results:{now.year}:17') == {'sent': 1}
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM web_notifications')).fetchone())[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_sent', [False, True])
@pytest.mark.parametrize('complete', [False, True])
async def test_saved_results_recover_without_api_or_rescoring(prediction_delivery, monkeypatch, legacy_sent, complete):
    database, now, _, bot = prediction_delivery
    await saved_score(database, now.year, complete=complete)
    if legacy_sent:
        await mark_notification_state(now.year, 17, 'results_sent')
    score = AsyncMock(side_effect=AssertionError('Saved totals must be preserved'))
    monkeypatch.setattr(n, 'score_prediction_round', score)
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.kwargs['text']
    assert '17/37' in text
    assert ('Предварительные итоги' in text) is (not complete)
    n.get_race_results_async.assert_not_awaited()
    n.get_prediction_race_facts.assert_not_awaited()
    score.assert_not_awaited()
    row = await (await database.conn.execute('SELECT points,max_points,breakdown_json FROM race_predictions')).fetchone()
    assert tuple(row) == (17, 37, '[]')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['results', 'results-updated', 'results-manual'])
@pytest.mark.parametrize('legacy_sent', [False, True])
async def test_existing_queue_resumes_without_duplicate_broadcast(prediction_delivery, kind, legacy_sent):
    database, now, _, bot = prediction_delivery
    key = f'prediction:{kind}:{now.year}:17' + (':fingerprint' if kind == 'results-manual' else '')
    await enqueue(key, 'Saved broadcast', None, [(12345, 'UTC')], (now + timedelta(days=1)).timestamp())
    if legacy_sent:
        await mark_notification_state(now.year, 17, 'results_sent')
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_not_awaited()
    n.get_race_results_async.assert_not_awaited()
    assert (await get_notification_state(now.year, 17))['results_sent']
    await drain(bot)
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs['text'] == 'Saved broadcast'
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM telegram_delivery_batches')).fetchone())[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_sent', [False, True])
async def test_old_results_do_not_broadcast_after_restart(prediction_delivery, legacy_sent):
    database, now, event, bot = prediction_delivery
    event['race_start_utc'] = (now - timedelta(days=7, seconds=1)).isoformat()
    await saved_score(database, now.year)
    if legacy_sent:
        await mark_notification_state(now.year, 17, 'results_sent')
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_not_awaited()
    assert (await get_notification_state(now.year, 17))['results_sent']
    assert await delivery_counts(f'prediction:results:{now.year}:17') == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_data', ['missing', 'live', 'zero-points'])
async def test_results_wait_for_complete_classification_then_retry(prediction_delivery, bad_data):
    _, now, _, bot = prediction_delivery
    original = n.get_race_results_async.return_value
    incomplete = original.copy()
    if bad_data == 'live':
        incomplete['DataComplete'] = False
    elif bad_data == 'zero-points':
        incomplete['Points'] = 0
    else:
        incomplete = None
    n.get_race_results_async.return_value = incomplete
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_not_awaited()
    assert not (await get_notification_state(now.year, 17))['results_sent']
    n.get_race_results_async.return_value = original
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_failure_retries_saved_score_after_restart(prediction_delivery, monkeypatch):
    _, now, _, bot = prediction_delivery
    original = n.enqueue
    monkeypatch.setattr(n, 'enqueue', AsyncMock(side_effect=RuntimeError('Queue unavailable')))
    with pytest.raises(RuntimeError, match='Queue unavailable'):
        await n.check_and_notify_predictions(bot, not_before=now)
    assert not (await get_notification_state(now.year, 17))['results_sent']
    bot.send_message.assert_not_awaited()
    monkeypatch.setattr(n, 'enqueue', original)
    await n.check_and_notify_predictions(bot, not_before=now)
    bot.send_message.assert_awaited_once()
    n.get_race_results_async.assert_awaited_once()
