from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.utils.classification_card import render_classification
from app.utils.image_render import create_f1_style_classification_image


def sample_rows():
    names = [
        ("ANT", "Kimi Antonelli", "Mercedes"), ("RUS", "George Russell", "Mercedes"),
        ("VER", "Max Verstappen", "Red Bull"), ("NOR", "Lando Norris", "McLaren"),
        ("PIA", "Oscar Piastri", "McLaren"), ("HAM", "Lewis Hamilton", "Ferrari"),
        ("GAS", "Pierre Gasly", "Alpine"), ("LIN", "Arvid Lindblad", "Racing Bulls"),
        ("COL", "Franco Colapinto", "Alpine"), ("TSU", "Yuki Tsunoda", "Racing Bulls"),
        ("BOR", "Gabriel Bortoleto", "Audi"), ("HUL", "Nico Hulkenberg", "Audi"),
        ("SAI", "Carlos Sainz", "Williams"), ("LAW", "Liam Lawson", "Racing Bulls"),
        ("BEA", "Oliver Bearman", "Haas"), ("OCO", "Esteban Ocon", "Haas"),
        ("ALB", "Alexander Albon", "Williams"), ("PER", "Sergio Perez", "Cadillac"),
        ("BOT", "Valtteri Bottas", "Cadillac"), ("STR", "Lance Stroll", "Aston Martin"),
        ("ALO", "Fernando Alonso", "Aston Martin"), ("LEC", "Charles Leclerc", "Ferrari"),
    ]
    points = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1] + [0] * 12
    return [dict(pos=i + 1, driver_code=code, driver=name, team=team, points=points[i],
                 gap_or_time="1:19.123" if i == 0 else f"+{i * .123:.3f}")
            for i, (code, name, team) in enumerate(names)]


@pytest.mark.parametrize("session", ["RACE CLASSIFICATION", "QUALIFYING CLASSIFICATION", "SPRINT QUALIFYING"])
def test_card_keeps_full_grid_and_telegram_friendly_dimensions(session):
    result = create_f1_style_classification_image("Italian Grand Prix", session, sample_rows(), 2026, {"ANT"})
    with Image.open(result) as image:
        assert image.size == (1080, 1594)
        assert image.mode == "RGB"
        assert sum(image.size) < 10000
    assert len(result.getvalue()) < 10_000_000


def test_portraits_missing_or_broken_do_not_block_results():
    def unavailable(*args):
        raise OSError("No artwork")
    output = render_classification("Long event name " * 20, "QUALIFYING", sample_rows(), 1900, set(), unavailable)
    assert Image.open(output).size[0] == 1080
    assert Image.open(render_classification("", "", [], 1900, set(), unavailable)).height == 1350


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [(8, []), (8, [{"position": 1, "driver": "?"}]), RuntimeError("offline")])
async def test_qualifying_fallback_on_partial_or_failed_primary(payload):
    from app.f1_data import get_quali_for_round_async
    source = AsyncMock(side_effect=payload) if isinstance(payload, Exception) else AsyncMock(return_value=payload)
    fallback = [{"position": 1, "driver": "ANT", "name": "Antonelli", "best": "1:19.123"}]
    with patch("app.f1_data.openf1_get_quali_for_round", source), patch(
        "app.f1_data._get_quali_async", new_callable=AsyncMock, return_value=fallback
    ) as reserve:
        assert await get_quali_for_round_async(2026, 8) == (8, fallback)
    reserve.assert_awaited_once_with(2026, 8, 100)


@pytest.mark.asyncio
async def test_qualifying_uses_finished_round_and_retries_wrong_round():
    from app.utils.notifications import check_and_notify_quali
    now = datetime.now(timezone.utc)
    events = [
        {"round": 8, "quali_start_utc": (now - timedelta(hours=2)).isoformat()},
        {"round": 9, "quali_start_utc": (now + timedelta(days=7)).isoformat()},
    ]
    with patch("app.utils.notifications.get_season_schedule_short_async", AsyncMock(return_value=events)), patch(
        "app.utils.notifications.get_last_notified_quali_round", AsyncMock(return_value=7)
    ), patch("app.utils.notifications.get_quali_for_round_async", AsyncMock(return_value=(7, []))) as source, patch(
        "app.utils.notifications.set_last_notified_quali_round", AsyncMock()
    ) as mark:
        assert await check_and_notify_quali(object()) is False
    source.assert_awaited_once_with(now.year, 8)
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_voting_results_are_skipped_without_telegram():
    from app.utils.notifications import check_and_notify_voting_results
    now = datetime.now(timezone.utc)
    with patch("app.utils.notifications.get_all_group_chats", AsyncMock(return_value=[])), patch(
        "app.utils.notifications.get_season_schedule_short_async", AsyncMock(return_value=[{"round": 1}])
    ), patch(
        "app.utils.notifications.get_last_notified_voting_round", AsyncMock(return_value=None)
    ), patch("app.utils.notifications.get_users_with_settings", AsyncMock(return_value=[(42, "UTC")])), patch(
        "app.utils.notifications._voting_closes_at", return_value=now - timedelta(days=5)
    ), patch("app.utils.notifications.set_last_notified_voting_round", AsyncMock()) as mark, patch(
        "app.utils.notifications.safe_send_message", AsyncMock()
    ) as send:
        await check_and_notify_voting_results(object(), not_before=now)
    mark.assert_awaited_once_with(now.year, 1)
    send.assert_not_awaited()

@pytest.mark.asyncio
async def test_partial_delivery_retries_only_failed_recipient():
    from app.utils.notifications import _deliver_session_classification
    receipts = set()
    async def seen(*key):
        return key in receipts
    async def mark(*key):
        receipts.add(key)
    send = AsyncMock(side_effect=[True, False, True])
    rows = [dict(position=i + 1, code=f"D{i}", name=f"Driver {i}") for i in range(10)]
    with patch("app.utils.notifications.get_users_with_settings", AsyncMock(return_value=[(1, "UTC"), (2, "UTC")])), patch(
        "app.utils.notifications.get_users_favorites_for_notifications", AsyncMock(return_value={})
    ), patch("app.utils.notifications.get_all_group_chats", AsyncMock(return_value=[])), patch(
        "app.utils.notifications.was_reminder_sent", side_effect=seen
    ), patch("app.utils.notifications.set_reminder_sent", side_effect=mark), patch(
        "app.utils.notifications.safe_send_photo", send
    ), patch("app.utils.notifications.create_f1_style_classification_image", return_value=BytesIO(b"png")):
        arguments = (object(), 2026, 8, "Test GP", "Квалификация", "QUALIFYING CLASSIFICATION", rows)
        assert await _deliver_session_classification(*arguments) is False
        assert await _deliver_session_classification(*arguments) is True
        assert await _deliver_session_classification(*arguments) is True
    assert [call.args[1] for call in send.await_args_list] == [1, 2, 2]


@pytest.mark.asyncio
async def test_startup_does_not_send_old_predictions_but_still_scores():
    import pandas as pd
    from app.services.prediction_notifications import check_and_notify_predictions
    now = datetime.now(timezone.utc)
    event = {"round": 1, "event_name": "Old GP", "race_start_utc": (now - timedelta(days=7)).isoformat()}
    prefix = "app.services.prediction_notifications."
    from contextlib import ExitStack
    with ExitStack() as stack:
        mocks = {}
        values = {
            "get_season_schedule_short_async": [event],
            "get_notification_state": {"opened_sent": True, "results_sent": False},
            "get_users_with_settings": [(42, "UTC")],
            "get_race_results_async": pd.DataFrame({"Position": range(1, 23)}),
            "get_quali_for_round_async": (1, []),
            "score_prediction_round": {"scored": 1, "max_points": 34},
            "get_stage_top": [],
            "mark_notification_state": None,
            "_send_prediction_results": 1,
        }
        for name, value in values.items():
            mocks[name] = stack.enter_context(patch(prefix + name, AsyncMock(return_value=value)))
        stack.enter_context(patch(prefix + "get_prediction_window", return_value=(None, None)))
        stack.enter_context(patch(prefix + "build_actual_answers", return_value={}))
        await check_and_notify_predictions(object(), not_before=now)
    mocks["score_prediction_round"].assert_awaited_once()
    mocks["_send_prediction_results"].assert_not_awaited()
    mocks["mark_notification_state"].assert_awaited_once_with(now.year, 1, "results_sent")
