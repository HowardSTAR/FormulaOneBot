import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from app.db import (
    db,
    get_users_favorites_for_notifications,
    get_last_notified_round,
    set_last_notified_round,
    get_last_notified_quali_round,
    set_last_notified_quali_round,
    get_last_notified_voting_round,
    set_last_notified_voting_round,
    get_last_notified_voting_invite_round,
    set_last_notified_voting_invite_round,
    get_race_avg_for_round,
    get_driver_vote_winner,
    get_all_group_chats,
    was_reminder_sent,
    set_reminder_sent,
)
import pandas as pd

from app.f1_data import (
    points_for_race_position,
    get_season_schedule_short_async,
    get_race_results_async,
    get_constructor_standings_async,
    get_driver_standings_async,
    _get_latest_quali_async,
    get_testing_results_async,
    get_driver_full_name_async,
    set_cached_quali_results,
)
from app.utils.safe_send import safe_send_message, safe_send_photo
from app.utils.image_render import create_f1_style_classification_image

logger = logging.getLogger(__name__)
ADMIN_ID = 2099386


# --- ХЕЛПЕРЫ ОБЩИЕ ---

# Тихий режим: 21:00–10:00 по времени пользователя (без звука)
QUIET_START_HOUR = 21
QUIET_END_HOUR = 10

# Для групп: напоминать за 60 минут, таймзона МСК
GROUP_NOTIFY_BEFORE = 60
GROUP_TIMEZONE = "Europe/Moscow"


def is_quiet_hours(tz_name: str) -> bool:
    """
    Возвращает True, если сейчас 21:00–10:00 в таймзоне пользователя.
    В этот период уведомления отправляются с disable_notification=True (тихий режим).
    """
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(tz)
    hour = now.hour
    if QUIET_START_HOUR <= hour or hour < QUIET_END_HOUR:
        return True
    return False


def format_time_left(minutes_left: int) -> str:
    if minutes_left >= 20 * 60: return "Уже завтра"
    hours = minutes_left // 60
    minutes = int(minutes_left % 60)
    parts = []
    if hours > 0: parts.append(f"{int(hours)} ч.")
    if minutes > 0: parts.append(f"{minutes} мин.")
    return f"Через {' '.join(parts)}"


def get_notification_text(race: dict, user_tz_name: str, minutes_left: int, for_quali: bool = False) -> str:
    """Генерирует текст для ГОНКИ или КВАЛИФИКАЦИИ."""
    event_name = race.get('event_name', 'Гран-при')
    dt_key = "quali_start_utc" if for_quali else "race_start_utc"
    dt_str = race.get(dt_key) or race.get("race_start_utc")
    try:
        dt_utc = datetime.fromisoformat(dt_str)
        if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        user_tz = ZoneInfo(user_tz_name)
        start_time_str = dt_utc.astimezone(user_tz).strftime("%H:%M")
    except Exception:
        start_time_str = "??:??"

    if for_quali:
        return (
            f"⏱ Скоро квалификация!\n\n"
            f"{format_time_left(minutes_left)} старт: {event_name}\n"
            f"📍 Трасса: {race.get('location', '')}\n"
            f"⏰ Начало в {start_time_str} (по вашему времени)\n"
        )
    return (
        f"🏎 Скоро гонка!\n\n"
        f"{format_time_left(minutes_left)} старт: {event_name} 🏁\n"
        f"📍 Трасса: {race.get('location', '')}\n"
        f"⏰ Начало в {start_time_str} (по вашему времени)\n"
    )


async def get_users_with_settings(notifications_only: bool = False):
    """Возвращает (telegram_id, timezone, notify_before[, notifications_enabled])."""
    if not db.conn: await db.connect()
    try:
        q = "SELECT telegram_id, timezone, notify_before, notifications_enabled FROM users"
        if notifications_only:
            q += " WHERE notifications_enabled = 1"
        async with db.conn.execute(q) as cursor:
            rows = await cursor.fetchall()
            return [(r[0], r[1], r[2], r[3] if len(r) > 3 else False) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        return []


# --- ЗАДАЧА 1: АНОНСЫ (ГОНКИ И ТЕСТЫ) ---

async def check_and_send_notifications(bot: Bot):
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule: return

    now = datetime.now(timezone.utc)
    upcoming_event = []  # (race_dict, minutes_left, for_quali)

    for r in schedule:
        # Напоминание перед ГОНКОЙ
        if r.get("race_start_utc"):
            try:
                race_dt = datetime.fromisoformat(r["race_start_utc"])
                if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
                minutes_left = (race_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, False))
            except Exception:
                pass
        # Напоминание перед КВАЛИФИКАЦИЕЙ
        if r.get("quali_start_utc") and not r.get("is_testing"):
            try:
                quali_dt = datetime.fromisoformat(r["quali_start_utc"])
                if quali_dt.tzinfo is None: quali_dt = quali_dt.replace(tzinfo=timezone.utc)
                minutes_left = (quali_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, True))
            except Exception:
                pass

    if not upcoming_event:
        return

    users = await get_users_with_settings(notifications_only=True)
    group_chats = await get_all_group_chats()
    if not users and not group_chats:
        return

    # Окно ±1 мин от целевого времени, чтобы не слать «за 32 мин» вместо «за 30»
    half_window = 1.0

    sent_count = 0
    for user in users:
        try:
            tg_id = user[0]
            tz = user[1] or "Europe/Moscow"
            notify_min = user[2] or 1440

            for race, mins, for_quali in upcoming_event:
                if abs(mins - notify_min) <= half_window:
                    round_num = race.get("round")
                    if round_num is not None:
                        if await was_reminder_sent(tg_id, season, round_num, for_quali, notify_min):
                            continue

                    if race.get("is_testing"):
                        text = (
                            f"🧪 Предсезонные тесты!\n\n"
                            f"Уже завтра: {race.get('event_name')}\n"
                            f"📍 Трасса: {race.get('location')}\n"
                            f"Не забудьте следить за результатами!"
                        )
                    else:
                        text = get_notification_text(race, tz, mins, for_quali=for_quali)

                    quiet = is_quiet_hours(tz)
                    if await safe_send_message(bot, tg_id, text, disable_notification=quiet):
                        sent_count += 1
                        if round_num is not None:
                            await set_reminder_sent(tg_id, season, round_num, for_quali, notify_min)
                    await asyncio.sleep(0.05)
        except Exception:
            continue

    # === Рассылка в группы (общая информация, без избранного) — один раз на группу ===
    group_chats_raw = await get_all_group_chats()
    group_chats = list(dict.fromkeys(group_chats_raw)) if group_chats_raw else []
    if group_chats:
        for race, mins, for_quali in upcoming_event:
            if abs(mins - GROUP_NOTIFY_BEFORE) <= half_window:
                round_num_g = race.get("round")
                text = get_notification_text(race, GROUP_TIMEZONE, mins, for_quali=for_quali)
                quiet = is_quiet_hours(GROUP_TIMEZONE)
                for chat_id in group_chats:
                    group_key = None
                    if round_num_g is not None:
                        group_key = -abs(int(chat_id))
                        if await was_reminder_sent(group_key, season, round_num_g, for_quali, GROUP_NOTIFY_BEFORE):
                            continue
                    if await safe_send_message(bot, chat_id, text, parse_mode="HTML", disable_notification=quiet):
                        sent_count += 1
                        if group_key is not None:
                            await set_reminder_sent(group_key, season, round_num_g, for_quali, GROUP_NOTIFY_BEFORE)
                    await asyncio.sleep(0.05)
                break  # одно напоминание за цикл

    if sent_count > 0:
        logger.info(f"✅ Sent {sent_count} event reminders.")


# --- ЗАДАЧА 2: РЕЗУЛЬТАТЫ (ГОНКИ И ТЕСТЫ) ---

def build_results_text(race_name: str, favorites_results: list[dict]) -> str:
    """Текст по избранным пилотам (для тестовых команд)."""
    lines = []
    for item in favorites_results:
        pos_str = f"P{item['pos']}"
        if str(item.get('pos')) == '1': pos_str = "🥇 P1"
        elif str(item.get('pos')) == '2': pos_str = "🥈 P2"
        elif str(item.get('pos')) == '3': pos_str = "🥉 P3"
        lines.append(f"{item['code']}: {pos_str} (+{item.get('points', 0)})")
    return f"🏁 Финиш: {race_name}\n\nВаши фавориты:\n" + "\n".join(lines)


def build_favorites_caption(
    event_name: str,
    driver_results: list[dict],
    team_results: list[dict],
    use_spoiler: bool = True,
) -> str:
    """
    Текст по избранным пилотам и командам.
    use_spoiler=True — оборачивает результаты в <tg-spoiler> (HTML).
    """
    parts = []
    if driver_results:
        lines = []
        for item in driver_results:
            pos_str = f"P{item['pos']}"
            if str(item.get('pos')) == '1': pos_str = "🥇 P1"
            elif str(item.get('pos')) == '2': pos_str = "🥈 P2"
            elif str(item.get('pos')) == '3': pos_str = "🥉 P3"
            lines.append(f"{item['code']}: {pos_str} (+{item.get('points', 0)})")
        parts.append("<b>🏎 Пилоты</b>\n" + "\n".join(lines))
    if team_results:
        lines = []
        for t in team_results:
            lines.append(f"• {t.get('team', '?')}: {t.get('text', '')}")
        parts.append("<b>🏁 Команды</b>\n" + "\n".join(lines))
    if not parts:
        return f"🏁 {event_name}\n\n📊 Результаты на картинке."
    inner = "\n\n".join(parts)
    if use_spoiler:
        return f"🏁 {event_name}\n\n<tg-spoiler>{inner}</tg-spoiler>"
    return f"🏁 {event_name}\n\n{inner}"


async def check_and_send_results(bot: Bot):
    season = datetime.now(timezone.utc).year
    last_notified = await get_last_notified_round(season)
    schedule = await get_season_schedule_short_async(season)

    # Ищем последнюю завершенную
    now = datetime.now(timezone.utc)
    finished_event = None

    for r in schedule:
        if not r.get("race_start_utc"): continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
            # Считаем завершенным: тесты — 9ч; гонка — 1ч (OpenF1 даёт результаты почти сразу)
            finish_offset = 9 if r.get("is_testing") else 1

            if now > race_dt + timedelta(hours=finish_offset):
                finished_event = r
            else:
                break
        except:
            continue

    if not finished_event: return
    round_num = finished_event["round"]

    if last_notified and last_notified >= round_num: return

    # === ЛОГИКА ДЛЯ ТЕСТОВ ===
    if finished_event.get("is_testing"):
        # Для тестов рассылаем ТОП-3 всем
        logger.info(f"🧪 Checking testing results for {finished_event['event_name']}...")
        df, day_name = await get_testing_results_async(season, round_num)

        if df.empty: return

        # Формируем текст Топ-3
        top3 = df.head(3)
        lines = []
        for i, row in top3.iterrows():
            driver = row.get('Abbreviation', '???')
            time = str(row.get('Time', '-'))
            if "days" in time: time = time.split("days")[-1].strip()
            if "." in time: time = time[:-3]

            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
            lines.append(f"{medal} {driver}: {time}")

        text = (
                f"🧪 Итоги тестов: {day_name}\n"
                f"{finished_event['event_name']}\n\n"
                + "\n".join(lines) +
                "\n\n📊 Подробности: /next_race"
        )

        # Рассылаем всем с включёнными уведомлениями + в группы
        users = await get_users_with_settings(notifications_only=True)
        group_chats = await get_all_group_chats()
        sent_count = 0
        for user in users:
            tz = user[1] or "Europe/Moscow"
            quiet = is_quiet_hours(tz)
            if await safe_send_message(bot, user[0], text, disable_notification=quiet):
                sent_count += 1
            await asyncio.sleep(0.05)
        for chat_id in group_chats:
            if await safe_send_message(bot, chat_id, text, disable_notification=is_quiet_hours(GROUP_TIMEZONE)):
                sent_count += 1
            await asyncio.sleep(0.05)

        await set_last_notified_round(season, round_num)
        return

    # === ЛОГИКА ДЛЯ ГОНОК: картинка + текст по избранным под спойлером ===
    results_df = await get_race_results_async(season, round_num)

    # Проверяем, что данные полные (нет ??)
    data_incomplete = False
    if not results_df.empty:
        for row in results_df.itertuples(index=False):
            code = getattr(row, "Abbreviation", "") or getattr(row, "DriverNumber", "?")
            given = getattr(row, "FirstName", "") or ""
            family = getattr(row, "LastName", "") or ""
            full = f"{given} {family}".strip() or code
            if code == "?" or "?" in str(full):
                data_incomplete = True
                break

    # Если результатов нет или данные неполные — приглашаем на голосование
    voting_invite_sent = await get_last_notified_voting_invite_round(season)
    if results_df.empty or data_incomplete:
        if voting_invite_sent is None or voting_invite_sent < round_num:
            voting_users = await get_users_with_settings(notifications_only=True)
            event_name = finished_event.get("event_name", "Гран-при")
            voting_text = (
                f"🗳 <b>Приглашаем на голосование!</b>\n\n"
                f"🏁 {event_name} завершена.\n\n"
                f"Оцените этап по 5-балльной шкале и выберите пилота дня — "
                f"откройте раздел <b>Голосование</b> в MiniWebApp слева по кнопке."
            )
            for u in voting_users:
                tg_id, tz = u[0], u[1] or "Europe/Moscow"
                quiet = is_quiet_hours(tz)
                await safe_send_message(bot, tg_id, voting_text, parse_mode="HTML", disable_notification=quiet)
                await asyncio.sleep(0.05)
            await set_last_notified_voting_invite_round(season, round_num)
            logger.info(f"🗳 Sent voting invite for {event_name} (no results yet)")
        return

    users_favorites = await get_users_favorites_for_notifications()
    group_chats = await get_all_group_chats()
    if not users_favorites and not group_chats:
        await set_last_notified_round(season, round_num)
        return

    # Сразу помечаем этап как «рассылаем», чтобы параллельный запуск job не дублировал
    await set_last_notified_round(season, round_num)

    users_settings = await get_users_with_settings()
    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users_settings}

    # Картинка с общими результатами (без звёздочек для избранных — одна картинка на всех)
    race_info = finished_event
    if "Position" in results_df.columns:
        results_df = results_df.sort_values("Position")

    driver_standings = await get_driver_standings_async(season, round_number=round_num)
    code_to_team: dict[str, str] = {}
    if not driver_standings.empty and "driverCode" in driver_standings.columns:
        for row in driver_standings.itertuples(index=False):
            c = str(getattr(row, "driverCode", "") or "").strip().upper()
            team = str(getattr(row, "constructorName", "") or "").strip()
            if c:
                code_to_team[c] = team

    min_time_sec: float | None = None
    time_secs: list[float] = []
    has_time = "Time" in results_df.columns
    if has_time:
        for _, row in results_df.iterrows():
            t = row.get("Time")
            if t is not None and pd.notna(t):
                try:
                    sec = pd.to_timedelta(t).total_seconds()
                    if sec > 0:
                        time_secs.append(sec)
                except Exception:
                    pass
        min_time_sec = min(time_secs) if time_secs else None

    rows_for_image: list[dict] = []
    for _, row in results_df.head(22).iterrows():
        pos = row.get("Position")
        if pos is None:
            continue
        code = str(row.get("Abbreviation", "?") or row.get("DriverNumber", "?"))
        given = str(row.get("FirstName", "") or "")
        family = str(row.get("LastName", "") or "")
        full_name = f"{given} {family}".strip() or code
        team = str(row.get("TeamName", "") or "") or code_to_team.get(code.upper(), "")

        gap_str = "-"
        if has_time and min_time_sec is not None:
            t = row.get("Time")
            if t is not None and pd.notna(t):
                try:
                    sec = pd.to_timedelta(t).total_seconds()
                    if sec > 0:
                        if sec <= min_time_sec:
                            h, m = int(sec // 3600), int((sec % 3600) // 60)
                            s = sec % 60
                            gap_str = f"{h}:{m:02d}:{s:05.2f}" if h > 0 else f"{m}:{s:05.2f}"
                        else:
                            gap_str = f"+{sec - min_time_sec:.3f}"
                except Exception:
                    pass

        pts_val = row.get("Points")
        pts = int(float(pts_val)) if pts_val is not None and pd.notna(pts_val) else 0
        if pts == 0:
            try:
                pos_int = int(pos) if pos not in ("?", "", None) else 0
            except (TypeError, ValueError):
                pos_int = 0
            pts = points_for_race_position(pos_int)

        rows_for_image.append({
            "pos": int(pos) if pos != "?" else "?",
            "driver": full_name,
            "team": team,
            "gap_or_time": gap_str,
            "points": pts,
            "driver_code": code.upper() if code else "",
        })

    if not rows_for_image:
        await set_last_notified_round(season, round_num)
        return

    event_name = race_info.get("event_name", "Гран-при") or "Гран-при"

    def _render_race_image(fav_codes: set[str] | None = None):
        return create_f1_style_classification_image(
            event_name=event_name,
            session_type="RACE CLASSIFICATION",
            rows=rows_for_image,
            season=season,
            favorite_driver_codes=fav_codes,
        )

    # Общая картинка для групп (без избранных)
    photo_bytes_generic = (await asyncio.to_thread(_render_race_image, None)).getvalue()

    res_map = {}
    for _, row in results_df.iterrows():
        code = str(row.get("Abbreviation", "")).upper()
        pts = row.get("Points", 0)
        if pts is None or pd.isna(pts) or (isinstance(pts, (int, float)) and pts == 0):
            pos_val = row.get("Position")
            try:
                pts = points_for_race_position(int(pos_val)) if pos_val not in ("?", "", None) else 0
            except (TypeError, ValueError):
                pts = 0
        res_map[code] = {"pos": str(row.get("Position", "DNF")), "points": pts}

    constructor_standings = await get_constructor_standings_async(season, round_number=round_num)
    constructor_results_by_name = {}
    for row in results_df.itertuples(index=False):
        team_name = getattr(row, "TeamName", None)
        if team_name:
            if team_name not in constructor_results_by_name:
                constructor_results_by_name[team_name] = []
            constructor_results_by_name[team_name].append(row)

    sent_count = 0
    for tg_id, favs in users_favorites.items():
        fav_codes = {str(c).upper() for c in favs.get("drivers", [])}
        photo_bytes = (await asyncio.to_thread(_render_race_image, fav_codes)).getvalue()

        driver_res = []
        for code in favs.get("drivers", []):
            if code in res_map:
                driver_res.append({"code": code, **res_map[code]})

        team_res = []
        for team_name in favs.get("teams", []):
            team_rows = constructor_results_by_name.get(team_name)
            if team_rows is None:
                tn_lower = team_name.lower()
                for key, rows in constructor_results_by_name.items():
                    if tn_lower in key.lower() or key.lower() in tn_lower:
                        team_rows = rows
                        break
            if team_rows:
                total_pts = sum(float(getattr(r, "Points", 0) or 0) for r in team_rows)
                best_pos = min(int(getattr(r, "Position", 999)) for r in team_rows)
                team_res.append({"team": team_name, "text": f"P{best_pos}, +{int(total_pts)} очк."})

        caption = build_favorites_caption(race_info.get("event_name", "Гран-при"), driver_res, team_res)
        tz = tz_map.get(tg_id, "Europe/Moscow")
        quiet = is_quiet_hours(tz)
        if await safe_send_photo(
            bot, tg_id, photo_bytes,
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            disable_notification=quiet,
        ):
            sent_count += 1
        await asyncio.sleep(0.05)

    # Напоминание о голосовании — всем с включёнными уведомлениями (если ещё не отправляли)
    if voting_invite_sent is None or voting_invite_sent < round_num:
        voting_users = await get_users_with_settings(notifications_only=True)
        event_name = race_info.get("event_name", "Гран-при")
        voting_text = (
            f"🗳 <b>Приглашаем на голосование!</b>\n\n"
            f"🏁 {event_name} завершена.\n\n"
            f"Оцените этап по 5-балльной шкале и выберите пилота дня — "
            f"откройте раздел <b>Голосование</b> в MiniWebApp слева по кнопке."
        )
        for u in voting_users:
            tg_id, tz = u[0], u[1] or "Europe/Moscow"
            quiet = is_quiet_hours(tz)
            await safe_send_message(bot, tg_id, voting_text, parse_mode="HTML", disable_notification=quiet)
            await asyncio.sleep(0.05)
        await set_last_notified_voting_invite_round(season, round_num)

    # === Результаты в группы (общая картинка, без избранного) ===
    group_caption = f"🏁 {event_name} — этап {round_num}, сезон {season}\n\n📊 Результаты на картинке."
    for chat_id in group_chats:
        if await safe_send_photo(
            bot, chat_id, photo_bytes_generic,
            caption=group_caption,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(GROUP_TIMEZONE),
        ):
            sent_count += 1
        await asyncio.sleep(0.05)


# --- ЗАДАЧА 3: РЕЗУЛЬТАТЫ КВАЛИФИКАЦИИ ---

async def check_and_notify_quali(bot: Bot) -> None:
    """Картинка с общими результатами + текст по избранным пилотам под спойлером. Для групп — только картинка."""
    season = datetime.now(timezone.utc).year
    data = await _get_latest_quali_async(season)
    if not data or data[0] is None:
        return

    round_num, results = data
    last_notified = await get_last_notified_quali_round(season)
    if last_notified is not None and last_notified >= round_num:
        return

    users_favorites = await get_users_favorites_for_notifications()
    group_chats = await get_all_group_chats()
    if not users_favorites and not group_chats:
        await set_last_notified_quali_round(season, round_num)
        return

    users_settings = await get_users_with_settings()
    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users_settings}

    schedule = await get_season_schedule_short_async(season)
    race_info = next((r for r in schedule if r["round"] == round_num), None) if schedule else None

    driver_standings = await get_driver_standings_async(season, round_number=round_num)
    code_to_team: dict[str, str] = {}
    if not driver_standings.empty and "driverCode" in driver_standings.columns:
        for row in driver_standings.itertuples(index=False):
            c = str(getattr(row, "driverCode", "") or "").strip().upper()
            team = str(getattr(row, "constructorName", "") or "").strip()
            if c:
                code_to_team[c] = team

    rows_for_image: list[dict] = []
    for r in results:
        code = str(r.get("driver", "") or "").upper()
        name = r.get("name") or r.get("driver", "")
        rows_for_image.append({
            "pos": r.get("position", 0),
            "driver": name,
            "team": code_to_team.get(code, ""),
            "gap_or_time": r.get("gap") or r.get("best", "—"),
            "driver_code": code,
        })

    if not rows_for_image:
        await set_last_notified_quali_round(season, round_num)
        return

    # Сразу помечаем этап как «рассылаем», чтобы параллельный запуск job не дублировал
    await set_last_notified_quali_round(season, round_num)

    event_name = (race_info or {}).get("event_name", "") or f"Этап {round_num:02d}"

    def _render_quali_image(fav_codes: set[str] | None = None):
        return create_f1_style_classification_image(
            event_name=event_name,
            session_type="QUALIFYING CLASSIFICATION",
            rows=rows_for_image,
            season=season,
            favorite_driver_codes=fav_codes,
        )

    # Кэш для веб-апа: одни и те же результаты до следующей квалы/гонки
    def _segment(pos: int) -> str:
        return "Q3" if pos <= 10 else ("Q2" if pos <= 16 else "Q1")
    cache_payload = {
        "season": season,
        "round": round_num,
        "race_info": race_info,
        "results": [
            {
                "position": r.get("position", 0),
                "driver": r.get("driver", ""),
                "name": r.get("name", ""),
                "best": r.get("best", "-"),
                "segment": _segment(r.get("position", 0)),
            }
            for r in results
        ],
    }
    await set_cached_quali_results(season, cache_payload)

    quali_map = {str(r.get("driver", "")).upper(): r for r in results}

    # Общая картинка для групп (без избранных)
    photo_bytes_generic_quali = (await asyncio.to_thread(_render_quali_image, None)).getvalue()

    sent_count = 0
    for tg_id, favs in users_favorites.items():
        fav_codes = {str(c).upper() for c in favs.get("drivers", [])}
        img_buf = await asyncio.to_thread(_render_quali_image, fav_codes)
        photo_bytes = img_buf.getvalue()
        driver_res = []
        for code in favs.get("drivers", []):
            if code in quali_map:
                row = quali_map[code]
                driver_res.append({
                    "code": code,
                    "pos": str(row.get("position", "?")),
                    "points": 0,
                    "best": row.get("best", "-"),
                })

        lines = []
        for d in driver_res:
            pos_str = f"P{d['pos']}"
            if d["pos"] == "1": pos_str = "🥇 P1"
            elif d["pos"] == "2": pos_str = "🥈 P2"
            elif d["pos"] == "3": pos_str = "🥉 P3"
            lines.append(f"⏱ {d['code']}: {pos_str} ({d.get('best', '-')})")

        inner = "\n".join(lines) if lines else "📊 Результаты на картинке."
        caption = f"🏁 Квалификация (Этап {round_num})\n\n<tg-spoiler><b>🏎 Пилоты</b>\n{inner}</tg-spoiler>"
        tz = tz_map.get(tg_id, "Europe/Moscow")
        quiet = is_quiet_hours(tz)
        if await safe_send_photo(
            bot, tg_id, photo_bytes,
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            disable_notification=quiet,
        ):
            sent_count += 1
        await asyncio.sleep(0.05)

    # === Квалификация в группы (общая картинка) ===
    quali_caption = f"⏱ Квалификация — этап {round_num:02d}, сезон {season}\n\n📊 Результаты на картинке."
    for chat_id in group_chats:
        if await safe_send_photo(
            bot, chat_id, photo_bytes_generic_quali,
            caption=quali_caption,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(GROUP_TIMEZONE),
        ):
            sent_count += 1
        await asyncio.sleep(0.05)


# --- ЗАДАЧА 4: ИТОГИ ГОЛОСОВАНИЯ (3 дня после гонки) ---

DRIVER_VOTING_DAYS = 3


async def check_and_notify_voting_results(bot: Bot) -> None:
    """
    Через 3 дня после гонки отправляем итоги голосования:
    «По мнению нашего сообщества этап оценили на: X. Лучшим пилотом стал: Y.»
    """
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return

    last_notified = await get_last_notified_voting_round(season)
    now = datetime.now(timezone.utc).date()

    users = await get_users_with_settings(notifications_only=True)
    if not users:
        return

    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users}

    for event in schedule:
        round_num = event.get("round")
        if not round_num:
            continue
        if last_notified is not None and round_num <= last_notified:
            continue

        date_str = event.get("date")
        if not date_str:
            continue
        try:
            race_date = datetime.fromisoformat(date_str).date()
        except Exception:
            continue

        voting_closes = race_date + timedelta(days=DRIVER_VOTING_DAYS + 1)
        if now < voting_closes:
            continue

        results_df = await get_race_results_async(season, round_num)
        if results_df.empty:
            continue

        event_name = event.get("event_name", "Гран-при")
        avg_rating, race_count = await get_race_avg_for_round(season, round_num)
        driver_winner, driver_count = await get_driver_vote_winner(season, round_num)

        if race_count == 0 and driver_count == 0:
            await set_last_notified_voting_round(season, round_num)
            continue

        rating_str = f"{avg_rating:.1f} ★" if avg_rating is not None and race_count > 0 else "—"
        if driver_winner and driver_count > 0:
            driver_str = await get_driver_full_name_async(season, round_num, driver_winner)
        else:
            driver_str = "не выбран"

        text = (
            f"🗳 <b>Итоги голосования</b>\n\n"
            f"🏁 {event_name} (этап {round_num})\n\n"
            f"По мнению нашего сообщества этап оценили на: <b>{rating_str}</b>\n"
            f"Лучшим пилотом стал: <b>{driver_str}</b>"
        )

        sent_count = 0
        for tg_id in tz_map:
            quiet = is_quiet_hours(tz_map[tg_id])
            if await safe_send_message(bot, tg_id, text, parse_mode="HTML", disable_notification=quiet):
                sent_count += 1
            await asyncio.sleep(0.05)

        if sent_count > 0:
            logger.info(f"✅ Sent voting results for {event_name} to {sent_count} users.")
        await set_last_notified_voting_round(season, round_num)
        return