"""
Тесты уведомлений (user/group formatting).
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.utils.notifications import (
    GROUP_TIMEZONE,
    check_and_send_notifications,
    check_and_send_results,
    check_and_notify_quali,
    get_notification_text,
)


def test_group_notifications_use_utc_and_explicit_label():
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T15:00:00+00:00",
    }

    text = get_notification_text(race, GROUP_TIMEZONE, minutes_left=60, for_quali=False)

    assert GROUP_TIMEZONE == "UTC"
    assert "15:00" in text
    assert "UTC" in text
    assert "по вашему времени" not in text


def test_private_notifications_keep_user_timezone_wording():
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T15:00:00+00:00",
    }

    text = get_notification_text(race, "Europe/Moscow", minutes_left=60, for_quali=False)

    assert "18:00" in text
    assert "по вашему времени" in text


def test_notification_text_contains_local_date():
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T23:30:00+00:00",
    }

    text = get_notification_text(race, "Europe/Moscow", minutes_left=60, for_quali=False)

    assert "📅" in text
    assert "02.03.2026" in text


@pytest.mark.asyncio
async def test_check_and_send_notifications_sends_sprint_events():
    now = datetime.now(timezone.utc)
    sprint_quali_dt = (now + timedelta(minutes=60)).isoformat()
    sprint_race_dt = (now + timedelta(minutes=61)).isoformat()
    schedule = [{
        "round": 3,
        "event_name": "Miami Grand Prix",
        "location": "Miami",
        "sprint_quali_start_utc": sprint_quali_dt,
        "sprint_start_utc": sprint_race_dt,
    }]

    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_users_with_settings", new_callable=AsyncMock) as m_users, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.was_reminder_sent", new_callable=AsyncMock) as m_was_sent, \
            patch("app.utils.notifications.set_reminder_sent", new_callable=AsyncMock) as m_set_sent, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as m_send:
        m_sched.return_value = schedule
        m_users.return_value = [(111, "Europe/Moscow", 60, 1)]
        m_groups.return_value = []
        m_was_sent.return_value = False
        m_send.return_value = True

        await check_and_send_notifications(bot=object())

    sent_texts = [call.args[2] for call in m_send.await_args_list if len(call.args) >= 3]
    assert any("Скоро спринт-квалификация" in t for t in sent_texts)
    assert any("Скоро спринт" in t for t in sent_texts)
    assert m_set_sent.await_count >= 2


@pytest.mark.asyncio
async def test_check_and_send_results_does_not_mark_round_when_delivery_failed():
    """Раунд не должен помечаться как отправленный, если фактическая доставка не удалась."""
    now = datetime.now(timezone.utc)
    schedule = [{
        "round": 5,
        "event_name": "Bahrain GP",
        "race_start_utc": (now - timedelta(hours=2)).isoformat(),
    }]
    results_df = pd.DataFrame([
        {"Position": 1, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull", "Points": 25},
    ])

    async def users_side_effect(notifications_only: bool = False):
        if notifications_only:
            return [(111, "Europe/Moscow", 60, 1)]
        return [(111, "Europe/Moscow", 60, 1)]

    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_last_notified_round", new_callable=AsyncMock) as m_last_notified, \
            patch("app.utils.notifications.get_race_results_async", new_callable=AsyncMock) as m_race_res, \
            patch("app.utils.notifications.get_last_notified_voting_invite_round", new_callable=AsyncMock) as m_voting_inv, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as m_favs, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect) as m_users, \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_driver_st, \
            patch("app.utils.notifications.get_constructor_standings_async", new_callable=AsyncMock) as m_con_st, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_send_photo, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as m_send_msg, \
            patch("app.utils.notifications.set_last_notified_round", new_callable=AsyncMock) as m_set_notified:
        m_sched.return_value = schedule
        m_last_notified.return_value = None
        m_race_res.return_value = results_df
        m_voting_inv.return_value = 5
        m_favs.return_value = {}
        m_groups.return_value = []
        m_driver_st.return_value = pd.DataFrame()
        m_con_st.return_value = pd.DataFrame()
        m_send_photo.return_value = False
        m_send_msg.return_value = True

        await check_and_send_results(bot=object())

    assert m_send_photo.await_count >= 1
    assert m_set_notified.await_count == 0


@pytest.mark.asyncio
async def test_check_and_notify_quali_does_not_mark_round_when_delivery_failed():
    """Квалификационный раунд не помечается отправленным при провале доставки."""
    results = [{"position": 1, "driver": "VER", "name": "Max Verstappen", "best": "1:29.0", "gap": "1:29.0"}]

    async def users_side_effect(notifications_only: bool = False):
        if notifications_only:
            return [(111, "Europe/Moscow", 60, 1)]
        return [(111, "Europe/Moscow", 60, 1)]

    with patch("app.utils.notifications._get_latest_quali_async", new_callable=AsyncMock) as m_latest, \
            patch("app.utils.notifications.get_last_notified_quali_round", new_callable=AsyncMock) as m_last, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as m_favs, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_driver_st, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_send_photo, \
            patch("app.utils.notifications.set_cached_quali_results", new_callable=AsyncMock) as m_set_cache, \
            patch("app.utils.notifications.set_last_notified_quali_round", new_callable=AsyncMock) as m_set_notified:
        m_latest.return_value = (4, results)
        m_last.return_value = None
        m_favs.return_value = {}
        m_groups.return_value = []
        m_sched.return_value = [{"round": 4, "event_name": "Bahrain GP"}]
        m_driver_st.return_value = pd.DataFrame()
        m_send_photo.return_value = False
        m_set_cache.return_value = None

        await check_and_notify_quali(bot=object())

    assert m_send_photo.await_count >= 1
    assert m_set_notified.await_count == 0
