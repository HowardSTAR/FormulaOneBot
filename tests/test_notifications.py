"""
Тесты уведомлений (user/group formatting).
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.notifications import GROUP_TIMEZONE, check_and_send_notifications, get_notification_text


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
