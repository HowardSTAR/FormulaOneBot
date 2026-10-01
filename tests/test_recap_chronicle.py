"""Invented race-control records; no live requests, scoring or Telegram sends."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.db import Database
from app.services import recap_chronicle as chronicle, recap_news as news, race_recap as recap
from app.utils.telegram_presentation import race_card, race_fallback

NOW = datetime(2026, 9, 27, 14, tzinfo=timezone.utc)
EVENT = {'round': 15, 'event_name': 'Azerbaijan Grand Prix', 'race_start_utc': '2026-09-26T11:00:00Z'}
SESSION = {'session_key': 15000, 'session_type': 'Race', 'session_name': 'Race',
           'date_start': EVENT['race_start_utc'], 'date_end': '2026-09-26T13:00:00Z'}
DRIVERS = [{'session_key': 15000, 'driver_number': 43, 'full_name': 'Test Driver'}]


def message(text, date='11:10:00', category='Other', **extra):
    return {'session_key': 15000, 'date': f'2026-09-26T{date}Z', 'message': text,
            'category': category, 'lap_number': 3, **extra}


BOUNDARIES = [message('SESSION STARTED', '11:05:00', 'SessionStatus'),
              message('CHEQUERED FLAG', '12:45:00', 'Flag', flag='CHEQUERED')]
EVENTS = [message('SAFETY CAR DEPLOYED', category='SafetyCar'),
          message('VIRTUAL SAFETY CAR DEPLOYED', '11:20:00', 'SafetyCar', lap_number=7),
          message('RED FLAG', '11:30:00', 'Flag', flag='RED', scope='Track', lap_number=10),
          message('FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 43 (TST) - CAUSING A COLLISION', '13:10:00', lap_number=51)]


@pytest_asyncio.fixture
async def database(temp_db_path, monkeypatch):
    value = Database(temp_db_path)
    await value.connect()
    try:
        await value.init_tables()
        monkeypatch.setattr(news, 'db', value)
        yield value
    finally:
        await value.close()


def test_templates_chronology_and_after_finish_penalty():
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, *reversed(EVENTS)], DRIVERS, NOW)
    assert [row['category'] for row in rows] == ['sc', 'vsc', 'red_flag', 'penalty']
    assert 'Круг 3:' in rows[0]['title'] and 'нейтрализована' in rows[0]['title']
    assert rows[-1]['title'] == 'После финиша: Test Driver: объявлен временной штраф — 10 сек.'
    assert all(news.canonical_url(row['url'], news.FEED_BY_ID[chronicle.SOURCE]) for row in rows)
    assert not any('CAUSING' in row['title'] for row in rows)


@pytest.mark.parametrize('row', [
    message('SAFETY CAR DEPLOYED', '11:02:00', 'SafetyCar'),
    message('SAFETY CAR DEPLOYED', '13:20:00', 'SafetyCar'),
    message('SAFETY CAR IN THIS LAP', category='SafetyCar'),
    message('VIRTUAL SAFETY CAR ENDING', category='SafetyCar'),
    message('RED FLAG', '11:30:00', 'Flag', flag='RED', scope='Sector'),
    message('YELLOW FLAG', '11:30:00', 'Flag', flag='YELLOW', scope='Track'),
    message('FIA STEWARDS: CAR 43 UNDER INVESTIGATION - POSSIBLE TIME PENALTY'),
    message('FIA STEWARDS: NO FURTHER ACTION FOR CAR 43'),
    message('10 SECOND TIME PENALTY FOR CAR 43 RESCINDED'),
    message('10 SECOND TIME PENALTY FOR CAR 43 UNDER INVESTIGATION'),
    message('SAFETY CAR DEPLOYED', category='SafetyCar', session_key=15001),
    message('SAFETY CAR DEPLOYED', category='SafetyCar', date='2025-09-26T11:10:00Z'),
    message('SAFETY CAR DEPLOYED', category='SafetyCar', date='invalid'),
], ids=['formation-lap', 'post-race-sc', 'sc-ending', 'vsc-ending', 'sector-red', 'yellow',
         'investigation', 'no-action', 'rescinded', 'penalty-investigation', 'wrong-session', 'wrong-year', 'bad-date'])
def test_ambiguous_or_irrelevant_messages_are_not_stories(row):
    assert chronicle.build_chronicle(SESSION, [*BOUNDARIES, row], DRIVERS, NOW) == []


@pytest.mark.parametrize('session,rows,now', [
    (SESSION, EVENTS, NOW), (SESSION, BOUNDARIES[:1], NOW),
    ({**SESSION, 'session_type': 'Qualifying'}, BOUNDARIES, NOW),
    ({**SESSION, 'is_cancelled': True}, BOUNDARIES, NOW),
    ({**SESSION, 'date_end': None}, BOUNDARIES, NOW),
    (SESSION, BOUNDARIES, datetime(2026, 9, 26, 12, tzinfo=timezone.utc)),
])
def test_unfinished_or_unconfirmed_session_is_not_a_recap(session, rows, now):
    assert chronicle.build_chronicle(session, rows, DRIVERS, now) is None


def test_names_are_session_scoped_no_static_driver_number_guess():
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, EVENTS[-1]],
                                     [{**DRIVERS[0], 'session_key': 99999}], NOW)
    assert 'Машина №43' in rows[0]['title'] and 'Test Driver' not in rows[0]['title']


def test_event_selection_keeps_diverse_topics_then_time_order():
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, *EVENTS,
        *[message('SAFETY CAR DEPLOYED', f'12:{minute}:00', 'SafetyCar', lap_number=minute) for minute in (10, 20, 30)]], DRIVERS, NOW)
    selected = chronicle.select_events([*rows, rows[0]])
    assert len(selected) == 4
    assert {row['category'] for row in selected} == {'sc', 'vsc', 'red_flag', 'penalty'}
    assert [row['published'] for row in selected] == sorted(row['published'] for row in selected)


@pytest.mark.parametrize('url', [
    'https://api.openf1.org/v1/race_control?session_key=latest#event-0123456789abcdef',
    'https://api.openf1.org/v1/race_control?session_key=15000&other=1#event-0123456789abcdef',
    'https://api.openf1.org/v1/drivers?session_key=15000#event-0123456789abcdef',
    'https://api.openf1.org.evil.test/v1/race_control?session_key=15000#event-0123456789abcdef',
])
def test_control_source_links_are_restricted(url):
    assert news.canonical_url(url, news.FEED_BY_ID[chronicle.SOURCE]) is None


def mock_background(monkeypatch, messages=None):
    from app import f1_data
    monkeypatch.setattr(chronicle, 'datetime', SimpleNamespace(now=lambda zone: NOW, fromisoformat=datetime.fromisoformat, fromtimestamp=datetime.fromtimestamp))
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', AsyncMock(return_value=[EVENT]))
    monkeypatch.setattr(chronicle, '_cached_prediction_openf1_sessions', AsyncMock(return_value=[
        {**SESSION, 'session_key': 14999, 'session_type': 'Qualifying', 'date_start': '2026-09-25T11:00:00Z'}, SESSION]))
    async def fetch(path, *, diagnostics=None, **params):
        assert params == {'session_key': 15000}
        return ([*BOUNDARIES, *EVENTS] if messages is None else messages) if path == 'race_control' else DRIVERS
    mocked = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', mocked)
    return mocked


async def test_background_persistence_read_only_public_and_final_no_refetch(database, monkeypatch):
    fetch = mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    assert [call.args[0] for call in fetch.await_args_list] == ['race_control', 'drivers']
    fetch.side_effect = AssertionError('Public readers cannot fetch OpenF1')
    result = await chronicle.public_chronicle(2026, 15)
    assert len(result) == 4 and result[0]['publisher'] == 'OpenF1'
    assert await news.public_news(2026, 15) == []  # Own templates are not publisher headlines.
    assert await chronicle.public_chronicle(2026, 14) == []
    await database.conn.execute('UPDATE recap_news_sources SET next_check=0 WHERE source_id=?', (chronicle.SOURCE,))
    await database.conn.commit()
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2  # Final snapshot is persisted, including across worker restarts.
    row = await (await database.conn.execute('SELECT * FROM recap_control_checks')).fetchone()
    assert row['final'] == 1 and row['session_key'] == 15000
    for table in ('race_predictions', 'prediction_round_results', 'telegram_deliveries'):
        assert (await (await database.conn.execute(f'SELECT COUNT(*) FROM {table}')).fetchone())[0] == 0


async def test_quiet_race_is_cached_without_fabricating_absence_claims(database, monkeypatch):
    fetch = mock_background(monkeypatch, BOUNDARIES)
    await chronicle._refresh_recent_race_control()
    assert await chronicle.public_chronicle(2026, 15) == []
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM recap_control_checks')).fetchone())[0] == 1
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2


async def test_rate_limit_stops_requests_backs_off_and_retains_events(database, monkeypatch):
    mock_background(monkeypatch)
    entries = chronicle.build_chronicle(SESSION, [*BOUNDARIES, *EVENTS], DRIVERS, NOW)
    await news.save_candidates(database.conn, entries, EVENT, 2026, NOW)
    await database.conn.commit()
    async def limited(path, *, diagnostics=None, **params):
        diagnostics['http_status'] = 429
        return None
    fetch = AsyncMock(side_effect=limited)
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', fetch)
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 1
    state = await (await database.conn.execute('SELECT * FROM recap_news_sources WHERE source_id=?', (chronicle.SOURCE,))).fetchone()
    assert state['error'] == 'OpenF1: HTTP 429' and state['next_check'] > NOW.timestamp()
    assert len(await chronicle.public_chronicle(2026, 15)) == 4


async def test_disabled_source_and_hidden_events_are_immediate(database, monkeypatch):
    fetch = mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    await database.conn.execute("UPDATE recap_news_articles SET hidden=1 WHERE category='penalty'")
    await database.conn.commit()
    assert len(await chronicle.public_chronicle(2026, 15)) == 3
    await database.conn.execute('UPDATE recap_news_sources SET enabled=0 WHERE source_id=?', (chronicle.SOURCE,))
    await database.conn.commit()
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2
    assert await chronicle.public_chronicle(2026, 15) == []


async def test_sessions_failure_visible_without_requests(database, monkeypatch):
    fetch = mock_background(monkeypatch)
    monkeypatch.setattr(chronicle, '_cached_prediction_openf1_sessions', AsyncMock(side_effect=chronicle.OpenF1SourceUnavailable('OpenF1: список сессий (HTTP 429)')))
    await chronicle._refresh_recent_race_control()
    state = await (await database.conn.execute('SELECT * FROM recap_news_sources WHERE source_id=?', (chronicle.SOURCE,))).fetchone()
    assert 'HTTP 429' in state['error']
    fetch.assert_not_awaited()


async def test_recap_cache_and_waiting_do_not_gain_unconfirmed_events(database, monkeypatch):
    mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    original = {'status': 'ready', 'items': []}
    monkeypatch.setattr(recap, 'get_race_recap', AsyncMock(return_value=original))
    result = await recap.get_race_recap_with_news(2026, 15)
    assert result['chronicle'] and 'chronicle' not in original
    original['status'] = 'waiting'
    assert not (await recap.get_race_recap_with_news(2026, 15))['chronicle']


def test_telegram_presentations_and_spoilers_include_chronicle():
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, *EVENTS], DRIVERS, NOW)
    data = {'status': 'ready', 'items': [], 'chronicle': [{**row, 'publisher': 'OpenF1'} for row in rows]}
    assert 'Ключевые события гонки' in recap.format_recap_telegram(data, spoiler=True)
    assert 'tg-spoiler' in recap.format_recap_telegram(data, spoiler=True)
    assert 'Журнал дирекции · OpenF1' in race_card('Baku', 2026, 15, [], data).model_dump_json()
    assert 'После финиша' in race_fallback('Baku', 2026, 15, [], data)
