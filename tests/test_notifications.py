"""
Тесты уведомлений (user/group formatting).
"""
import io
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from aiogram.types import BufferedInputFile

from app.utils.notifications import (
    GROUP_TIMEZONE,
    _is_voting_results_send_time,
    check_and_send_notifications,
    check_and_send_results,
    check_and_send_session_results,
    check_and_notify_quali,
    check_and_notify_voting_results,
    get_notification_text,
)
from app.utils.safe_send import safe_send_photo


def _emit_preview(request: pytest.FixtureRequest, label: str, text: str) -> None:
    """Always show rendered message preview in pytest output."""
    tr = request.config.pluginmanager.getplugin("terminalreporter")
    if tr is None:
        return
    tr.write_line(f"[PREVIEW] {label}")
    for line in text.splitlines():
        tr.write_line(f"          {line}")


def test_group_notifications_no_time_line(request: pytest.FixtureRequest):
    """В групповых чатах не показываем строку «Начало в HH:MM (UTC)», только заголовок, через, трасса, дата."""
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T15:00:00+00:00",
    }

    text = get_notification_text(race, GROUP_TIMEZONE, minutes_left=60, for_quali=False, for_group=True)
    _emit_preview(request, "Group race reminder", text)

    assert GROUP_TIMEZONE == "UTC"
    assert "Скоро гонка" in text
    assert "Через" in text and "старт:" in text
    assert "Трасса:" in text and "Sakhir" in text
    assert "Дата:" in text and "01.03.2026" in text
    assert "Начало в" not in text
    assert "UTC" not in text


def test_private_notifications_keep_user_timezone_wording(request: pytest.FixtureRequest):
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T15:00:00+00:00",
    }

    text = get_notification_text(race, "Europe/Moscow", minutes_left=60, for_quali=False)
    _emit_preview(request, "Private race reminder", text)

    assert "18:00" in text
    assert "по вашему времени" in text


def test_notification_text_contains_local_date(request: pytest.FixtureRequest):
    race = {
        "event_name": "Bahrain Grand Prix",
        "location": "Sakhir",
        "race_start_utc": "2026-03-01T23:30:00+00:00",
    }

    text = get_notification_text(race, "Europe/Moscow", minutes_left=60, for_quali=False)
    _emit_preview(request, "Private race reminder with local date", text)

    assert "📅" in text
    assert "02.03.2026" in text


def test_voting_results_retry_window_stays_open_after_ten():
    """Пропущенный запуск в 10:00 можно безопасно повторить позднее в тот же день."""
    assert _is_voting_results_send_time(
        "Europe/Moscow",
        datetime(2026, 7, 18, 8, 30, tzinfo=timezone.utc),
    ) is True


@pytest.mark.asyncio
async def test_voting_results_do_not_depend_on_external_race_results():
    """Итоги из локальных голосов доставляются даже без внешнего протокола гонки."""
    schedule = [{"round": 1, "event_name": "Australian GP", "date": "2026-01-01"}]

    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_last_notified_voting_round", new_callable=AsyncMock) as m_last, \
            patch("app.utils.notifications.get_users_with_settings", new_callable=AsyncMock) as m_users, \
            patch("app.utils.notifications.get_race_avg_for_round", new_callable=AsyncMock) as m_avg, \
            patch("app.utils.notifications.get_driver_vote_winner", new_callable=AsyncMock) as m_winner, \
            patch("app.utils.notifications.get_driver_full_name_async", new_callable=AsyncMock) as m_name, \
            patch("app.utils.notifications._is_voting_results_send_time", return_value=True), \
            patch("app.utils.notifications.was_reminder_sent", new_callable=AsyncMock) as m_was_sent, \
            patch("app.utils.notifications.set_reminder_sent", new_callable=AsyncMock) as m_set_sent, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as m_send:
        m_sched.return_value = schedule
        m_last.return_value = None
        m_users.return_value = [(111, "Europe/Moscow", 60, 1)]
        m_avg.return_value = (4.5, 12)
        m_winner.return_value = ("PIA", 8)
        m_name.return_value = "Oscar Piastri"
        m_was_sent.return_value = False
        m_send.return_value = True

        await check_and_notify_voting_results(bot=object())

    m_send.assert_awaited_once()
    assert "4.5" in m_send.await_args.args[2]
    assert "Oscar Piastri" in m_send.await_args.args[2]
    m_set_sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_and_send_notifications_sends_sprint_events(request: pytest.FixtureRequest):
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
    for idx, preview in enumerate(sent_texts, start=1):
        _emit_preview(request, f"Sent notification #{idx}", preview)
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
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_send_photo, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as m_send_msg, \
            patch("app.utils.notifications.RACE_RESULTS_MIN_ROWS", 1), \
            patch("app.utils.notifications.set_last_notified_round", new_callable=AsyncMock) as m_set_notified:
        m_sched.return_value = schedule
        m_last_notified.return_value = None
        m_race_res.return_value = results_df
        m_voting_inv.return_value = 5
        m_favs.return_value = {}
        m_groups.return_value = []
        m_driver_st.return_value = pd.DataFrame()
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
            patch("app.utils.notifications.SESSION_RESULTS_MIN_ROWS", 1), \
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


@pytest.mark.asyncio
async def test_check_and_send_results_does_not_mark_round_when_rows_unparseable():
    """Если результаты пришли в неразбираемом формате, этап не помечается отправленным (нужен ретрай)."""
    now = datetime.now(timezone.utc)
    schedule = [{
        "round": 6,
        "event_name": "Imola GP",
        "race_start_utc": (now - timedelta(hours=3)).isoformat(),
    }]
    # Нет колонки Position -> rows_for_image останется пустым
    results_df = pd.DataFrame([
        {"Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull", "Points": 25},
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
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_driver_st, \
            patch("app.utils.notifications.set_last_notified_round", new_callable=AsyncMock) as m_set_notified:
        m_sched.return_value = schedule
        m_last_notified.return_value = None
        m_race_res.return_value = results_df
        m_voting_inv.return_value = 6
        m_favs.return_value = {}
        m_groups.return_value = []
        m_driver_st.return_value = pd.DataFrame()

        await check_and_send_results(bot=object())

    assert m_set_notified.await_count == 0


@pytest.mark.asyncio
async def test_check_and_notify_quali_does_not_mark_round_when_no_rows():
    """Если latest-quali временно пустая, раунд не должен считаться отправленным."""
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
            patch("app.utils.notifications.set_cached_quali_results", new_callable=AsyncMock) as m_set_cache, \
            patch("app.utils.notifications.set_last_notified_quali_round", new_callable=AsyncMock) as m_set_notified:
        m_latest.return_value = (4, [])
        m_last.return_value = None
        m_favs.return_value = {}
        m_groups.return_value = []
        m_sched.return_value = [{"round": 4, "event_name": "Bahrain GP"}]
        m_driver_st.return_value = pd.DataFrame()
        m_set_cache.return_value = None

        await check_and_notify_quali(bot=object())

    assert m_set_notified.await_count == 0


@pytest.mark.asyncio
async def test_check_and_send_results_fallbacks_to_all_users_when_notifications_only_empty():
    """Legacy-режим: если notifications_only пуст, пост-гоночная рассылка идёт всем пользователям."""
    now = datetime.now(timezone.utc)
    schedule = [{
        "round": 7,
        "event_name": "Monaco GP",
        "race_start_utc": (now - timedelta(hours=2)).isoformat(),
    }]
    results_df = pd.DataFrame([
        {"Position": 1, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull", "Points": 25},
    ])

    async def users_side_effect(notifications_only: bool = False):
        if notifications_only:
            return []
        return [(111, "Europe/Moscow", 60, 0)]

    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_last_notified_round", new_callable=AsyncMock) as m_last_notified, \
            patch("app.utils.notifications.get_race_results_async", new_callable=AsyncMock) as m_race_res, \
            patch("app.utils.notifications.get_last_notified_voting_invite_round", new_callable=AsyncMock) as m_voting_inv, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as m_favs, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_driver_st, \
            patch("app.utils.notifications.create_f1_style_classification_image") as m_render, \
            patch("app.utils.notifications.RACE_RESULTS_MIN_ROWS", 1), \
            patch("app.utils.notifications.set_last_notified_round", new_callable=AsyncMock) as m_set_notified, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_send_photo:
        m_sched.return_value = schedule
        m_last_notified.return_value = None
        m_race_res.return_value = results_df
        m_voting_inv.return_value = 7
        m_favs.return_value = {}
        m_groups.return_value = []
        m_driver_st.return_value = pd.DataFrame()
        m_render.return_value = io.BytesIO(b"test-image")
        m_send_photo.return_value = True

        await check_and_send_results(bot=object())

    assert m_send_photo.await_count >= 1
    assert m_set_notified.await_count == 1


@pytest.mark.asyncio
async def test_safe_send_photo_wraps_bytes_for_aiogram():
    """Сгенерированные PNG bytes преобразуются в BufferedInputFile перед Telegram API."""
    bot = AsyncMock()
    sent = await safe_send_photo(bot, 111, b"png-bytes", caption="Результаты")
    assert sent is True
    photo = bot.send_photo.await_args.kwargs["photo"]
    assert isinstance(photo, BufferedInputFile)
    assert photo.filename == "f1hub-results.png"


@pytest.mark.asyncio
async def test_race_results_wait_until_race_can_be_finished():
    """Live-позиции через 90 минут после старта не рассылаются как финальный результат."""
    now = datetime.now(timezone.utc)
    schedule = [{
        "round": 8,
        "event_name": "Spa GP",
        "race_start_utc": (now - timedelta(minutes=90)).isoformat(),
    }]
    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_last_notified_round", new_callable=AsyncMock) as m_last, \
            patch("app.utils.notifications.get_race_results_async", new_callable=AsyncMock) as m_results:
        m_sched.return_value = schedule
        m_last.return_value = None
        await check_and_send_results(bot=object())
    assert m_results.await_count == 0


@pytest.mark.asyncio
async def test_race_results_send_image_and_separate_favorites_message():
    """После гонки пользователь получает общую картинку и отдельный текст по избранному."""
    now = datetime.now(timezone.utc)
    schedule = [{
        "round": 9,
        "event_name": "Monza GP",
        "race_start_utc": (now - timedelta(hours=3)).isoformat(),
    }]
    results_df = pd.DataFrame([
        {"Position": 1, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull", "Points": 25},
        {"Position": 2, "Abbreviation": "NOR", "FirstName": "Lando", "LastName": "Norris", "TeamName": "McLaren", "Points": 18},
    ])

    async def users_side_effect(notifications_only: bool = False):
        return [(111, "Europe/Moscow", 60, 1)]

    with patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_last_notified_round", new_callable=AsyncMock) as m_last, \
            patch("app.utils.notifications.get_race_results_async", new_callable=AsyncMock) as m_results, \
            patch("app.utils.notifications.get_last_notified_voting_invite_round", new_callable=AsyncMock) as m_invite, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as m_favs, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_standings, \
            patch("app.utils.notifications.create_f1_style_classification_image") as m_render, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_photo, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as m_message, \
            patch("app.utils.notifications.RACE_RESULTS_MIN_ROWS", 1), \
            patch("app.utils.notifications.set_last_notified_round", new_callable=AsyncMock) as m_set_round:
        m_sched.return_value = schedule
        m_last.return_value = None
        m_results.return_value = results_df
        m_invite.return_value = 9
        m_favs.return_value = {111: {"drivers": ["VER"], "teams": ["Red Bull"]}}
        m_groups.return_value = []
        m_standings.return_value = pd.DataFrame()
        m_render.return_value = io.BytesIO(b"test-image")
        m_photo.return_value = True
        m_message.return_value = True
        await check_and_send_results(bot=object())

    assert m_photo.await_count == 1
    favorite_texts = [call.args[2] for call in m_message.await_args_list if len(call.args) >= 3]
    assert any("Пилоты" in text and "Команды" in text for text in favorite_texts)
    assert m_set_round.await_count == 1


@pytest.mark.asyncio
async def test_check_and_notify_quali_fallbacks_to_all_users_when_notifications_only_empty():
    """Legacy-режим: если notifications_only пуст, пост-квали-рассылка идёт всем пользователям."""
    results = [{"position": 1, "driver": "VER", "name": "Max Verstappen", "best": "1:29.0", "gap": "1:29.0"}]

    async def users_side_effect(notifications_only: bool = False):
        if notifications_only:
            return []
        return [(111, "Europe/Moscow", 60, 0)]

    with patch("app.utils.notifications._get_latest_quali_async", new_callable=AsyncMock) as m_latest, \
            patch("app.utils.notifications.get_last_notified_quali_round", new_callable=AsyncMock) as m_last, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as m_favs, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as m_groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as m_sched, \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as m_driver_st, \
            patch("app.utils.notifications.SESSION_RESULTS_MIN_ROWS", 1), \
            patch("app.utils.notifications.set_cached_quali_results", new_callable=AsyncMock), \
            patch("app.utils.notifications.create_f1_style_classification_image") as m_render, \
            patch("app.utils.notifications.set_last_notified_quali_round", new_callable=AsyncMock) as m_set_notified, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as m_send_photo:
        m_latest.return_value = (8, results)
        m_last.return_value = None
        m_favs.return_value = {}
        m_groups.return_value = []
        m_sched.return_value = [{"round": 8, "event_name": "Monaco GP"}]
        m_driver_st.return_value = pd.DataFrame()
        m_render.return_value = io.BytesIO(b"test-image")
        m_send_photo.return_value = True

        await check_and_notify_quali(bot=object())

    assert m_send_photo.await_count >= 1
    assert m_set_notified.await_count == 1


@pytest.mark.asyncio
async def test_quali_sends_generic_image_and_separate_favorites_message():
    """Избранные после квалификации приходят отдельным сообщением, как после гонки."""
    results = [
        {"position": 1, "driver": "VER", "name": "Max Verstappen", "best": "1:44.361", "gap": "1:44.361"},
        {"position": 2, "driver": "NOR", "name": "Lando Norris", "best": "1:44.678", "gap": "+0.317"},
    ]

    async def users_side_effect(notifications_only: bool = False):
        return [(111, "Europe/Moscow", 60, 1)]

    standings = pd.DataFrame([
        {"driverCode": "VER", "constructorName": "Red Bull"},
        {"driverCode": "NOR", "constructorName": "McLaren"},
    ])
    with patch("app.utils.notifications._get_latest_quali_async", new_callable=AsyncMock) as latest, \
            patch("app.utils.notifications.get_last_notified_quali_round", new_callable=AsyncMock) as last, \
            patch("app.utils.notifications.get_users_favorites_for_notifications", new_callable=AsyncMock) as favorites, \
            patch("app.utils.notifications.get_all_group_chats", new_callable=AsyncMock) as groups, \
            patch("app.utils.notifications.get_users_with_settings", side_effect=users_side_effect), \
            patch("app.utils.notifications.get_season_schedule_short_async", new_callable=AsyncMock) as schedule, \
            patch("app.utils.notifications.get_driver_standings_async", new_callable=AsyncMock) as driver_standings, \
            patch("app.utils.notifications.SESSION_RESULTS_MIN_ROWS", 1), \
            patch("app.utils.notifications.set_cached_quali_results", new_callable=AsyncMock), \
            patch("app.utils.notifications.create_f1_style_classification_image") as render, \
            patch("app.utils.notifications.safe_send_photo", new_callable=AsyncMock) as send_photo, \
            patch("app.utils.notifications.safe_send_message", new_callable=AsyncMock) as send_message, \
            patch("app.utils.notifications.set_last_notified_quali_round", new_callable=AsyncMock) as set_round:
        latest.return_value = (10, results)
        last.return_value = None
        favorites.return_value = {111: {"drivers": ["VER"], "teams": ["Red Bull"]}}
        groups.return_value = []
        schedule.return_value = [{"round": 10, "event_name": "Belgian Grand Prix"}]
        driver_standings.return_value = standings
        render.return_value = io.BytesIO(b"test-image")
        send_photo.return_value = True
        send_message.return_value = True

        delivered = await check_and_notify_quali(bot=object())

    assert delivered is True
    send_photo.assert_awaited_once()
    send_message.assert_awaited_once()
    favorite_text = send_message.await_args.args[2]
    assert "Квалификация" in favorite_text
    assert "VER: P1" in favorite_text
    assert "Red Bull: P1" in favorite_text
    set_round.assert_awaited_once_with(datetime.now(timezone.utc).year, 10)


@pytest.mark.asyncio
async def test_session_results_are_checked_in_required_order_and_stop_on_failure():
    """Следующая сессия не обгоняет предыдущую, если её данные/доставка ещё не готовы."""
    order = []

    async def sprint_quali(_bot):
        order.append("sprint_quali")
        return False

    async def sprint(_bot):
        order.append("sprint")
        return True

    with patch("app.utils.notifications.check_and_notify_sprint_quali", side_effect=sprint_quali), \
            patch("app.utils.notifications.check_and_notify_sprint", side_effect=sprint), \
            patch("app.utils.notifications.check_and_notify_quali", new_callable=AsyncMock) as quali, \
            patch("app.utils.notifications.check_and_send_results", new_callable=AsyncMock) as race:
        await check_and_send_session_results(bot=object())

    assert order == ["sprint_quali"]
    quali.assert_not_awaited()
    race.assert_not_awaited()
