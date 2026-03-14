"""
Тесты уведомлений (user/group formatting).
"""

from app.utils.notifications import GROUP_TIMEZONE, get_notification_text


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
