import asyncio

from datetime import datetime, date, timezone, timedelta

from collections import defaultdict
from datetime import datetime, date, timezone, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
)

from app.db import (
    get_last_reminded_round, get_favorite_drivers, get_favorite_teams, get_user_settings
)
from app.f1_data import (
    get_season_schedule_short_async, get_weekend_schedule, get_race_results_async,
    get_constructor_standings_async, _get_latest_quali_async
)
from app.utils.default import SESSION_NAME_RU, validate_f1_year
from app.utils.image_render import (
    create_results_image, create_season_image, create_quali_results_image
)
from app.utils.time_tools import format_race_time

router = Router()
UTC_PLUS_3 = timezone(timedelta(hours=3))


class RacesYearState(StatesGroup):
    year = State()


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

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание уикенда",
                              callback_data=f"weekend_{payload['season']}_{payload['round']}")],
        [InlineKeyboardButton(text="⏱ Квалификация", callback_data=f"quali_{payload['season']}_{payload['round']}"),
         InlineKeyboardButton(text="🏁 Гонка", callback_data=f"race_{payload['season']}_{payload['round']}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu"),
         InlineKeyboardButton(text="⚙️ Настройки (Время)", callback_data=f"settings_race_{payload['season']}")]
    ])

    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("next_race"))
async def cmd_next_race(message: Message):
    await _send_next_race_message(message, message.from_user.id)


@router.message(F.text == "🏁 Следующая гонка")
async def next_race_btn(message: Message):
    await _send_next_race_message(message, message.from_user.id)


@router.callback_query(F.data.startswith("back_to_race_"))
async def back_to_race(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        season = int(callback.data.split("_")[-1])
    except:
        season = None

    if callback.message.photo:
        await callback.message.delete()
        await _send_next_race_message(callback.message, callback.from_user.id, season, False)
    else:
        await _send_next_race_message(callback.message, callback.from_user.id, season, True)


@router.callback_query(F.data.startswith("weekend_"))
async def weekend_schedule(callback: CallbackQuery):
    try:
        parts = callback.data.split("_")
        season, round_num = int(parts[1]), int(parts[2])
    except:
        await callback.answer("Ошибка данных")
        return

    sessions = get_weekend_schedule(season, round_num)
    settings = await get_user_settings(callback.from_user.id)
    user_tz = settings.get("timezone", "Europe/Moscow")

    lines = []
    for s in sessions:
        ru_name = SESSION_NAME_RU.get(s["name"], s["name"])
        # Для расписания в боте используем format_race_time (UTC+X)
        time_str = format_race_time(s.get("utc_iso"), user_tz)
        lines.append(f"• {ru_name}\n  {time_str}")

    text = f"📅 Расписание уикенда (Сезон {season}, Этап {round_num}):\n\n" + "\n\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"settings_race_{season}")],
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"back_to_race_{season}")]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("quali_"))
async def quali_callback(callback: CallbackQuery) -> None:
    try:
        _, season_str, _ = callback.data.split("_")
        season = int(season_str)
    except:
        season = datetime.now().year

    latest = await _get_latest_quali_async(season)
    latest_round, results = latest

    if not latest_round or not results:
        await callback.answer("Нет результатов", show_alert=True)
        return

    rows: list[tuple[str, str, str, str]] = []
    for r in results:
        pos = f"{r['position']:02d}"
        code = r["driver"]
        name = r.get("name") or r["driver"]
        best = r.get("best") or "—"
        rows.append((pos, code, name, best))

    img_buf = await asyncio.to_thread(
        create_quali_results_image,
        f"Квалификация {season}",
        f"Этап {latest_round:02d}",
        rows
    )
    photo = BufferedInputFile(img_buf.getvalue(), filename="quali_results.png")

    await callback.message.delete()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"back_to_race_{season}")]
    ])

    await callback.message.answer_photo(
        photo=photo,
        caption=f"⏱ Результаты квалификации. Сезон {season}, этап {latest_round}.",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("race_"))
async def race_callback(callback: CallbackQuery) -> None:
    try:
        parts = callback.data.split("_")
        season = int(parts[1])
    except:
        season = datetime.now().year

    last_round = await get_last_reminded_round(season)
    if last_round is None:
        await callback.answer("Гонка еще не прошла", show_alert=True)
        return

    race_results = await get_race_results_async(season, last_round)
    if race_results is None or race_results.empty:
        await callback.answer("Нет результатов", show_alert=True)
        return

    schedule = await get_season_schedule_short_async(season)
    race_info = next((r for r in schedule if r["round"] == last_round), None)

    constructor_standings = await get_constructor_standings_async(season, round_number=last_round)

    fav_drivers = await get_favorite_drivers(callback.from_user.id)
    fav_teams = await get_favorite_teams(callback.from_user.id)

    # --- ОФОРМЛЕНИЕ ---
    df = race_results
    if "Position" in df.columns:
        df = df.sort_values("Position")

    lines: list[str] = []
    max_positions = 20
    count = 0

    fav_drivers_set = set(fav_drivers or [])
    rows_for_image: list[tuple[str, str, str, str]] = []

    for row in df.itertuples(index=False):
        pos = getattr(row, "Position", None)
        if pos is None: continue
        try:
            pos_int = int(pos)
        except:
            continue

        count += 1
        if count > max_positions: break

        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
        given = getattr(row, "FirstName", "") or ""
        family = getattr(row, "LastName", "") or ""
        full_name = f"{given} {family}".strip() or code
        pts = getattr(row, "Points", None)

        is_fav = code in fav_drivers_set

        code_for_img = f"⭐️{code}" if is_fav else code
        if pts is not None:
            try:
                pts_val = float(pts)
                pts_text = f"{pts_val:.0f}"
            except:
                pts_text = str(pts)
        else:
            pts_text = "0"

        rows_for_image.append((f"{pos_int:02d}", code_for_img, full_name, pts_text))

    if not rows_for_image:
        if callback.message:
            await callback.message.answer("Пока нет данных по результатам гонки 🤔")
        await callback.answer()
        return

    if race_info is not None:
        img_title = "Результаты гонки"
        img_subtitle = (
            f"{race_info['event_name']} — {race_info['country']}, "
            f"{race_info['location']} (этап {last_round}, сезон {season})"
        )
    else:
        img_title = "Результаты гонки"
        img_subtitle = f"Этап {last_round}, сезон {season}"

    img_buf = await asyncio.to_thread(
        create_results_image,
        title=img_title,
        subtitle=img_subtitle,
        rows=rows_for_image,
    )

    photo = BufferedInputFile(
        img_buf.getvalue(),
        filename="race_results.png",
    )

    fav_block = ""
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
            fav_block = "──────────\n\n" + "".join(fav_lines)

    caption = (
        "🏁 Результаты последней гонки (таблица на картинке).\n"
        "⭐️ — твои избранные пилоты."
    )
    if fav_block:
        caption += "\n\n" + fav_block

    if callback.message:
        await callback.message.delete()
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

    await callback.answer()


# --- Календарь ---
async def _send_races_for_year(message: Message, season: int) -> None:
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
async def btn_close_calendar(callback: CallbackQuery, state: FSMContext): # <-- Добавили state
    await state.clear()                                                   # <-- СБРАСЫВАЕМ СОСТОЯНИЕ
    await callback.message.delete()


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
    await callback.answer()


def _parse_season_from_text(text: str) -> int:
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit(): return int(parts[1])
    return datetime.now().year