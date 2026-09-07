from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack

import pytest

from app.utils.voting_window import voting_closes_at


def test_voting_deadline_is_identical_with_or_without_start_time():
    expected = datetime(2026, 9, 8, 21, tzinfo=timezone.utc)
    assert voting_closes_at({"date": "2026-09-06"}) == expected
    assert voting_closes_at({"race_start_utc": "2026-09-06T13:00:00Z"}) == expected
    assert voting_closes_at({}) is None


@pytest.mark.asyncio
async def test_voting_delivers_at_deadline_to_groups_and_retries_without_duplicates():
    from app.utils.notifications import check_and_notify_voting_results
    deadline = datetime(2026, 9, 8, 21, tzinfo=timezone.utc)
    event = {"round": 16, "date": "2026-09-06", "event_name": "Test & GP"}
    receipts = set()
    async def seen(*key):
        return key in receipts
    async def record(*key):
        receipts.add(key)
    send = AsyncMock(side_effect=[True, False, True])
    last = AsyncMock(return_value=None)
    with ExitStack() as stack:
        prefix = "app.utils.notifications."
        for name, value in {
            "get_season_schedule_short_async": [event],
            "get_users_with_settings": [(42, "Europe/Moscow")],
            "get_all_group_chats": [-100123, -100123],
            "get_race_avg_for_round": (4.5, 12),
            "get_driver_vote_winner": ("NOR", 7),
            "get_driver_full_name_async": "Lando Norris",
        }.items():
            stack.enter_context(patch(prefix + name, AsyncMock(return_value=value)))
        stack.enter_context(patch(prefix + "get_last_notified_voting_round", last))
        mark_round = stack.enter_context(patch(prefix + "set_last_notified_voting_round", AsyncMock()))
        stack.enter_context(patch(prefix + "was_reminder_sent", side_effect=seen))
        stack.enter_context(patch(prefix + "set_reminder_sent", side_effect=record))
        stack.enter_context(patch(prefix + "safe_send_message", send))
        clock = stack.enter_context(patch(prefix + "datetime", wraps=datetime))
        clock.now.return_value = deadline - timedelta(seconds=1)
        await check_and_notify_voting_results(object(), not_before=deadline - timedelta(days=1))
        send.assert_not_awaited()
        clock.now.return_value = deadline
        await check_and_notify_voting_results(object(), not_before=deadline - timedelta(days=1))
        mark_round.assert_not_awaited()
        await check_and_notify_voting_results(object(), not_before=deadline - timedelta(days=1))
        mark_round.assert_awaited_once_with(2026, 16)
    assert [call.args[1] for call in send.await_args_list] == [42, -100123, -100123]
    assert "4.5" in send.await_args.args[2]
    assert "Lando Norris" in send.await_args.args[2]
    assert "Test &amp; GP" in send.await_args.args[2]


@pytest.mark.asyncio
async def test_old_group_voting_is_skipped_even_without_private_recipients():
    from app.utils.notifications import check_and_notify_voting_results
    now = datetime.now(timezone.utc)
    with ExitStack() as stack:
        prefix = "app.utils.notifications."
        for name, value in {
            "get_season_schedule_short_async": [{"round": 1, "date": "2020-01-05"}],
            "get_users_with_settings": [],
            "get_all_group_chats": [-100123],
            "get_last_notified_voting_round": None,
        }.items():
            stack.enter_context(patch(prefix + name, AsyncMock(return_value=value)))
        mark = stack.enter_context(patch(prefix + "set_last_notified_voting_round", AsyncMock()))
        send = stack.enter_context(patch(prefix + "safe_send_message", AsyncMock()))
        await check_and_notify_voting_results(object(), not_before=now)
    mark.assert_awaited_once_with(now.year, 1)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_driver_vote_api_rejects_after_shared_deadline(api_client):
    with patch("app.api.miniapp_api.get_season_schedule_short_async",
               AsyncMock(return_value=[{"round": 1, "date": "2020-01-05"}])):
        response = await api_client.post("/api/votes/driver", json={
            "season": 2020, "round": 1, "driver_code": "NOR",
        })
    assert response.status_code == 400

