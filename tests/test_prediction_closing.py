from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize('offset,restarted,already,expected', [(120,False,False,True),(121,False,False,False),(110,False,False,False),(120,True,False,False),(120,False,True,False)])
async def test_closing_window(monkeypatch, offset, restarted, already, expected):
    from app.services import prediction_notifications as n
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(n, 'get_season_schedule_short_async', AsyncMock(return_value=[{'round':1}]))
    monkeypatch.setattr(n, 'get_users_with_settings', AsyncMock(return_value=[(1,'UTC')]))
    monkeypatch.setattr(n, 'get_notification_state', AsyncMock(return_value={'opened_sent':True,'results_sent':True,'closing_sent':already}))
    monkeypatch.setattr(n, 'get_prediction_window', lambda e: (now-timedelta(days=1),now+timedelta(minutes=offset)))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(n, '_send_prediction_closing', send)
    monkeypatch.setattr(n, 'mark_notification_state', AsyncMock())
    await n.check_and_notify_predictions(AsyncMock(), not_before=now+timedelta(seconds=1) if restarted else None)
    assert bool(send.await_count) is expected


@pytest.mark.asyncio
async def test_closing_queues_only_recipients_without_legacy_receipts(monkeypatch):
    from app.services import prediction_notifications as n
    receipts = {1}
    async def seen(tg, *args): return tg in receipts
    monkeypatch.setattr(n, 'was_reminder_sent', seen)
    monkeypatch.setattr(n, 'publish_web', AsyncMock())
    monkeypatch.setattr(n, 'mini_app_button', AsyncMock(return_value=None))
    sender = AsyncMock()
    monkeypatch.setattr(n, '_queue_prediction', sender)
    args = (AsyncMock(), {'season':2026,'round':1,'event_name':'Test GP'}, [(1,'UTC'),(2,'UTC')])
    assert await n._send_prediction_closing(*args)
    assert sender.call_args.args[-1] == [(2,'UTC')]
