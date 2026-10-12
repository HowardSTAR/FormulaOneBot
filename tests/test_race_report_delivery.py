"""Post-race recovery and presentation with isolated data and no external sends."""
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.race_report import favorites_text
from app.utils import notifications as n


def classification():
    return pd.DataFrame([dict(Position=i + 1, Abbreviation=code, FirstName='Test', LastName=code,
                              FullName=f'Test {code}', TeamName='Red Bull' if i < 2 else 'Other',
                              Points=25 if i == 0 else 18 if i == 1 else 0, DataComplete=True)
                         for i, code in enumerate(['VER', 'HAD', 'NOR', 'PIA', 'LEC', 'HAM', 'RUS', 'ANT', 'ALO', 'SAI'])])


@pytest.fixture
def report(monkeypatch):
    event = dict(round=17, event_name='Test GP', race_status='finished',
                 race_start_utc=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat())
    drivers = pd.DataFrame([dict(driverCode='VER', points=301)])
    teams = pd.DataFrame([dict(constructorName='Red Bull Racing', points=411)])
    for name, value in {
        'get_season_schedule_short_async': [event], 'get_race_results_async': classification(),
        'get_driver_standings_async': drivers, 'get_constructor_standings_async': teams,
        'get_users_with_settings': [(111, 'UTC', 60, 1, 0, 0), (222, 'UTC', 60, 1, 0, 0)],
        'get_users_favorites_for_notifications': {111: {'drivers': ['VER'], 'teams': ['Red Bull']}},
        'get_all_group_chats': [], 'get_last_notified_voting_invite_round': 17,
        'web_classification': None, 'publish_web': None, 'mini_app_button': None,
    }.items():
        monkeypatch.setattr(n, name, AsyncMock(return_value=value))
    monkeypatch.setattr(n, 'create_f1_style_classification_image', lambda **kwargs: io.BytesIO(b'png-test'))
    return event


def test_favorites_distinguish_race_points_from_total_and_unknown():
    rows = [{'pos': 1, 'driver_code': 'VER', 'team': 'Red Bull', 'points': 12.5},
            {'pos': 2, 'driver_code': 'HAD', 'team': 'Red Bull', 'points': 9}]
    favorites = {'drivers': ['ver', 'VER'], 'teams': ['Red Bull']}
    drivers = pd.DataFrame([{'driverCode': 'VER', 'points': 201.5}])
    teams = pd.DataFrame([{'constructorName': 'Red Bull Racing', 'points': 303}])
    text = favorites_text(rows, favorites, drivers, teams, round_num=17)
    assert text.count('VER:') == 1 and '+12.5 очк. за гонку; всего 201.5 очк.' in text
    assert 'Red Bull: +21.5 очк. за гонку; всего 303 очк.' in text
    drivers.attrs['round'] = teams.attrs['round'] = 16
    pending = favorites_text(rows, favorites, drivers, teams, round_num=17)
    assert 'уточняется' in pending and '201.5' not in pending and '303' not in pending


@pytest.mark.asyncio
async def test_late_recap_retries_after_classification_and_is_deduplicated(db_session, report, monkeypatch):
    monkeypatch.setenv('TELEGRAM_RICH_MESSAGES', '1')
    ready = {'status': 'ready', 'items': [{'title': 'Winner', 'text': 'Verified result'}],
             'commentary': {'status': 'ready'}, 'chronicle': [{'title': 'Круг 8: красный флаг.'}]}
    load = AsyncMock(return_value={'status': 'partial', 'items': [], 'commentary': {'status': 'waiting'}})
    monkeypatch.setattr(n, 'get_race_recap', load)
    await n.check_and_send_results(None)
    season = datetime.now(timezone.utc).year
    assert await n.get_last_notified_round(season) == 17
    assert await n.get_last_notified_recap_round(season) is None
    await n.check_and_notify_race_recap(None)
    load.return_value = ready
    await n.check_and_notify_race_recap(None)
    await n.check_and_notify_race_recap(None)
    assert await n.get_last_notified_recap_round(season) == 17
    batches = await (await db_session.conn.execute('SELECT event_key FROM telegram_delivery_batches')).fetchall()
    assert {row[0] for row in batches} == {f'{kind}:{season}:17:{user}' for kind in ('race-photo', 'race-recap') for user in (111, 222)}
    payload = await (await db_session.conn.execute('SELECT payload FROM delivery_payloads WHERE event_key=?', (f'race-recap:{season}:17:111',))).fetchone()
    blocks = json.loads(payload[0])['actions'][0]['kwargs']['rich_message']['blocks']
    assert blocks[1]['type'] == 'photo' and blocks[2]['text']['type'] == 'spoiler'
    assert 'всего 301 очк.' in blocks[2]['text']['text'] and 'всего 411 очк.' in blocks[2]['text']['text']
    assert any('Круг 8' in str(block.get('text', '')) for block in blocks)


@pytest.mark.asyncio
async def test_race_remains_pending_when_one_recipient_cannot_be_queued(db_session, report, monkeypatch):
    monkeypatch.setenv('TELEGRAM_RICH_MESSAGES', '0')
    monkeypatch.setattr(n, 'get_race_recap', AsyncMock(return_value={'items': []}))
    monkeypatch.setattr(n, 'safe_send_photo', AsyncMock(side_effect=[True, False]))
    await n.check_and_send_results(None)
    assert await n.get_last_notified_round(datetime.now(timezone.utc).year) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('age,previous,receipt,expected', [(3, 16, False, None), (3, 17, False, 16), (3, 17, True, None), (72, 16, False, 17)])
async def test_startup_preserves_recent_race_and_recovers_false_watermark(report, monkeypatch, age, previous, receipt, expected):
    report['race_start_utc'] = (datetime.now(timezone.utc) - timedelta(hours=age)).isoformat()
    monkeypatch.setattr(n, 'get_last_notified_round', AsyncMock(return_value=previous))
    setter = AsyncMock()
    monkeypatch.setattr(n, 'set_last_notified_round', setter)
    monkeypatch.setattr(n, '_result_delivery_started', AsyncMock(return_value=receipt))
    assert await n.initialize_result_notification_state()
    if expected is None:
        setter.assert_not_awaited()
    else:
        setter.assert_awaited_once_with(datetime.now(timezone.utc).year, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize('private', [True, False])
async def test_recap_command_uses_image_and_keeps_favorites_private(report, monkeypatch, private):
    from app.handlers import insights
    event = report
    monkeypatch.setattr(insights, 'get_season_schedule_short_async', AsyncMock(return_value=[event]))
    monkeypatch.setattr(insights, 'get_race_recap', AsyncMock(return_value={'status': 'ready', 'items': [], 'note': 'test'}))
    monkeypatch.setattr(insights, 'get_race_results_async', AsyncMock(return_value=classification()))
    monkeypatch.setattr(insights, 'get_users_favorites_for_notifications', n.get_users_favorites_for_notifications)
    monkeypatch.setattr(insights, 'get_driver_standings_async', n.get_driver_standings_async)
    monkeypatch.setattr(insights, 'get_constructor_standings_async', n.get_constructor_standings_async)
    monkeypatch.setattr(insights, 'create_f1_style_classification_image', n.create_f1_style_classification_image)
    monkeypatch.setattr(insights, '_web_button', AsyncMock(return_value=None))
    send = AsyncMock()
    monkeypatch.setattr(insights, 'send_card', send)
    message = SimpleNamespace(chat=SimpleNamespace(id=111, type='private' if private else 'group'), bot=None,
                              message_thread_id=None, answer=AsyncMock())
    await insights._show_recap(message)
    card = send.await_args.args[2]
    assert card.blocks[1].type == 'photo'
    assert not any(block.type == 'table' for block in card.blocks)
    assert ('всего 301' in str(card.model_dump())) is private


@pytest.mark.asyncio
@pytest.mark.parametrize('rich', [True, False])
async def test_highlights_are_selected_per_recipient_and_groups_have_no_personal_passes(db_session, report, monkeypatch, rich):
    monkeypatch.setenv('TELEGRAM_RICH_MESSAGES', '1' if rich else '0')
    candidates = [dict(title='Crash for everyone', category='incident', score=100, published=1, url='crash', driver_code=''),
                  dict(title='Penalty for everyone', category='penalty', score=90, published=2, url='penalty', driver_code=''),
                  dict(title='VER retained pass', category='retained_overtake', score=80, published=3, url='ver', driver_code='VER'),
                  dict(title='NOR retained pass', category='retained_overtake', score=80, published=4, url='nor', driver_code='NOR')]
    monkeypatch.setattr(n, 'get_race_recap', AsyncMock(return_value={'status':'ready', 'items':[],
        'chronicle':candidates[:2], 'highlight_candidates':candidates}))
    monkeypatch.setattr(n, 'get_all_group_chats', AsyncMock(return_value=[-999]))
    await n.check_and_send_results(None)
    season = datetime.now(timezone.utc).year
    for user in (111, 222, -999):
        stored = await (await db_session.conn.execute('SELECT payload FROM delivery_payloads WHERE event_key=?',
                        (f'race-photo:{season}:17:{user}',))).fetchone()
        assert stored is not None
        payload = stored[0]
        assert 'Crash for everyone' in payload and 'Penalty for everyone' in payload
        assert ('VER retained pass' in payload) is (user == 111)
        assert 'NOR retained pass' not in payload
