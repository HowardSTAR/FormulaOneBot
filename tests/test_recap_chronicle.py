"""Invented race-control records; no live requests, scoring or Telegram sends."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.db import Database
from app.services import recap_chronicle as chronicle, recap_news as news, race_recap as recap
from app.utils.telegram_presentation import race_card, race_fallback

NOW = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
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
    assert rows[0]['title'] == 'Круг 3: ' + chronicle.SC_TEXT
    assert 'остановлена' not in rows[0]['title']  # SC is not a red flag.
    assert rows[2]['title'] == 'Круг 10: ' + chronicle.RED_TEXT
    assert rows[-1]['title'] == 'После финиша: Test Driver получил 10-секундный штраф за провоцирование столкновения.'
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


def set_clock(monkeypatch, now):
    monkeypatch.setattr(chronicle, 'datetime', SimpleNamespace(now=lambda zone: now, fromisoformat=datetime.fromisoformat, fromtimestamp=datetime.fromtimestamp))


def mock_background(monkeypatch, messages=None, *, now=NOW):
    from app import f1_data
    set_clock(monkeypatch, now)
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


@pytest.mark.parametrize('reason,expected', [
    ('CAUSING A COLLISION (16:11:31)', 'за провоцирование столкновения'),
    ('SPEEDING IN PIT LANE', 'за превышение скорости на пит-лейне'),
    ('LEAVING THE TRACK AND GAINING AN ADVANTAGE', 'за выезд за пределы трассы с получением преимущества'),
    ("FAILING TO FOLLOW RACE DIRECTOR'S INSTRUCTIONS", 'за невыполнение указаний дирекции гонки'),
    ('UNKNOWN REASON', None),
])
def test_only_explicit_recognised_penalty_reasons_are_translated(reason, expected):
    row = message('FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 43 (TST) - ' + reason, '13:10:00')
    title = chronicle.build_chronicle(SESSION, [*BOUNDARIES, row], DRIVERS, NOW)[0]['title']
    assert 'получил 10-секундный штраф' in title
    if expected:
        assert expected in title
    else:
        assert title == 'После финиша: Test Driver получил 10-секундный штраф.'


def test_safety_context_is_detail_not_an_inferred_cause_or_driver():
    messages = [*BOUNDARIES, EVENTS[0],
                message('RECOVERY VEHICLE ON TRACK AT TURN 6', '11:12:00'),
                message('MARSHALS ON TRACK AT TURN 6', '11:13:00'),
                message('MARSHALS ON TRACK AT TURN 8', '11:14:00'),
                message('ALL CARS THROUGH THE PIT LANE', '11:11:00'),
                message('CAR 43 RETIRED', '11:10:15')]
    title = chronicle.build_chronicle(SESSION, messages, DRIVERS, NOW)[0]['title']
    assert 'в повороте 6 работала эвакуационная техника' in title
    assert 'в повороте 8 работали маршалы' in title
    assert 'маршалы' in title and 'машины' not in title  # Two distinct, specific details.
    assert 'из-за' not in title and 'Test Driver' not in title and 'столкновени' not in title


@pytest.mark.parametrize('row', [
    message('RECOVERY VEHICLE ON TRACK AT TURN 6', '11:09:00'),
    message('RECOVERY VEHICLE ON TRACK AT TURN 6', '11:20:00'),
    message('RECOVERY VEHICLE ON TRACK AT TURN 6', '11:12:00', session_key=15001),
    message('RECOVERY VEHICLE ON TRACK AT TURN 6', '11:12:00', category='Flag'),
])
def test_context_outside_this_deployment_is_ignored(row):
    title = chronicle.build_chronicle(SESSION, [*BOUNDARIES, EVENTS[0], row], DRIVERS, NOW)[0]['title']
    assert title == 'Круг 3: ' + chronicle.SC_TEXT


def test_context_stops_when_safety_car_was_called_in():
    messages = [*BOUNDARIES, EVENTS[0], message('SAFETY CAR IN THIS LAP', '11:11:00', 'SafetyCar'),
                message('MARSHALS ON TRACK AT TURN 1', '11:12:00')]
    assert chronicle.build_chronicle(SESSION, messages, DRIVERS, NOW)[0]['title'] == 'Круг 3: ' + chronicle.SC_TEXT


def test_pit_lane_context_and_explicit_deployment_cause():
    row = message('SAFETY CAR DEPLOYED - DEBRIS ON TRACK', category='SafetyCar')
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, row,
        message('ALL CARS THROUGH THE PIT LANE', '11:11:00')], DRIVERS, NOW)
    assert 'из-за обломков на трассе' in rows[0]['title']
    assert 'машины направили через пит-лейн' in rows[0]['title']


@pytest.mark.parametrize('old,new', [
    (chronicle.LEGACY_SC_TEXT, chronicle.SC_TEXT),
    (chronicle.PREVIOUS_SC_TEXT, chronicle.SC_TEXT),
    ('Включён VSC — пилоты обязаны соблюдать заданный темп.', chronicle.VSC_TEXT),
    ('Красный флаг — гонка остановлена.', chronicle.RED_TEXT),
    ('Test Driver: объявлен временной штраф — 10 сек.', 'Test Driver получил 10-секундный штраф.'),
])
def test_existing_generated_titles_switch_to_past_tense_not_rss_headlines(old, new):
    assert chronicle.display_title('Круг 3: ' + old) == 'Круг 3: ' + new
    assert chronicle.display_title(old, 'autosport') == old


async def test_hourly_refresh_and_late_penalty_preserve_moderation(database, monkeypatch):
    first = datetime(2026, 9, 26, 14, tzinfo=timezone.utc)
    fetch = mock_background(monkeypatch, [*BOUNDARIES, EVENTS[0]], now=first)
    await chronicle._refresh_recent_race_control()
    check = await (await database.conn.execute('SELECT * FROM recap_control_checks')).fetchone()
    assert check['final'] == 0 and check['next_check'] == first.timestamp() + 3600
    await database.conn.execute("UPDATE recap_news_articles SET hidden=1 WHERE category='sc'")
    await database.conn.commit()
    set_clock(monkeypatch, first + timedelta(minutes=16))
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2  # No repeated download before the stage's next check.
    late = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
    penalty = {**EVENTS[-1], 'date': '2026-09-28T10:00:00Z'}
    fetch = mock_background(monkeypatch, [*BOUNDARIES, EVENTS[0], penalty], now=late)
    await chronicle._refresh_recent_race_control()
    result = await chronicle.public_chronicle(2026, 15)
    assert len(result) == 1 and 'за провоцирование столкновения' in result[0]['title']
    assert (await (await database.conn.execute('SELECT COUNT(*) FROM recap_news_articles')).fetchone())[0] == 2
    check = await (await database.conn.execute('SELECT * FROM recap_control_checks')).fetchone()
    assert check['final'] == 0 and check['next_check'] == late.timestamp() + 6 * 3600


def relocated_fixture(date, key):
    session = {**SESSION, 'session_key': key,
               'date_start': SESSION['date_start'].replace('2026-09-26', date),
               'date_end': SESSION['date_end'].replace('2026-09-26', date)}
    messages = [{**row, 'session_key': key, 'date': row['date'].replace('2026-09-26', date)}
                for row in [*BOUNDARIES, *EVENTS]]
    drivers = [{**row, 'session_key': key} for row in DRIVERS]
    return session, messages, drivers


async def test_next_round_is_loaded_after_previous_round_was_finalised(database, monkeypatch):
    from app import f1_data
    mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    now = NOW + timedelta(minutes=16)
    set_clock(monkeypatch, now)
    session, messages, drivers = relocated_fixture('2026-10-03', 15001)
    event = {**EVENT, 'round': 16, 'race_start_utc': session['date_start']}
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', AsyncMock(return_value=[EVENT, event]))
    monkeypatch.setattr(chronicle, '_cached_prediction_openf1_sessions', AsyncMock(return_value=[SESSION, session]))
    async def fetch(path, **params):
        assert params['session_key'] == 15001
        return messages if path == 'race_control' else drivers
    fetch = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', fetch)
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2
    assert len(await chronicle.public_chronicle(2026, 16)) == 4
    assert len(await chronicle.public_chronicle(2026, 15)) == 4
    checks = await (await database.conn.execute('SELECT round,final FROM recap_control_checks ORDER BY round')).fetchall()
    assert [(row['round'], row['final']) for row in checks] == [(15, 1), (16, 0)]


async def test_new_parser_refetches_old_final_snapshot_once(database, monkeypatch):
    now = datetime(2026, 9, 27, 14, tzinfo=timezone.utc)
    fetch = mock_background(monkeypatch, now=now)
    await database.conn.execute('INSERT INTO recap_control_checks(season,round,session_key,updated,next_check,final) VALUES(2026,15,15000,?,?,1)',
                                (now.timestamp(), now.timestamp() + 86400))
    await database.conn.commit()
    await chronicle._refresh_recent_race_control()
    check = await (await database.conn.execute('SELECT * FROM recap_control_checks')).fetchone()
    assert check['parser_version'] == chronicle.PARSER_VERSION and check['final'] == 0
    assert any('за провоцирование столкновения' in row['title'] for row in await chronicle.public_chronicle(2026, 15))
    await chronicle._refresh_recent_race_control()
    assert fetch.await_count == 2


async def test_previous_season_race_keeps_its_year_at_new_year(database, monkeypatch):
    from app import f1_data
    now = datetime(2027, 1, 1, 14, tzinfo=timezone.utc)
    set_clock(monkeypatch, now)
    session, messages, drivers = relocated_fixture('2026-12-31', 16000)
    event = {**EVENT, 'race_start_utc': session['date_start']}
    schedule = AsyncMock(side_effect=lambda year: [event] if year == 2026 else [])
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', schedule)
    sessions = AsyncMock(return_value=[session])
    monkeypatch.setattr(chronicle, '_cached_prediction_openf1_sessions', sessions)
    async def fetch(path, **params):
        assert params['session_key'] == 16000
        return messages if path == 'race_control' else drivers
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', AsyncMock(side_effect=fetch))
    await chronicle._refresh_recent_race_control()
    sessions.assert_awaited_once_with(2026)
    assert len(await chronicle.public_chronicle(2026, 15)) == 4
    assert await chronicle.public_chronicle(2027, 15) == []


async def test_legacy_check_schema_migration_keeps_existing_snapshot(temp_db_path):
    import aiosqlite
    async with aiosqlite.connect(temp_db_path) as conn:
        await conn.execute('CREATE TABLE recap_control_checks(season INTEGER,round INTEGER,session_key INTEGER,updated REAL,next_check REAL,final INTEGER,PRIMARY KEY(season,round))')
        await conn.execute('INSERT INTO recap_control_checks VALUES(2026,15,15000,1,2,1)')
        await conn.commit()
        await news.ensure_schema(conn)
        await conn.commit()
        row = await (await conn.execute('SELECT * FROM recap_control_checks')).fetchone()
        assert row == (2026, 15, 15000, 1, 2, 1, 0)
        await news.ensure_schema(conn)
        assert (await (await conn.execute('SELECT COUNT(*) FROM recap_control_checks')).fetchone())[0] == 1


async def test_bot_and_web_schema_migration_can_overlap(temp_db_path):
    import asyncio
    import aiosqlite
    async with aiosqlite.connect(temp_db_path) as conn:
        await conn.execute('CREATE TABLE recap_control_checks(season INTEGER,round INTEGER,session_key INTEGER,updated REAL,next_check REAL,final INTEGER,PRIMARY KEY(season,round))')
        await conn.commit()
    async def startup():
        async with aiosqlite.connect(temp_db_path, timeout=5) as conn:
            await news.ensure_schema(conn)
            await conn.commit()
    await asyncio.gather(startup(), startup())
    async with aiosqlite.connect(temp_db_path) as conn:
        columns = await (await conn.execute('PRAGMA table_info(recap_control_checks)')).fetchall()
        assert [column[1] for column in columns].count('parser_version') == 1


async def test_retry_after_rate_limit_recovers_without_requiring_admin(database, monkeypatch):
    mock_background(monkeypatch)
    async def limited(path, *, diagnostics=None, **params):
        diagnostics['http_status'] = 429
        return None
    limited_fetch = AsyncMock(side_effect=limited)
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', limited_fetch)
    await chronicle._refresh_recent_race_control()
    await chronicle._refresh_recent_race_control()
    assert limited_fetch.await_count == 1  # Persisted cooldown, no immediate retry loop.
    good_fetch = mock_background(monkeypatch, now=NOW + timedelta(minutes=16))
    await chronicle._refresh_recent_race_control()
    assert good_fetch.await_count == 2
    assert len(await chronicle.public_chronicle(2026, 15)) == 4
    source = await (await database.conn.execute('SELECT * FROM recap_news_sources WHERE source_id=?', (chronicle.SOURCE,))).fetchone()
    assert source['error'] is None and source['failures'] == 0 and source['successful'] is not None


async def test_recap_cache_and_waiting_do_not_gain_unconfirmed_events(database, monkeypatch):
    mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    original = {'status': 'ready', 'items': []}
    monkeypatch.setattr(recap, 'get_race_recap', AsyncMock(return_value=original))
    result = await recap.get_race_recap_with_news(2026, 15)
    assert result['chronicle'] and 'chronicle' not in original
    original['status'] = 'waiting'
    assert not (await recap.get_race_recap_with_news(2026, 15))['chronicle']


async def test_final_stored_sc_wording_updates_without_refetch_or_database_write(database, monkeypatch):
    mock_background(monkeypatch)
    await chronicle._refresh_recent_race_control()
    old_title = 'Круг 3: ' + chronicle.LEGACY_SC_TEXT
    await database.conn.execute("UPDATE recap_news_articles SET title=? WHERE category='sc'", (old_title,))
    await database.conn.commit()
    fetch = AsyncMock(side_effect=AssertionError('No refetch for a wording change'))
    monkeypatch.setattr(chronicle, '_prediction_openf1_get', fetch)
    result = await chronicle.public_chronicle(2026, 15)
    assert result[0]['title'] == 'Круг 3: ' + chronicle.SC_TEXT
    stored = await (await database.conn.execute("SELECT title FROM recap_news_articles WHERE category='sc'")).fetchone()
    assert stored['title'] == old_title
    assert chronicle.display_title(old_title, 'autosport') == old_title
    fetch.assert_not_awaited()


def test_telegram_presentations_and_spoilers_include_chronicle():
    rows = chronicle.build_chronicle(SESSION, [*BOUNDARIES, *EVENTS], DRIVERS, NOW)
    data = {'status': 'ready', 'items': [], 'chronicle': [{**row, 'publisher': 'OpenF1'} for row in rows]}
    assert 'Ключевые события гонки' in recap.format_recap_telegram(data, spoiler=True)
    assert 'tg-spoiler' in recap.format_recap_telegram(data, spoiler=True)
    for rendered in (recap.format_recap_telegram(data), race_card('Baku', 2026, 15, [], data).model_dump_json(),
                     race_fallback('Baku', 2026, 15, [], data)):
        assert 'Журнал дирекции' not in rendered
        assert 'api.openf1.org' not in rendered
        assert 'Ключевые события гонки' in rendered
    assert 'После финиша' in race_fallback('Baku', 2026, 15, [], data)
