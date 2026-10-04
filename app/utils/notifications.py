import html
import asyncio
import logging
import aiosqlite
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.types import BufferedInputFile
from app.utils.mini_app_links import mini_app_button
from app.services.race_recap import get_race_recap, recap_caption
from app.utils.telegram_presentation import race_card, race_fallback, personal_buttons, rich_enabled
from app.services.delivery_adapters import queued_rich_message
from app.utils.time_tools import telegram_time
from app.services.web_notifications import classification as web_classification, publish_safely as publish_web, has_members as has_web_members

from app.db import (
    db,
    get_users_favorites_for_notifications,
    get_last_notified_round,
    set_last_notified_round,
    get_last_notified_quali_round,
    set_last_notified_quali_round,
    get_last_notified_sprint_quali_round,
    set_last_notified_sprint_quali_round,
    get_last_notified_sprint_round,
    set_last_notified_sprint_round,
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
    get_season_schedule_short_async,
    get_race_results_async,
    get_driver_standings_async,
    get_quali_for_round_async,
    get_sprint_quali_results_async,
    get_sprint_results_async,
    get_testing_results_async,
    get_driver_full_name_async,
    set_cached_quali_results,
)
from app.services.delivery_adapters import queued_message as safe_send_message, queued_photo as safe_send_photo
from app.utils.image_render import create_f1_style_classification_image

logger = logging.getLogger(__name__)

# --- ХЕЛПЕРЫ ОБЩИЕ ---

# Тихий режим: 21:00–10:00 по времени пользователя (без звука)
QUIET_START_HOUR = 21
QUIET_END_HOUR = 10

# Для групп: напоминать за 60 минут, таймзона UTC
GROUP_NOTIFY_BEFORE = 60
GROUP_TIMEZONE = "UTC"


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
    if minutes_left <= 0: return "УЖЕ ИДЁТ"
    if minutes_left >= 20 * 60: return "Уже завтра"
    hours = minutes_left // 60
    minutes = int(minutes_left % 60)
    parts = []
    if hours > 0: parts.append(f"{int(hours)} ч.")
    if minutes > 0: parts.append(f"{minutes} мин.")
    return f"Через {' '.join(parts)}" if parts else "Менее чем через минуту"


from app.session_reminders import session_enabled, reminder_intervals


def _event_reminder_key(event_kind: str, notify_before: int) -> tuple[bool, int]:
    """
    Возвращает (is_quali, notify_key) для дедупликации.
    В БД есть только is_quali + notify_before_min, поэтому для спринт-событий используем смещение.
    """
    base = int(notify_before)
    if event_kind in ("practice1", "practice2", "practice3"):
        return False, base + 2000 * (int(event_kind[-1]) + 1)
    if event_kind == "quali":
        return True, base
    if event_kind == "sprint":
        return False, base + 2000
    if event_kind == "sprint_quali":
        return True, base + 2000
    return False, base


def get_notification_text(
    race: dict,
    user_tz_name: str,
    minutes_left: int,
    for_quali: bool = False,
    event_kind: str | None = None,
    for_group: bool = False,
    phase: str | None = None,
    estimated: bool = False,
) -> str:
    """Reminder and in-place lifecycle text; groups omit the absolute time line."""
    if event_kind is None:
        event_kind = "quali" if for_quali else "race"
    event_name = html.escape(str(race.get('event_name') or 'Гран-при'))
    dt_key_map = {
        "race": "race_start_utc",
        "quali": "quali_start_utc",
        "sprint": "sprint_start_utc",
        "sprint_quali": "sprint_quali_start_utc",
        "practice1": "practice1_start_utc",
        "practice2": "practice2_start_utc",
        "practice3": "practice3_start_utc",
    }
    dt_key = dt_key_map.get(event_kind, "race_start_utc")
    dt_str = race.get(dt_key) or race.get("race_start_utc")
    try:
        dt_utc = datetime.fromisoformat(dt_str)
        if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        user_tz = ZoneInfo(user_tz_name)
        local_dt = dt_utc.astimezone(user_tz)
        start_time_str = local_dt.strftime("%H:%M")
        start_date_str = local_dt.strftime("%d.%m.%Y")
    except Exception:
        start_time_str = "??:??"
        start_date_str = "??.??.????"

    if phase is None:
        from app.services.reminder_status import session_phase, parse_utc
        started = parse_utc(dt_str)
        if started:
            phase, estimated = session_phase(race, event_kind, started-timedelta(minutes=minutes_left))
        else:
            phase = "before" if minutes_left > 0 else "unknown"
    titles = {
        "race": ("🏎", "Гонка", "Скоро гонка"),
        "quali": ("⏱", "Квалификация", "Скоро квалификация"),
        "sprint_quali": ("⏱", "Спринт-квалификация", "Скоро спринт-квалификация"),
        "sprint": ("⚡", "Спринт", "Скоро спринт"),
        **{f"practice{i}": ("🏎", f"Свободные заезды — FP{i}", f"Скоро свободные заезды — FP{i}") for i in (1, 2, 3)},
    }
    emoji, title, upcoming_title = titles.get(event_kind, titles["race"])
    time_suffix = " (UTC)" if user_tz_name == "UTC" else " (по вашему времени)"
    local_time = telegram_time(dt_str, user_tz_name, fallback=start_time_str + time_suffix)
    if phase == "before":
        heading = f"{emoji} {upcoming_title}!"
        countdown = telegram_time(dt_str, user_tz_name, relative=True, fallback=format_time_left(minutes_left))
        event_line = f"{countdown} старт: {event_name}" + (" 🏁" if event_kind == "race" else "")
        time_label = "Начало в"
    elif phase == "finished":
        heading = f"{emoji} {title}"
        label = "Этап прошёл" if event_kind == "race" else "Сессия прошла"
        event_line = f"🏁 {label}: {event_name}"
        time_label = "Начало было в"
    elif phase == "cancelled":
        heading = f"{emoji} {title} — отмена"
        event_line = f"Сессия отменена: {event_name}"
        time_label = "Планировалось начало в"
    else:
        heading = f"{emoji} {title} — УЖЕ ИДЁТ" if phase == "live" else f"{emoji} {title}"
        event_line = event_name
        time_label = "Начало было в"
    time_line = "" if for_group else f"⏰ {time_label} {local_time}\n"
    schedule_note = "Статус по расписанию.\n" if estimated else ""
    return (f"{heading}\n\n{event_line}\n"
            f"📍 Трасса: {html.escape(str(race.get('location') or ''))}\n"
            f"📅 Дата: {start_date_str}\n{time_line}{schedule_note}")


async def get_users_with_settings(notifications_only: bool = False):
    """Active recipients; notifications_enabled controls sound, not delivery.

    notifications_only is retained for compatibility with existing callers.
    """
    if not db.conn: await db.connect()
    try:
        q = (
            "SELECT telegram_id, timezone, notify_before, notifications_enabled, reminder_sessions, results_spoiler, notify_before_mask "
            "FROM users WHERE telegram_id IS NOT NULL AND archived_at IS NULL"
        )
        async with db.conn.execute(q) as cursor:
            rows = await cursor.fetchall()
            return [tuple(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        return []


# --- ЗАДАЧА 1: АНОНСЫ (ГОНКИ И ТЕСТЫ) ---

async def check_and_send_notifications(bot: Bot):
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule: return

    now = datetime.now(timezone.utc)
    upcoming_event = []  # (race_dict, minutes_left, event_kind)

    for r in schedule:
        if r.get("is_cancelled"):
            continue
        if not r.get("is_testing"):
            for kind in ("practice1", "practice2", "practice3"):
                try:
                    start = datetime.fromisoformat(r.get(f"{kind}_start_utc") or "")
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)
                    minutes_left = (start - now).total_seconds() / 60
                    if 0 < minutes_left <= 30 * 60:
                        upcoming_event.append((r, minutes_left, kind))
                except (ValueError, TypeError):
                    pass
        # Напоминание перед ГОНКОЙ
        if r.get("race_start_utc"):
            try:
                race_dt = datetime.fromisoformat(r["race_start_utc"])
                if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
                minutes_left = (race_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, "race"))
            except Exception:
                pass
        # Напоминание перед КВАЛИФИКАЦИЕЙ
        if r.get("quali_start_utc") and not r.get("is_testing"):
            try:
                quali_dt = datetime.fromisoformat(r["quali_start_utc"])
                if quali_dt.tzinfo is None: quali_dt = quali_dt.replace(tzinfo=timezone.utc)
                minutes_left = (quali_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, "quali"))
            except Exception:
                pass
        # Напоминание перед СПРИНТОМ
        if r.get("sprint_start_utc") and not r.get("is_testing"):
            try:
                sprint_dt = datetime.fromisoformat(r["sprint_start_utc"])
                if sprint_dt.tzinfo is None: sprint_dt = sprint_dt.replace(tzinfo=timezone.utc)
                minutes_left = (sprint_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, "sprint"))
            except Exception:
                pass
        # Напоминание перед СПРИНТ-КВАЛИФИКАЦИЕЙ
        if r.get("sprint_quali_start_utc") and not r.get("is_testing"):
            try:
                sprint_q_dt = datetime.fromisoformat(r["sprint_quali_start_utc"])
                if sprint_q_dt.tzinfo is None: sprint_q_dt = sprint_q_dt.replace(tzinfo=timezone.utc)
                minutes_left = (sprint_q_dt - now).total_seconds() / 60
                if 0 < minutes_left <= 30 * 60:
                    upcoming_event.append((r, minutes_left, "sprint_quali"))
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
            intervals = reminder_intervals(user[6] if len(user) > 6 else None, user[2])

            for race, mins, event_kind in upcoming_event:
                if not session_enabled(user[4] if len(user) > 4 else None, event_kind):
                    continue
                # Allowed lead times are at least 15 minutes apart: at most one
                # can fall into the +/-1 minute window on this scheduler tick.
                notify_min = next((value for value in intervals if abs(mins - value) <= half_window), None)
                if notify_min is None:
                    continue
                # The prediction-closing notice already says that qualifying
                # starts in two hours and links to the form. Do not send a
                # second generic reminder to the same private chat.
                closing_session = "sprint_quali" if (
                    race.get("sprint_quali_start_utc") or race.get("sprint_start_utc")
                ) else "quali"
                if not race.get("is_testing") and notify_min == 120 and event_kind == closing_session:
                    continue
                if abs(mins - notify_min) <= half_window:
                    round_num = race.get("round")
                    is_quali_key, notify_key = _event_reminder_key(event_kind, notify_min)
                    if round_num is not None:
                        if await was_reminder_sent(tg_id, season, round_num, is_quali_key, notify_key):
                            continue

                    if race.get("is_testing"):
                        text = (
                            f"🧪 Предсезонные тесты!\n\n"
                            f"Уже завтра: {race.get('event_name')}\n"
                            f"📍 Трасса: {race.get('location')}\n"
                            f"Не забудьте следить за результатами!"
                        )
                    else:
                        text = get_notification_text(race, tz, mins, event_kind=event_kind)

                    quiet = is_quiet_hours(tz)
                    if await safe_send_message(bot, tg_id, text, disable_notification=quiet, delivery_key=f'reminder:{season}:{round_num}:{event_kind}:{notify_min}', expires=datetime.now(timezone.utc).timestamp()+max(0,mins)*60):
                        sent_count += 1
                        if round_num is not None:
                            await set_reminder_sent(tg_id, season, round_num, is_quali_key, notify_key)
                    await asyncio.sleep(0.05)
        except Exception:
            continue

    # === Рассылка в группы (общая информация, без избранного) — один раз на группу ===
    group_chats_raw = await get_all_group_chats()
    group_chats = list(dict.fromkeys(group_chats_raw)) if group_chats_raw else []
    if group_chats:
        for race, mins, event_kind in upcoming_event:
            if event_kind.startswith("practice"):
                continue  # Individual preferences do not change group broadcasts.
            if abs(mins - GROUP_NOTIFY_BEFORE) <= half_window:
                round_num_g = race.get("round")
                is_quali_key, notify_key = _event_reminder_key(event_kind, GROUP_NOTIFY_BEFORE)
                text = get_notification_text(race, GROUP_TIMEZONE, mins, event_kind=event_kind, for_group=True)
                quiet = is_quiet_hours(GROUP_TIMEZONE)
                for chat_id in group_chats:
                    group_key = None
                    if round_num_g is not None:
                        group_key = -abs(int(chat_id))
                        if await was_reminder_sent(group_key, season, round_num_g, is_quali_key, notify_key):
                            continue
                    if await safe_send_message(bot, chat_id, text, parse_mode="HTML", disable_notification=quiet, delivery_key=f'reminder:{season}:{round_num_g}:{event_kind}:{GROUP_NOTIFY_BEFORE}', expires=datetime.now(timezone.utc).timestamp()+max(0,mins)*60):
                        sent_count += 1
                        if group_key is not None:
                            await set_reminder_sent(group_key, season, round_num_g, is_quali_key, notify_key)
                    await asyncio.sleep(0.05)

    if sent_count > 0:
        logger.info(f"✅ Sent {sent_count} event reminders.")


# --- ЗАДАЧА 2: РЕЗУЛЬТАТЫ (ГОНКИ И ТЕСТЫ) ---

RACE_RESULTS_MIN_ROWS = 10

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


SESSION_RESULTS_MIN_ROWS = 10


def _valid_driver_identity(code: str, name: str) -> bool:
    normalized_code = str(code or "").strip().upper()
    normalized_name = str(name or "").strip()
    return (
        2 <= len(normalized_code) <= 4
        and normalized_code.isalpha()
        and "?" not in normalized_name
        and normalized_name not in {"", normalized_code}
    )


def _format_session_value(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        seconds = pd.to_timedelta(value).total_seconds()
        if seconds > 0:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            remainder = seconds % 60
            return f"{hours}:{minutes:02d}:{remainder:06.3f}" if hours else f"{minutes}:{remainder:06.3f}"
    except Exception:
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat"} else "—"


def _clean_result_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _latest_finished_session(
    schedule: list[dict],
    datetime_key: str,
    elapsed_minutes: int,
    status_key: str | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc)
    finished = None
    finished_round = -1
    for event in schedule or []:
        if event.get("is_cancelled"):
            continue
        status = str(event.get(status_key) or "").strip().lower() if status_key else ""
        is_finished = False
        if status in {"completed", "results_ready"}:
            is_finished = True
        elif status:
            continue
        else:
            raw = event.get(datetime_key)
            if not raw:
                continue
            try:
                started = datetime.fromisoformat(raw)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                is_finished = now >= started + timedelta(minutes=elapsed_minutes)
            except (TypeError, ValueError):
                continue

        if is_finished:
            try:
                round_num = int(event.get("round"))
            except (TypeError, ValueError):
                round_num = finished_round + 1
            if finished is None or round_num > finished_round:
                finished = event
                finished_round = round_num
    return finished


async def _result_delivery_started(event_type: str, season: int, round_num: int) -> bool:
    """A restart must resume a partially queued result instead of baselining it away."""
    prefixes = {
        "sprint_qualifying_results": ("classification:{season}:{round}:20010:", "classification:{season}:{round}:20011:"),
        "sprint_results": ("classification:{season}:{round}:20020:", "classification:{season}:{round}:20021:"),
        "qualifying_results": ("classification:{season}:{round}:20000:", "classification:{season}:{round}:20001:"),
        "race_results": ("race-photo:{season}:{round}:", "race-favorites:{season}:{round}:"),
    }[event_type]
    patterns = tuple(prefix.format(season=season, round=round_num) + "%" for prefix in prefixes)
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM telegram_deliveries WHERE event_key LIKE ? OR event_key LIKE ? LIMIT 1", patterns
        )).fetchone()
    return row is not None


async def initialize_result_notification_state() -> bool:
    """Skip result-session backlog that already exists when the bot starts.

    Result notifications are live events, not a historical digest. Advancing each
    per-session watermark before the scheduler starts prevents a restart or a new
    deployment from replaying the latest completed weekend. A failed schedule
    lookup is reported as not ready so the guarded scheduler can retry this
    initialization without dispatching anything.
    """
    season = datetime.now(timezone.utc).year
    try:
        schedule = await get_season_schedule_short_async(season)
    except Exception:
        logger.exception(
            "[Startup Result Baseline] schedule lookup failed season=%s; result dispatch remains disabled",
            season,
        )
        return False

    if not schedule:
        logger.error(
            "[Startup Result Baseline] empty schedule season=%s; result dispatch remains disabled",
            season,
        )
        return False

    session_states = (
        (
            "sprint_qualifying_results",
            "sprint_quali_start_utc",
            45,
            "sprint_qualifying_status",
            get_last_notified_sprint_quali_round,
            set_last_notified_sprint_quali_round,
        ),
        (
            "sprint_results",
            "sprint_start_utc",
            30,
            "sprint_status",
            get_last_notified_sprint_round,
            set_last_notified_sprint_round,
        ),
        (
            "qualifying_results",
            "quali_start_utc",
            60,
            "qualifying_status",
            get_last_notified_quali_round,
            set_last_notified_quali_round,
        ),
        (
            "race_results",
            "race_start_utc",
            120,
            "race_status",
            get_last_notified_round,
            set_last_notified_round,
        ),
    )

    try:
        for event_type, datetime_key, elapsed, status_key, getter, setter in session_states:
            event = _latest_finished_session(schedule, datetime_key, elapsed, status_key)
            if event is None:
                continue
            round_num = int(event["round"])
            previous_round = await getter(season)
            if previous_round is not None and previous_round >= round_num:
                continue
            if await _result_delivery_started(event_type, season, round_num):
                logger.info(
                    "[Startup Result Baseline] event=%s season=%s round=%s delivery already started; resuming",
                    event_type, season, round_num,
                )
                continue
            await setter(season, round_num)
            logger.info(
                "[Startup Result Baseline] event=%s season=%s skipped_backlog_through_round=%s previous=%s",
                event_type,
                season,
                round_num,
                previous_round,
            )
    except Exception:
        logger.exception(
            "[Startup Result Baseline] state update failed season=%s; result dispatch remains disabled",
            season,
        )
        return False

    logger.info("[Startup Result Baseline] ready season=%s", season)
    return True


def _normalize_qualifying_results(results: list[dict], code_to_team: dict[str, str]) -> list[dict]:
    rows = []
    for result in results or []:
        code = str(result.get("driver", "") or "").strip().upper()
        name = str(result.get("name", "") or "").strip()
        if not _valid_driver_identity(code, name):
            return []
        try:
            position = int(result.get("position"))
        except (TypeError, ValueError):
            return []
        rows.append({
            "position": position,
            "code": code,
            "name": name,
            "team": code_to_team.get(code, ""),
            "display": result.get("gap") or result.get("best") or "—",
            "points": 0,
        })
    return sorted(rows, key=lambda row: row["position"])


def _normalize_sprint_results(results_df: pd.DataFrame, code_to_team: dict[str, str]) -> list[dict]:
    rows = []
    if results_df is None or results_df.empty:
        return rows
    for _, result in results_df.head(22).iterrows():
        try:
            position = int(result.get("Position"))
        except (TypeError, ValueError):
            return []
        code = _clean_result_text(result.get("Abbreviation", "")).upper()
        given = _clean_result_text(result.get("FirstName", ""))
        family = _clean_result_text(result.get("LastName", ""))
        name = f"{given} {family}".strip() or code
        if not _valid_driver_identity(code, name):
            return []
        team = _clean_result_text(result.get("TeamName", "")) or code_to_team.get(code, "")
        raw_points = result.get("Points", 0)
        try:
            points = int(float(raw_points)) if raw_points is not None and pd.notna(raw_points) else 0
        except (TypeError, ValueError):
            points = 0
        rows.append({
            "position": position,
            "code": code,
            "name": name,
            "team": team,
            "display": _format_session_value(result.get("Time")),
            "points": points,
        })
    return sorted(rows, key=lambda row: row["position"])


def _team_matches(favorite: str, actual: str) -> bool:
    fav = str(favorite or "").strip().lower()
    team = str(actual or "").strip().lower()
    return bool(fav and team and (fav in team or team in fav))


def _build_session_favorites_text(
    event_name: str,
    session_label: str,
    rows: list[dict],
    favorite_drivers: list[str],
    favorite_teams: list[str],
) -> str:
    by_code = {row["code"]: row for row in rows}
    sections = []
    driver_lines = []
    for raw_code in favorite_drivers:
        code = str(raw_code).upper()
        row = by_code.get(code)
        if row:
            driver_lines.append(f"• {code}: P{row['position']} ({row['display']})")
    if driver_lines:
        sections.append("<b>🏎 Пилоты</b>\n" + "\n".join(driver_lines))

    team_lines = []
    for favorite_team in favorite_teams:
        team_rows = [row for row in rows if _team_matches(favorite_team, row.get("team", ""))]
        if team_rows:
            best_position = min(row["position"] for row in team_rows)
            total_points = sum(row.get("points", 0) for row in team_rows)
            suffix = f", +{total_points} очк." if total_points else ""
            team_lines.append(f"• {favorite_team}: P{best_position}{suffix}")
    if team_lines:
        sections.append("<b>🏁 Команды</b>\n" + "\n".join(team_lines))

    if not sections:
        return ""
    inner = "\n\n".join(sections)
    return f"🏁 {event_name}\n{session_label}\n\n<tg-spoiler>{inner}</tg-spoiler>"


async def _load_code_to_team(season: int, round_num: int) -> dict[str, str]:
    try:
        standings = await get_driver_standings_async(season, round_number=round_num)
    except Exception:
        logger.exception("Failed to load driver standings for session notification")
        return {}
    mapping = {}
    if not standings.empty and "driverCode" in standings.columns:
        for row in standings.itertuples(index=False):
            code = str(getattr(row, "driverCode", "") or "").strip().upper()
            team = str(getattr(row, "constructorName", "") or "").strip()
            if code:
                mapping[code] = team
    return mapping


async def _deliver_session_classification(
    bot: Bot,
    season: int,
    round_num: int,
    event_name: str,
    session_label: str,
    image_session_type: str,
    rows: list[dict],
) -> bool:
    """Отправляет общую картинку всем и отдельный текст по избранному."""
    if len(rows) < SESSION_RESULTS_MIN_ROWS:
        logger.warning("%s round %s is incomplete: %s rows", session_label, round_num, len(rows))
        return False

    web_route = {"QUALIFYING CLASSIFICATION": "quali-results", "SPRINT QUALIFYING CLASSIFICATION": "sprint-quali-results", "SPRINT CLASSIFICATION": "sprint-results"}[image_session_type]
    await web_classification(season, round_num, f"{event_name} · {session_label}", web_route, rows)

    users_favorites = await get_users_favorites_for_notifications()
    group_chats = list(dict.fromkeys(await get_all_group_chats() or []))
    notification_users = await get_users_with_settings(notifications_only=True)
    if not notification_users:
        notification_users = await get_users_with_settings(notifications_only=False)
    if not users_favorites and not group_chats and not notification_users:
        return True

    image_rows = [{
        "pos": row["position"],
        "driver": row["name"],
        "team": row.get("team", ""),
        "gap_or_time": row.get("display", "—"),
        "points": row.get("points", 0),
        "driver_code": row["code"],
    } for row in rows]

    def _render():
        return create_f1_style_classification_image(
            event_name=event_name,
            session_type=image_session_type,
            rows=image_rows,
            season=season,
            favorite_driver_codes=None,
        )

    photo_bytes = (await asyncio.to_thread(_render)).getvalue()

    # Durable, per-recipient receipts: retry failed recipients without replaying
    # photos or favorites already delivered successfully. Keys don't overlap reminders.
    receipt_base = {
        "QUALIFYING CLASSIFICATION": 20000,
        "SPRINT QUALIFYING CLASSIFICATION": 20010,
        "SPRINT CLASSIFICATION": 20020,
    }[image_session_type]

    async def send_once(sender, chat_id, payload, *, receipt_part=0, **kwargs):
        key = receipt_base + receipt_part
        if await was_reminder_sent(chat_id, season, round_num, False, key):
            return True
        delivered = await sender(bot, chat_id, payload, delivery_key=f'classification:{season}:{round_num}:{key}', **kwargs)
        if delivered:
            await set_reminder_sent(chat_id, season, round_num, False, key)
        return delivered
    logger.info(
        "[Notification Trigger] session=%s season=%s round=%s recipients=%s groups=%s",
        image_session_type,
        season,
        round_num,
        len(notification_users),
        len(group_chats),
    )
    sent_count = 0
    failed_count = 0
    recipient_ids = set()
    for user in notification_users:
        tg_id, tz = user[0], user[1] or "Europe/Moscow"
        hide_results = bool(user[5]) if len(user) > 5 else False
        recipient_ids.add(tg_id)
        delivered = await send_once(
            safe_send_photo,
            tg_id,
            photo_bytes,
            caption=f"🏁 {session_label}: результаты на картинке." + (" Нажмите на спойлер, чтобы открыть." if hide_results else ""),
            parse_mode="HTML",
            has_spoiler=hide_results,
            disable_notification=is_quiet_hours(tz),
        )
        sent_count += int(delivered)
        failed_count += int(not delivered)
        await asyncio.sleep(0.05)

    settings = await get_users_with_settings()
    tz_map = {user[0]: (user[1] or "Europe/Moscow") for user in settings}
    for tg_id, favorites in users_favorites.items():
        if recipient_ids and tg_id not in recipient_ids:
            continue
        text = _build_session_favorites_text(
            event_name,
            session_label,
            rows,
            favorites.get("drivers", []),
            favorites.get("teams", []),
        )
        if not text:
            continue
        delivered = await send_once(
            safe_send_message,
            tg_id,
            text,
            receipt_part=1,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(tz_map.get(tg_id, "Europe/Moscow")),
        )
        sent_count += int(delivered)
        failed_count += int(not delivered)
        await asyncio.sleep(0.05)

    group_caption = f"🏁 {session_label} — этап {round_num:02d}, сезон {season}\n\n📊 Результаты на картинке."
    for chat_id in group_chats:
        delivered = await send_once(
            safe_send_photo,
            chat_id,
            photo_bytes,
            caption=group_caption,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(GROUP_TIMEZONE),
        )
        sent_count += int(delivered)
        failed_count += int(not delivered)
        await asyncio.sleep(0.05)

    logger.info(
        "[Delivery Confirmation] session=%s season=%s round=%s delivered=%s failed=%s",
        image_session_type, season, round_num, sent_count, failed_count,
    )
    return failed_count == 0


async def check_and_send_results(bot: Bot):
    season = datetime.now(timezone.utc).year
    last_notified = await get_last_notified_round(season)
    schedule = await get_season_schedule_short_async(season)

    # Ищем последнюю завершенную
    now = datetime.now(timezone.utc)
    finished_event = None

    for r in schedule:
        if not r.get("race_start_utc"): continue
        race_status = str(r.get("race_status") or "").strip().lower()
        if race_status in {"completed", "results_ready"}:
            finished_event = r
            continue
        if race_status and race_status not in {"completed", "results_ready"}:
            continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None: race_dt = race_dt.replace(tzinfo=timezone.utc)
            # Не читаем live-позиции как финальную классификацию: обычную гонку
            # начинаем проверять не раньше чем через два часа после старта.
            finish_offset = 9 if r.get("is_testing") else 2

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
            if await safe_send_message(bot, user[0], text, disable_notification=quiet, delivery_key=f'testing:{season}:{round_num}'):
                sent_count += 1
            await asyncio.sleep(0.05)
        for chat_id in group_chats:
            if await safe_send_message(bot, chat_id, text, disable_notification=is_quiet_hours(GROUP_TIMEZONE), delivery_key=f'testing:{season}:{round_num}'):
                sent_count += 1
            await asyncio.sleep(0.05)

        if sent_count > 0:
            await set_last_notified_round(season, round_num)
        else:
            logger.warning(f"⚠️ Testing results delivery failed for round {round_num}, will retry.")
        return

    # === ЛОГИКА ДЛЯ ГОНОК: картинка + текст по избранным под спойлером ===
    logger.info("[Result Ingestion] event=race_results season=%s round=%s", season, round_num)
    results_df = await get_race_results_async(season, round_num)
    if results_df is None:
        results_df = pd.DataFrame()

    # Проверяем, что данные полные (нет ??)
    data_incomplete = (
        "DataComplete" in results_df.columns
        and not results_df["DataComplete"].fillna(False).all()
    )
    if not results_df.empty and len(results_df) >= 10 and "Points" in results_df.columns:
        top_ten = results_df[pd.to_numeric(results_df["Position"], errors="coerce").between(1, 10)]
        if len(top_ten) >= 10 and pd.to_numeric(top_ten["Points"], errors="coerce").fillna(0).eq(0).all():
            data_incomplete = True
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
                f"🏁 {event_name}.\n\n"
                f"Оцените этап по 5-балльной шкале и выберите пилота дня — "
                f"нажмите кнопку ниже, чтобы открыть голосование в Mini App."
            )
            voting_keyboard = await mini_app_button(
                bot, "🗳 Оценить этап", "/voting", season=season, round=round_num,
            )
            for u in voting_users:
                tg_id, tz = u[0], u[1] or "Europe/Moscow"
                quiet = is_quiet_hours(tz)
                await safe_send_message(bot, tg_id, voting_text, parse_mode="HTML", disable_notification=quiet, reply_markup=voting_keyboard, delivery_key=f'voting-invite:{season}:{round_num}')
                await asyncio.sleep(0.05)
            await set_last_notified_voting_invite_round(season, round_num)
            logger.info(f"🗳 Sent voting invite for {event_name} (no results yet)")
        return

    users_favorites = await get_users_favorites_for_notifications()
    group_chats = await get_all_group_chats()
    notifications_users = await get_users_with_settings(notifications_only=True)
    if not notifications_users:
        # Legacy fallback: старые пользователи могли остаться с notifications_enabled=0 после миграции.
        notifications_users = await get_users_with_settings(notifications_only=False)
    if not users_favorites and not group_chats and not notifications_users and not await has_web_members():
        await set_last_notified_round(season, round_num)
        return

    users_settings = await get_users_with_settings()
    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users_settings}

    # Картинка с общими результатами (без звёздочек для избранных — одна картинка на всех)
    race_info = finished_event
    if "Position" in results_df.columns:
        results_df = results_df.sort_values("Position")

    try:
        driver_standings = await get_driver_standings_async(season, round_number=round_num)
    except Exception:
        logger.exception("Failed to load driver standings while preparing race notification")
        driver_standings = pd.DataFrame()
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

        rows_for_image.append({
            "pos": int(pos) if pos != "?" else "?",
            "driver": full_name,
            "team": team,
            "gap_or_time": gap_str,
            "points": pts,
            "driver_code": code.upper() if code else "",
        })

    if len(rows_for_image) < RACE_RESULTS_MIN_ROWS:
        logger.warning(
            "⚠️ Race results for round %s are incomplete (%s rows), will retry later.",
            round_num,
            len(rows_for_image),
        )
        return

    logger.info(
        "[Notification Trigger] event=race_results season=%s round=%s rows=%s",
        season,
        round_num,
        len(rows_for_image),
    )

    event_name = race_info.get("event_name", "Гран-при") or "Гран-при"

    def _render_race_image(fav_codes: set[str] | None = None):
        return create_f1_style_classification_image(
            event_name=event_name,
            session_type="RACE CLASSIFICATION",
            rows=rows_for_image,
            season=season,
            favorite_driver_codes=fav_codes,
        )

    notification_recipients = [(u[0], u[1] or "Europe/Moscow", bool(u[5]) if len(u) > 5 else False) for u in notifications_users]
    use_rich = rich_enabled()
    # One verified classification image is shared by rich and ordinary sends.
    photo_bytes_generic = (await asyncio.to_thread(_render_race_image, None)).getvalue()
    await web_classification(season, round_num, f"{race_info.get('event_name', 'Гран-при')} · Итоги гонки", "race-results", [
        {"position": str(row.get("Position", "—")), "code": str(row.get("Abbreviation", "")),
         "name": str(row.get("FullName", row.get("Abbreviation", ""))), "team": str(row.get("TeamName", "")),
         "points": row.get("Points"), "data_complete": bool(row.get("DataComplete", True))} for _, row in results_df.iterrows()
    ])
    await publish_web(f"voting-invite:{season}:{round_num}", "Приглашаем на голосование", "Оцените этап и выберите пилота дня.", f"/voting?season={season}&round={round_num}")

    res_map = {}
    for _, row in results_df.iterrows():
        code = str(row.get("Abbreviation", "")).upper()
        pts = row.get("Points", 0)
        if pts is None or pd.isna(pts):
            pts = 0
        res_map[code] = {"pos": str(row.get("Position", "DNF")), "points": pts}

    constructor_results_by_name = {}
    for row in results_df.itertuples(index=False):
        team_name = getattr(row, "TeamName", None)
        if team_name:
            if team_name not in constructor_results_by_name:
                constructor_results_by_name[team_name] = []
            constructor_results_by_name[team_name].append(row)

    sent_count = 0
    # Classification image and recap in one rich message, or a spoiler photo.
    try:
        recap = await asyncio.wait_for(get_race_recap(season, round_num), timeout=15)
    except Exception:
        logger.warning("Recap unavailable for %s round %s; classification delivery continues", season, round_num)
        recap = {"items": []}
    results_keyboard = await mini_app_button(
        bot, "🏁 Результаты на сайте", "/race-results",
        season=season, round=round_num, mode="archive",
    )
    results_keyboard = personal_buttons(season, round_num, results_keyboard)
    card = race_card(event_name, season, round_num, rows_for_image, recap,
                     photo=BufferedInputFile(photo_bytes_generic, filename=f'race-{season}-{round_num}.png'))
    fallback = race_fallback(event_name, season, round_num, rows_for_image, recap)
    for tg_id, tz, hide_results in notification_recipients:
        if use_rich and not hide_results:
            queued = await queued_rich_message(
                bot, tg_id, card,
                fallback,
                delivery_key=f'race-photo:{season}:{round_num}',
                reply_markup=results_keyboard, disable_notification=is_quiet_hours(tz),
            )
        else:
            queued = await safe_send_photo(
                bot,
                tg_id,
                photo_bytes_generic,
                delivery_key=f'race-photo:{season}:{round_num}',
                caption="🏁 Результаты гонки на картинке." + (" Изображение скрыто как спойлер — нажмите, чтобы открыть." if hide_results else "") + recap_caption(recap, spoiler=hide_results),
                parse_mode="HTML",
                has_spoiler=hide_results,
                reply_markup=results_keyboard,
                disable_notification=is_quiet_hours(tz),
            )
        if queued:
            sent_count += 1
        await asyncio.sleep(0.05)

    for tg_id, favs in users_favorites.items():
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

        if not driver_res and not team_res:
            continue
        caption = build_favorites_caption(race_info.get("event_name", "Гран-при"), driver_res, team_res)
        tz = tz_map.get(tg_id, "Europe/Moscow")
        quiet = is_quiet_hours(tz)
        if await safe_send_message(
            bot,
            tg_id,
            caption,
            delivery_key=f'race-favorites:{season}:{round_num}',
            parse_mode="HTML",
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
            f"🏁 {event_name}.\n\n"
            f"Оцените этап по 5-балльной шкале и выберите пилота дня — "
            f"нажмите кнопку ниже, чтобы открыть голосование в Mini App."
        )
        voting_keyboard = await mini_app_button(
            bot, "🗳 Оценить этап", "/voting", season=season, round=round_num,
        )
        for u in voting_users:
            tg_id, tz = u[0], u[1] or "Europe/Moscow"
            quiet = is_quiet_hours(tz)
            await safe_send_message(bot, tg_id, voting_text, parse_mode="HTML", disable_notification=quiet, reply_markup=voting_keyboard, delivery_key=f'voting-invite:{season}:{round_num}')
            await asyncio.sleep(0.05)
        await set_last_notified_voting_invite_round(season, round_num)

    # === Public group classification, with private personal callbacks ===
    group_caption = f"🏁 {html.escape(event_name)} — этап {round_num}, сезон {season}\n\n📊 Результаты на картинке." + recap_caption(recap)
    for chat_id in group_chats:
        if use_rich:
            queued = await queued_rich_message(
                bot, chat_id, card, fallback,
                delivery_key=f'race-photo:{season}:{round_num}',
                reply_markup=personal_buttons(season, round_num),
                disable_notification=is_quiet_hours(GROUP_TIMEZONE),
            )
        else:
            queued = await safe_send_photo(
                bot, chat_id, photo_bytes_generic,
                delivery_key=f'race-photo:{season}:{round_num}',
                caption=group_caption,
                parse_mode="HTML",
                reply_markup=personal_buttons(season, round_num),
                disable_notification=is_quiet_hours(GROUP_TIMEZONE),
            )
        if queued:
            sent_count += 1
        await asyncio.sleep(0.05)

    if sent_count > 0:
        await set_last_notified_round(season, round_num)
        logger.info(
            "[Delivery Confirmation] event=race_results season=%s round=%s delivered=%s",
            season,
            round_num,
            sent_count,
        )
    else:
        logger.warning(f"⚠️ Race results delivery failed for round {round_num}, will retry.")


# --- ЗАДАЧА 3: РЕЗУЛЬТАТЫ КВАЛИФИКАЦИИ ---

async def check_and_notify_quali(bot: Bot) -> bool:
    """Отправляет полную квалификацию и отдельное сообщение по избранному."""
    season = datetime.now(timezone.utc).year
    logger.info("[Result Ingestion] event=qualifying_results season=%s", season)
    schedule = await get_season_schedule_short_async(season)
    race_info = _latest_finished_session(schedule, "quali_start_utc", 60, "qualifying_status")
    if race_info is None:
        return True
    expected_round = int(race_info["round"])
    last_notified = await get_last_notified_quali_round(season)
    if last_notified is not None and last_notified >= expected_round:
        return True
    data = await get_quali_for_round_async(season, expected_round)
    if not data or data[0] is None:
        return False

    round_num, results = data
    if round_num != expected_round:
        logger.warning("Qualifying feed returned round %s, expected %s; will retry", round_num, expected_round)
        return False

    code_to_team = await _load_code_to_team(season, round_num)
    normalized_rows = _normalize_qualifying_results(results, code_to_team)
    if len(normalized_rows) < SESSION_RESULTS_MIN_ROWS:
        logger.warning(
            "⚠️ Quali results for round %s have missing drivers or incomplete rows; will retry.",
            round_num,
        )
        return False

    event_name = (race_info or {}).get("event_name", "") or f"Этап {round_num:02d}"

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

    delivered = await _deliver_session_classification(
        bot,
        season,
        round_num,
        event_name,
        "Квалификация",
        "QUALIFYING CLASSIFICATION",
        normalized_rows,
    )
    if delivered:
        await set_last_notified_quali_round(season, round_num)
    else:
        logger.warning(f"⚠️ Quali results delivery failed for round {round_num}, will retry.")
    return delivered


async def check_and_notify_sprint_quali(bot: Bot) -> bool:
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    event = _latest_finished_session(
        schedule,
        "sprint_quali_start_utc",
        45,
        "sprint_qualifying_status",
    )
    if event is None:
        return True
    round_num = int(event["round"])
    last_notified = await get_last_notified_sprint_quali_round(season)
    if last_notified is not None and last_notified >= round_num:
        return True

    logger.info(
        "[Result Ingestion] event=sprint_qualifying_results season=%s round=%s",
        season,
        round_num,
    )
    results = await get_sprint_quali_results_async(season, round_num, limit=100)
    code_to_team = await _load_code_to_team(season, round_num)
    normalized_rows = _normalize_qualifying_results(results, code_to_team)
    if len(normalized_rows) < SESSION_RESULTS_MIN_ROWS:
        logger.warning("Sprint qualifying round %s is incomplete; will retry.", round_num)
        return False

    delivered = await _deliver_session_classification(
        bot,
        season,
        round_num,
        event.get("event_name", f"Этап {round_num:02d}"),
        "Спринт-квалификация",
        "SPRINT QUALIFYING CLASSIFICATION",
        normalized_rows,
    )
    if delivered:
        await set_last_notified_sprint_quali_round(season, round_num)
    return delivered


async def check_and_notify_sprint(bot: Bot) -> bool:
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    event = _latest_finished_session(schedule, "sprint_start_utc", 30, "sprint_status")
    if event is None:
        return True
    round_num = int(event["round"])
    last_notified = await get_last_notified_sprint_round(season)
    if last_notified is not None and last_notified >= round_num:
        return True

    logger.info("[Result Ingestion] event=sprint_results season=%s round=%s", season, round_num)
    results_df = await get_sprint_results_async(season, round_num)
    code_to_team = await _load_code_to_team(season, round_num)
    normalized_rows = _normalize_sprint_results(results_df, code_to_team)
    if len(normalized_rows) < SESSION_RESULTS_MIN_ROWS:
        logger.warning("Sprint round %s is incomplete; will retry.", round_num)
        return False

    delivered = await _deliver_session_classification(
        bot,
        season,
        round_num,
        event.get("event_name", f"Этап {round_num:02d}"),
        "Спринт",
        "SPRINT CLASSIFICATION",
        normalized_rows,
    )
    if delivered:
        await set_last_notified_sprint_round(season, round_num)
    return delivered


RESULT_NOTIFICATION_HANDLERS = {
    "sprint_qualifying_results": "check_and_notify_sprint_quali",
    "sprint_results": "check_and_notify_sprint",
    "qualifying_results": "check_and_notify_quali",
    "race_results": "check_and_send_results",
}


async def check_and_send_session_results(bot: Bot) -> None:
    """Poll every result event independently so one unavailable feed cannot block another."""
    for event_type, handler_name in RESULT_NOTIFICATION_HANDLERS.items():
        try:
            logger.info("[Result Ingestion] pipeline_poll event=%s", event_type)
            handler = globals()[handler_name]
            await handler(bot)
        except Exception:
            logger.exception("Result notification pipeline failed for event=%s", event_type)


# --- ЗАДАЧА 4: ИТОГИ ГОЛОСОВАНИЯ (3 дня после гонки) ---

DRIVER_VOTING_DAYS = 3
VOTING_RESULTS_NOTIFY_KEY = 10000


def _voting_closes_at(event: dict) -> datetime | None:
    from app.utils.voting_window import voting_closes_at
    return voting_closes_at(event)

async def check_and_notify_voting_results(bot: Bot, *, not_before: datetime | None = None) -> None:
    """
    Сразу после закрытия трёхдневного окна отправляем итоги голосования:
    «По мнению нашего сообщества этап оценили на: X. Лучшим пилотом стал: Y.»
    """
    season = datetime.now(timezone.utc).year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return

    last_notified = await get_last_notified_voting_round(season)
    now_utc = datetime.now(timezone.utc)
    users = await get_users_with_settings(notifications_only=True)
    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users}
    for chat_id in await get_all_group_chats() or []:
        tz_map.setdefault(chat_id, GROUP_TIMEZONE)

    for event in sorted(schedule, key=lambda row: int(row.get("round") or 0)):
        if event.get("is_cancelled"):
            continue
        round_num = event.get("round")
        if not round_num:
            continue
        if last_notified is not None and round_num <= last_notified:
            continue

        voting_closes_at = _voting_closes_at(event)
        if voting_closes_at is None or now_utc < voting_closes_at:
            continue
        if not_before is not None and voting_closes_at < not_before:
            # Old voting results are not a startup digest.
            await set_last_notified_voting_round(season, round_num)
            continue
        if not tz_map and not await has_web_members():
            continue

        event_name = event.get("event_name", "Гран-при")
        avg_rating, race_count = await get_race_avg_for_round(season, round_num)
        driver_winner, driver_count = await get_driver_vote_winner(season, round_num)

        if race_count == 0 and driver_count == 0:
            await set_last_notified_voting_round(season, round_num)
            continue

        rating_str = f"{avg_rating:.1f} ★" if avg_rating is not None and race_count > 0 else "—"
        if driver_winner and driver_count > 0:
            try:
                driver_str = await get_driver_full_name_async(season, round_num, driver_winner)
            except Exception:
                logger.exception(
                    "Failed to resolve driver name for voting results: season=%s round=%s code=%s",
                    season,
                    round_num,
                    driver_winner,
                )
                driver_str = driver_winner
        else:
            driver_str = "не выбран"

        def count_word(count: int, one: str, few: str, many: str) -> str:
            return one if count % 10 == 1 and count % 100 != 11 else (
                few if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else many
            )

        text = (
            f"🗳 <b>Итоги голосования</b>\n\n"
            f"🏁 {html.escape(str(event_name))} (этап {round_num})\n\n"
            f"Оценка гонки: <b>{rating_str}</b> ({race_count} {count_word(race_count, 'оценка', 'оценки', 'оценок')})\n"
            f"Лидер голосования за пилота: <b>{html.escape(str(driver_str))}</b> ({driver_count} {count_word(driver_count, 'голос', 'голоса', 'голосов')} за него)\n\n"
            "Это мнение проголосовавших, а не официальный результат этапа."
        )

        await publish_web(f"voting-results:{season}:{round_num}", "Итоги голосования", text, f"/voting?season={season}&round={round_num}")
        sent_count = 0
        for tg_id in tz_map:
            tz_name = tz_map[tg_id]
            if await was_reminder_sent(tg_id, season, round_num, False, VOTING_RESULTS_NOTIFY_KEY):
                continue

            quiet = is_quiet_hours(tz_name)
            if await safe_send_message(bot, tg_id, text, parse_mode="HTML", disable_notification=quiet, delivery_key=f'voting-results:{season}:{round_num}'):
                sent_count += 1
                await set_reminder_sent(tg_id, season, round_num, False, VOTING_RESULTS_NOTIFY_KEY)
            await asyncio.sleep(0.05)

        if sent_count > 0:
            logger.info(f"✅ Sent voting results for {event_name} to {sent_count} users.")
        else:
            logger.info(
                "Voting results for %s are pending: no eligible delivery succeeded in this run.",
                event_name,
            )

        all_users_notified = True
        for tg_id in tz_map:
            if not await was_reminder_sent(tg_id, season, round_num, False, VOTING_RESULTS_NOTIFY_KEY):
                all_users_notified = False
                break

        if all_users_notified:
            await set_last_notified_voting_round(season, round_num)
        return
