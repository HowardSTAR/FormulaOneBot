import asyncio

import pandas as pd
from collections import defaultdict
from datetime import datetime, date, timezone, timedelta

from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
)

from app.db import (
    get_favorite_drivers, get_favorite_teams, get_user_settings
)
from app.f1_data import (
    get_season_schedule_short_async, get_weekend_schedule, get_race_results_async,
    get_constructor_standings_async, get_driver_standings_async,
    get_quali_for_round_async, _get_latest_quali_async,
    points_for_race_position,
)
from app.utils.default import SESSION_NAME_RU, validate_f1_year
from app.utils.image_render import (
    create_f1_style_classification_image, create_season_image
)
from app.utils.loader import Loader
from app.utils.safe_send import safe_answer_callback
from app.utils.time_tools import format_race_time

router = Router()
UTC_PLUS_3 = timezone(timedelta(hours=3))


class RacesYearState(StatesGroup):
    year = State()


async def _notify_callback_user(callback: CallbackQuery, text: str, show_alert: bool = False) -> None:
    """
    Пытается показать уведомление через callback answer.
    Если query протух, отправляет обычное сообщение в чат как fallback.
    """
    shown = await safe_answer_callback(callback, text, show_alert=show_alert)
    if shown:
        return
    if callback.message:
        try:
            await callback.message.answer(text)
        except Exception:
            pass


def _parse_utc_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _get_latest_started_weekend_round(schedule: list, now: datetime) -> int | None:
    latest_started_round = None
    for r in schedule:
        candidates: list[datetime] = []
        for key in (
            "first_session_start_utc",
            "sprint_quali_start_utc",
            "quali_start_utc",
            "sprint_start_utc",
            "race_start_utc",
        ):
            dt = _parse_utc_iso(r.get(key))
            if dt is not None:
                candidates.append(dt)

        if not candidates:
            continue

        weekend_start = min(candidates)
        if weekend_start <= now:
            latest_started_round = r.get("round")
        else:
            break

    return latest_started_round


def _should_reset_previous_results(schedule: list, now: datetime, results_round: int | None) -> bool:
    if results_round is None:
        return False
    started_round = _get_latest_started_weekend_round(schedule, now)
    if started_round is None:
        return False
    try:
        return int(results_round) < int(started_round)
    except Exception:
        return False


async def build_next_race_payload(season: int | None = None, user_id: int | None = None) -> dict:
    """
    Возвращает инфу о ближайшей гонке.
    Добавляет поле fmt_date для сайта.
    """
    if season is None: season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)
    if not schedule: return {"status": "no_schedule", "season": season}

    today = date.today()
    future_races = [r for r in schedule if date.fromisoformat(r["date"]) >= today] if schedule else []

    if not future_races: return {"status": "season_finished", "season": season}

    r = future_races[0]
    race_start_utc_str = r.get("race_start_utc")

    local_str = None
    utc_str = None

    if race_start_utc_str:
        user_tz = "Europe/Moscow"
        if user_id:
            s = await get_user_settings(user_id)
            user_tz = s.get("timezone", "Europe/Moscow")

        # Для БОТА: Красивая строка с месяцем (8 марта...)
        local_str = format_race_time(race_start_utc_str, user_tz)
        try:
            utc_dt = datetime.fromisoformat(race_start_utc_str)
            utc_str = utc_dt.strftime("%d.%m.%Y %H:%M UTC")
        except:
            utc_str = race_start_utc_str

    return {
        "status": "ok", "season": season, "round": r["round"],
        "event_name": r["event_name"], "country": r["country"], "location": r["location"],
        "date": r["date"], "utc": utc_str,
        "is_cancelled": bool(r.get("is_cancelled", False)),
        "local": local_str,  # Оставляем для бота
        "fmt_date": r.get("local")
    }


async def _send_next_race_message(message: Message, user_id: int, season: int | None = None, is_edit: bool = False):
    payload = await build_next_race_payload(season, user_id)

    if payload["status"] != "ok":
        text = f"Сезон {payload['season']} завершен или нет данных."
        if is_edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    time_block = f"\n⏰ Старт гонки: {payload['local']}" if payload['local'] else f"📅 {payload['date']}"

    text = (
        f"🗓 Ближайший этап сезона {payload['season']}:\n\n"
        f"{payload['round']:02d}. {payload['event_name']}\n"
        f"📍 {payload['country']}, {payload['location']}\n"
        f"{time_block}\n\n"
        f"Уведомлю о результатах после финиша."
    )

    is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    keyboard = [
        [InlineKeyboardButton(text="📅 Расписание уикенда",
                              callback_data=f"weekend_{payload['season']}_{payload['round']}")],
        [InlineKeyboardButton(text="⏱ Квалификация", callback_data=f"quali_{payload['season']}_{payload['round']}"),
         InlineKeyboardButton(text="🏁 Гонка", callback_data=f"race_{payload['season']}_{payload['round']}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")],
    ]
    if not is_group:
        keyboard[-1].append(InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"settings_race_{payload['season']}"))
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("next_race"))
async def cmd_next_race(message: Message):
    user_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_next_race_message(message, user_id)


@router.message(F.text == "🏁 Следующая гонка")
async def next_race_btn(message: Message):
    user_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_next_race_message(message, user_id)


@router.callback_query(F.data.startswith("back_to_race_"))
async def back_to_race(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        season = int(callback.data.split("_")[-1])
    except:
        season = None

    user_id = callback.from_user.id if callback.message.chat.type == ChatType.PRIVATE else None
    if callback.message and callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _send_next_race_message(callback.message, user_id, season, False)
    else:
        await _send_next_race_message(callback.message, user_id, season, True)


@router.callback_query(F.data.startswith("weekend_"))
async def weekend_schedule(callback: CallbackQuery):
    try:
        parts = callback.data.split("_")
        season, round_num = int(parts[1]), int(parts[2])
    except:
        await safe_answer_callback(callback, "Ошибка данных")
        return

    sessions = get_weekend_schedule(season, round_num)
    if callback.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        user_tz = "Europe/Moscow"
    else:
        settings = await get_user_settings(callback.from_user.id)
        user_tz = settings.get("timezone", "Europe/Moscow")

    lines = []
    for s in sessions:
        ru_name = SESSION_NAME_RU.get(s["name"], s["name"])
        # Для расписания в боте используем format_race_time (UTC+X)
        time_str = format_race_time(s.get("utc_iso"), user_tz)
        lines.append(f"• {ru_name}\n  {time_str}")

    text = f"📅 Расписание уикенда (Сезон {season}, Этап {round_num}):\n\n" + "\n\n".join(lines)

    is_group = callback.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    kb_rows = [[InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"back_to_race_{season}")]]
    if not is_group:
        kb_rows.insert(0, [InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"settings_race_{season}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith("quali_"))
async def quali_callback(callback: CallbackQuery) -> None:
    try:
        parts = callback.data.split("_")
        season = int(parts[1])
        round_from_btn = int(parts[2]) if len(parts) > 2 else None
    except Exception:
        season = datetime.now().year
        round_from_btn = None

    async with Loader(callback.message, "⏳ Загружаю результаты квалификации..."):
        # Сначала пробуем квалификацию именно этого этапа (по кнопке), затем «последнюю»
        if round_from_btn is not None:
            latest_round, results = await get_quali_for_round_async(season, round_from_btn, limit=100)
        else:
            latest_round, results = None, []

        schedule = await get_season_schedule_short_async(season)
        now = datetime.now(timezone.utc)

        if round_from_btn is not None and not results:
            target_round = next((r for r in (schedule or []) if r.get("round") == round_from_btn), None)
            qutc = (target_round or {}).get("quali_start_utc")
            if qutc:
                try:
                    qdt = datetime.fromisoformat(qutc)
                    if qdt.tzinfo is None:
                        qdt = qdt.replace(tzinfo=timezone.utc)
                    if now < qdt:
                        await _notify_callback_user(callback, "Квалификация еще не прошла", show_alert=True)
                        return
                except Exception:
                    pass

        if not results:
            latest_round, results = await _get_latest_quali_async(season, limit=100)

        if not latest_round or not results:
            await _notify_callback_user(callback, "Квалификация еще не прошла", show_alert=True)
            return

        if _should_reset_previous_results(schedule or [], now, latest_round):
            await _notify_callback_user(callback, "Данных по квалификации еще нет", show_alert=True)
            return

        race_info = next((r for r in (schedule or []) if r.get("round") == latest_round), None)
        event_name = (race_info or {}).get("event_name", "") or f"Этап {latest_round:02d}"

        driver_standings = await get_driver_standings_async(season, latest_round)
        code_to_team: dict[str, str] = {}
        if not driver_standings.empty and "driverCode" in driver_standings.columns:
            for row in driver_standings.itertuples(index=False):
                code = str(getattr(row, "driverCode", "") or "").strip().upper()
                team = str(getattr(row, "constructorName", "") or "").strip()
                if code:
                    code_to_team[code] = team

        fav_driver_codes: set[str] = set()
        if callback.message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            fav_driver_codes = {str(c).upper() for c in await get_favorite_drivers(callback.from_user.id)}

        rows_for_image: list[dict] = []
        for r in results:
            code = str(r.get("driver", "") or "").upper()
            name = r.get("name") or r.get("driver", "")
            rows_for_image.append({
                "pos": r["position"],
                "driver": name,
                "team": code_to_team.get(code, ""),
                "gap_or_time": r.get("gap") or r.get("best", "—"),
                "driver_code": code,
            })

        img_buf = await asyncio.to_thread(
            create_f1_style_classification_image,
            event_name=event_name,
            session_type="QUALIFYING CLASSIFICATION",
            rows=rows_for_image,
            season=season,
            favorite_driver_codes=fav_driver_codes,
        )
        photo = BufferedInputFile(img_buf.getvalue(), filename="quali_results.png")

        try:
            await callback.message.delete()
        except Exception:
            pass

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"back_to_race_{season}")]
        ])

        await callback.message.answer_photo(
            photo=photo,
            caption=f"⏱ Результаты квалификации. Сезон {season}, этап {latest_round}.",
            reply_markup=kb
        )
    await safe_answer_callback(callback)


def _get_last_completed_race_round(schedule: list, now: datetime) -> int | None:
    """Последний этап, гонка которого уже завершилась (race_start + 1ч для обычных, +9ч для тестов)."""
    finished_event = None
    for r in schedule:
        if not r.get("race_start_utc"):
            continue
        try:
            race_dt = datetime.fromisoformat(r["race_start_utc"])
            if race_dt.tzinfo is None:
                race_dt = race_dt.replace(tzinfo=timezone.utc)
            finish_offset = 9 if r.get("is_testing") else 1
            if now > race_dt + timedelta(hours=finish_offset):
                finished_event = r
            else:
                break
        except Exception:
            continue
    return finished_event["round"] if finished_event else None


@router.callback_query(F.data.startswith("race_"))
async def race_callback(callback: CallbackQuery) -> None:
    try:
        parts = callback.data.split("_")
        season = int(parts[1])
    except Exception:
        season = datetime.now().year

    async with Loader(callback.message, "⏳ Загружаю результаты гонки..."):
        schedule = await get_season_schedule_short_async(season)
        if not schedule:
            await _notify_callback_user(callback, "Нет расписания", show_alert=True)
            return

        now = datetime.now(timezone.utc)
        last_round = _get_last_completed_race_round(schedule, now)
        if last_round is None:
            await _notify_callback_user(callback, "Гонка еще не прошла", show_alert=True)
            return

        if _should_reset_previous_results(schedule, now, last_round):
            await _notify_callback_user(callback, "Данных по гонке еще нет", show_alert=True)
            return

        race_results = await get_race_results_async(season, last_round)
        if race_results is None or race_results.empty:
            await _notify_callback_user(callback, "Этап еще не прошел", show_alert=True)
            return

        schedule = await get_season_schedule_short_async(season)
        race_info = next((r for r in schedule if r["round"] == last_round), None)

        constructor_standings = await get_constructor_standings_async(season, round_number=last_round)

        if callback.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            fav_drivers = []
            fav_teams = []
        else:
            fav_drivers = await get_favorite_drivers(callback.from_user.id)
            fav_teams = await get_favorite_teams(callback.from_user.id)

        fav_driver_codes = {str(c).upper() for c in fav_drivers}

        # --- ОФОРМЛЕНИЕ ---
        df = race_results
        if "Position" in df.columns:
            df = df.sort_values("Position")

        data_incomplete = False
        for row in df.itertuples(index=False):
            code = getattr(row, "Abbreviation", "") or getattr(row, "DriverNumber", "?")
            given = getattr(row, "FirstName", "") or ""
            family = getattr(row, "LastName", "") or ""
            full = f"{given} {family}".strip() or code
            if code == "?" or "?" in str(full):
                data_incomplete = True
                break
        if data_incomplete:
            await _notify_callback_user(callback, "Результаты обрабатываются. Данные скоро появятся ⏳", show_alert=True)
            return

        driver_standings = await get_driver_standings_async(season, last_round)
        code_to_team: dict[str, str] = {}
        if not driver_standings.empty and "driverCode" in driver_standings.columns:
            for row in driver_standings.itertuples(index=False):
                c = str(getattr(row, "driverCode", "") or "").strip().upper()
                team = str(getattr(row, "constructorName", "") or "").strip()
                if c:
                    code_to_team[c] = team

        min_time_sec: float | None = None
        time_secs: list[float] = []
        has_time = "Time" in df.columns
        if has_time:
            for row in df.itertuples(index=False):
                t = getattr(row, "Time", None)
                if t is not None and pd.notna(t):
                    try:
                        sec = pd.to_timedelta(t).total_seconds()
                        if sec > 0:
                            time_secs.append(sec)
                    except Exception:
                        pass
            min_time_sec = min(time_secs) if time_secs else None

        rows_for_image: list[dict] = []
        for row in df.itertuples(index=False):
            pos = getattr(row, "Position", None)
            if pos is None:
                continue
            try:
                pos_int = int(pos)
            except Exception:
                continue

            code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
            given = getattr(row, "FirstName", "") or ""
            family = getattr(row, "LastName", "") or ""
            full_name = f"{given} {family}".strip() or code
            team = getattr(row, "TeamName", None) or code_to_team.get(str(code or "").upper(), "")

            gap_str = "-"
            if has_time and min_time_sec is not None:
                t = getattr(row, "Time", None)
                if t is not None and pd.notna(t):
                    try:
                        sec = pd.to_timedelta(t).total_seconds()
                        if sec > 0:
                            if sec <= min_time_sec:
                                h = int(sec // 3600)
                                m = int((sec % 3600) // 60)
                                s = sec % 60
                                if h > 0:
                                    gap_str = f"{h}:{m:02d}:{s:05.2f}"
                                else:
                                    gap_str = f"{m}:{s:05.2f}"
                            else:
                                gap_str = f"+{sec - min_time_sec:.3f}"
                    except Exception:
                        pass

            pts_val = getattr(row, "Points", None)
            pts = int(float(pts_val)) if pts_val is not None and pd.notna(pts_val) else 0
            if pts == 0:
                pts = points_for_race_position(pos_int)

            rows_for_image.append({
                "pos": pos_int,
                "driver": full_name,
                "team": team or "",
                "gap_or_time": gap_str,
                "points": pts,
                "driver_code": str(code or "").strip().upper(),
            })

        if not rows_for_image:
            if callback.message:
                await callback.message.answer("Пока нет данных по результатам гонки 🤔")
            await safe_answer_callback(callback)
            return

        await safe_answer_callback(callback)

        event_name = (race_info or {}).get("event_name", "") or f"Этап {last_round:02d}"

        img_buf = await asyncio.to_thread(
            create_f1_style_classification_image,
            event_name=event_name,
            session_type="RACE CLASSIFICATION",
            rows=rows_for_image,
            season=season,
            favorite_driver_codes=fav_driver_codes,
        )

        photo = BufferedInputFile(
            img_buf.getvalue(),
            filename="race_results.png",
        )

    fav_block = ""
    fav_driver_lines: list[str] = []
    for r in rows_for_image:
        code = str(r.get("driver_code", "") or "").strip().upper()
        if code and code in fav_driver_codes:
            pos = r.get("pos", "?")
            pts = r.get("points", 0)
            fav_driver_lines.append(f"• {code}: P{pos} (+{pts} очк.)")
    if fav_driver_lines:
        fav_block = "⭐️ Твои избранные пилоты:\n<tg-spoiler>" + "\n".join(fav_driver_lines) + "</tg-spoiler>"

    if fav_teams:
        constructor_results_by_name: dict[str, list] = defaultdict(list)
        for row in race_results.itertuples(index=False):
            team_name = getattr(row, "TeamName", None)
            if team_name:
                constructor_results_by_name[team_name].append(row)

        constructor_standings_by_name = {}
        if constructor_standings is not None and not constructor_standings.empty:
            for row in constructor_standings.itertuples(index=False):
                team_name = getattr(row, "constructorName", None)
                if team_name:
                    constructor_standings_by_name[team_name] = row

        fav_lines: list[str] = []

        fav_lines.append("🏎 Твои избранные команды:\n")
        for team_name in fav_teams:
            team_rows = constructor_results_by_name.get(team_name)

            if team_rows is None:
                tn_lower = team_name.lower()
                for key, rows in constructor_results_by_name.items():
                    key_lower = key.lower()
                    if tn_lower in key_lower or key_lower in tn_lower:
                        team_rows = rows
                        break

            standings_row = constructor_standings_by_name.get(team_name)

            if (not team_rows) and standings_row is None:
                continue

            primary = None
            secondary = None
            if team_rows:
                valid_rows = []
                for r in team_rows:
                    pos = getattr(r, "Position", None)
                    try:
                        pos_val = int(float(pos))
                    except (TypeError, ValueError):
                        continue
                    valid_rows.append((pos_val, r))

                valid_rows.sort(key=lambda x: x[0])

                if valid_rows:
                    primary = valid_rows[0][1]
                if len(valid_rows) > 1:
                    secondary = valid_rows[1][1]

            team_race_pts = None
            if team_rows:
                total = 0.0
                has_pts = False
                for r in team_rows:
                    pts = getattr(r, "Points", None)
                    try:
                        total += float(pts)
                        has_pts = True
                    except (TypeError, ValueError):
                        continue
                if has_pts:
                    team_race_pts = int(total)

            total_pts = None
            if standings_row is not None:
                try:
                    total_pts = int(float(getattr(standings_row, "points", 0)))
                except (TypeError, ValueError):
                    total_pts = None

            part = f"\n• {team_name}\n"
            detail_lines = []

            def _format_driver_info(row):
                if row is None:
                    return None
                code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
                given = getattr(row, "FirstName", "") or ""
                family = getattr(row, "LastName", "") or ""
                full_name = f"{given} {family}".strip() or code
                pos = getattr(row, "Position", None)
                try:
                    pos_int = int(float(pos))
                except (TypeError, ValueError):
                    pos_int = None
                if pos_int is None:
                    return None
                return pos_int, code, full_name

            info1 = _format_driver_info(primary)
            info2 = _format_driver_info(secondary)

            if info1:
                pos1, code1, full1 = info1
                detail_lines.append(f"<i>Лучшая машина:</i> P{pos1} — {code1} ({full1})")
            if info2:
                pos2, code2, full2 = info2
                detail_lines.append(f"<i>Вторая машина:</i> P{pos2} — {code2} ({full2})")

            if team_race_pts is not None:
                detail_lines.append(f"<i>Команда набрала</i> {team_race_pts} очк.")
            if total_pts is not None:
                detail_lines.append(f"<i>Всего в чемпионате:</i> {total_pts}")

            if detail_lines:
                details_text = ";\n".join(detail_lines)
                part += f"<span class=\"tg-spoiler\">{details_text}</span>"

            fav_lines.append(part + "\n")

        if fav_lines:
            teams_block = "──────────\n\n" + "".join(fav_lines)
            fav_block = (fav_block + "\n\n" + teams_block) if fav_block else teams_block

    caption = "🏁 Результаты последней гонки (таблица на картинке)."
    if fav_block:
        caption += "\n\n" + fav_block

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"back_to_race_{season}")]
        ])
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
            reply_markup=kb
        )


# --- Календарь ---
async def _send_races_for_year(message: Message, season: int) -> None:
    async with Loader(message, f"📅 Загружаю календарь гонок за {season} год..."):
        races = await get_season_schedule_short_async(season)

        if not races:
            await message.answer(f"Нет данных по календарю сезона {season}.")
            return

        try:
            img_buf = await asyncio.to_thread(create_season_image, season, races)
        except Exception:
            await message.answer("Не удалось сгенерировать календарь.")
            return

        photo = BufferedInputFile(img_buf.getvalue(), filename=f"season_{season}.png")
        caption = f"📅 Календарь сезона {season}\n\n🟥 — гонка уже прошла\n🟩 — предстоящие гонки"

        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    season = _parse_season_from_text(message.text or "")
    await _send_races_for_year(message, season)


@router.message(F.text == "📅 Календарь")
async def btn_races_ask_year(message: Message, state: FSMContext) -> None:
    current_year = datetime.now().year
    kb = (InlineKeyboardMarkup
        (inline_keyboard=
    [
        [InlineKeyboardButton(text=f"Текущий сезон ({current_year})", callback_data=f"races_current_{current_year}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_calendar")]
    ]))
    await message.answer("🗓 Какой год тебя интересует?", reply_markup=kb)
    await state.set_state(RacesYearState.year)


@router.callback_query(F.data == "close_calendar")
async def btn_close_calendar(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.message(RacesYearState.year)
async def races_year_from_text(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите год числом.")
        return

    year = int(message.text)

    error_msg = validate_f1_year(year)
    if error_msg:
        await message.answer(error_msg)
        return

    await state.update_data(year=year)
    await _send_races_for_year(message, year)
    await state.clear()


@router.callback_query(F.data.startswith("races_current_"))
async def races_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        season = int(callback.data.split("_")[-1])
    except:
        season = datetime.now().year
    if callback.message: await _send_races_for_year(callback.message, season)
    await safe_answer_callback(callback)


def _parse_season_from_text(text: str) -> int:
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit(): return int(parts[1])
    return datetime.now().year