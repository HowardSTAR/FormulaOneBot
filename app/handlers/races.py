import asyncio
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)

from app.utils.default import SESSION_NAME_RU
from app.utils.image_render import (
    create_results_image,
    create_season_image,
    create_quali_results_image,
)
from app.db import (
    get_last_reminded_round,
    get_favorite_drivers,
    get_favorite_teams,
    get_user_settings,
)
from app.utils.time_tools import format_race_time
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,
    get_race_results_async,
    get_constructor_standings_async,
    _get_latest_quali_async,
)

router = Router()


class RacesYearState(StatesGroup):
    waiting_for_year = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def build_next_race_payload(season: int | None = None, user_id: int | None = None) -> dict:
    if season is None:
        season = datetime.now().year

    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        return {"status": "no_schedule", "season": season}

    today = date.today()
    future_races = []
    for r in schedule:
        try:
            race_date = date.fromisoformat(r["date"])
        except Exception:
            continue
        if race_date >= today:
            future_races.append((race_date, r))

    if not future_races:
        return {"status": "season_finished", "season": season}

    race_date, r = min(future_races, key=lambda x: x[0])
    round_num = r["round"]
    event_name = r["event_name"]
    country = r["country"]
    location = r["location"]
    date_str = race_date.strftime("%d.%m.%Y")

    race_start_utc_str = r.get("race_start_utc")
    utc_str: str | None = None
    local_str: str | None = None

    if race_start_utc_str:
        user_tz = "Europe/Moscow"
        if user_id:
            settings = await get_user_settings(user_id)
            user_tz = settings.get("timezone", "Europe/Moscow")
        local_str = format_race_time(race_start_utc_str, user_tz)
        utc_str = race_start_utc_str

    return {
        "status": "ok",
        "season": season,
        "round": round_num,
        "event_name": event_name,
        "country": country,
        "location": location,
        "date": date_str,
        "utc": utc_str,
        "local": local_str,
    }


# 👇 ИСПРАВЛЕНИЕ: Добавлен аргумент user_id
async def _send_next_race_message(message: Message, user_id: int, season: int | None = None, is_edit: bool = False):
    """
    Отправляет или обновляет карточку гонки.
    Требует явной передачи user_id, чтобы настройки времени брались корректно.
    """
    payload = await build_next_race_payload(season, user_id=user_id)

    status = payload["status"]
    current_season = payload["season"]

    if status != "ok":
        text = f"Нет данных или сезон {current_season} завершен."
        if is_edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    round_num = payload["round"]
    local_str = payload["local"]
    date_str = payload["date"]

    if local_str:
        time_block = f"\n⏰ Старт гонки: <b>{local_str}</b>"
    else:
        time_block = f"📅 Дата: {date_str}"

    reply = (
        f"🗓 Ближайший этап сезона {current_season}:\n\n"
        f"{round_num:02d}. {payload['event_name']}\n"
        f"📍 {payload['country']}, {payload['location']}\n"
        f"{time_block}\n\n"
        f"Я пришлю уведомление по избранным пилотам после гонки."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Расписание уикенда",
                    callback_data=f"weekend_{current_season}_{round_num}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏱ Квалификация",
                    callback_data=f"quali_{current_season}_{round_num}",
                ),
                InlineKeyboardButton(
                    text="🏁 Гонка",
                    callback_data=f"race_{current_season}_{round_num}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки",
                    callback_data=f"settings_race_{current_season}"
                )
            ]
        ]
    )

    if is_edit:
        await message.edit_text(reply, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(reply, reply_markup=keyboard, parse_mode="HTML")


# --- ХЕНДЛЕРЫ ---

@router.message(Command("next_race"))
async def cmd_next_race(message: Message) -> None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    season = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None

    # 👇 ИСПРАВЛЕНИЕ: Передаем message.from_user.id
    await _send_next_race_message(message, message.from_user.id, season, is_edit=False)


@router.message(F.text == "Ближайшая гонка")
async def next_race_button(message: Message) -> None:
    # 👇 ИСПРАВЛЕНИЕ: Передаем message.from_user.id
    await _send_next_race_message(message, message.from_user.id, season=None, is_edit=False)


@router.callback_query(F.data.startswith("back_to_race_"))
async def back_to_race_callback(callback: CallbackQuery, state: FSMContext):
    # Очищаем состояние настроек, чтобы не было конфликтов
    await state.clear()

    try:
        season_str = callback.data.split("_")[-1]
        season = int(season_str) if season_str != "None" else None
    except:
        season = None

    # 👇 ИСПРАВЛЕНИЕ: Передаем callback.from_user.id (Это ТЫ, а не бот)
    user_id = callback.from_user.id

    if callback.message.photo:
        await callback.message.delete()
        await _send_next_race_message(callback.message, user_id, season, is_edit=False)
    else:
        await _send_next_race_message(callback.message, user_id, season, is_edit=True)


@router.callback_query(F.data.startswith("weekend_"))
async def weekend_schedule_callback(callback: CallbackQuery) -> None:
    try:
        _, season_str, round_str = callback.data.split("_")
        season = int(season_str)
        round_num = int(round_str)
    except Exception:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    sessions = get_weekend_schedule(season, round_num)
    if not sessions:
        await callback.answer("Нет данных расписания", show_alert=True)
        return

    user_settings = await get_user_settings(callback.from_user.id)
    user_tz = user_settings.get("timezone", "Europe/Moscow")

    lines = []
    for s in sessions:
        raw_name = s["name"]
        name_ru = SESSION_NAME_RU.get(raw_name, raw_name)

        # Теперь s['utc'] — это ISO строка, и format_race_time сработает корректно
        formatted_time = format_race_time(s.get('utc'), user_tz)

        lines.append(
            f"• <b>{name_ru}</b>\n"
            f"  {formatted_time}"
        )

    text = (
            f"📅 Расписание уикенда сезона {season}, раунд {round_num}:\n\n"
            + "\n\n".join(lines)
    )

    # Добавил кнопку настроек
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настройки (Время)", callback_data=f"settings_race_{season}")],
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

    # --- Подготовка данных для рендера ---
    df = race_results
    if "Position" in df.columns:
        df = df.sort_values("Position")

    fav_drivers_set = set(fav_drivers or [])
    rows_for_image: list[tuple[str, str, str, str]] = []
    count = 0

    for row in df.itertuples(index=False):
        if count >= 20: break
        count += 1
        pos = getattr(row, "Position", "0")
        code = getattr(row, "Abbreviation", "?")
        name = getattr(row, "LastName", code)
        full_name = getattr(row, "FirstName", "") + " " + name
        pts = getattr(row, "Points", "0")
        try:
            pts = f"{float(pts):.0f}"
        except:
            pass

        is_fav = code in fav_drivers_set
        code_img = f"⭐️{code}" if is_fav else code
        rows_for_image.append((str(pos), code_img, full_name, str(pts)))

    if race_info:
        title = "Результаты гонки"
        sub = f"{race_info['event_name']} ({season})"
    else:
        title = "Результаты"
        sub = str(season)

    img_buf = await asyncio.to_thread(
        create_results_image,
        title=title,
        subtitle=sub,
        rows=rows_for_image,
    )
    photo = BufferedInputFile(img_buf.getvalue(), filename="race_results.png")

    # --- БЛОК ПО ИЗБРАННЫМ КОМАНДАМ ---
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
        fav_lines.append("🏎 <b>Твои избранные команды</b>:\n")

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

            primary, secondary = None, None
            if team_rows:
                valid_rows = []
                for r in team_rows:
                    pos = getattr(r, "Position", None)
                    try:
                        valid_rows.append((int(float(pos)), r))
                    except:
                        continue
                valid_rows.sort(key=lambda x: x[0])
                if valid_rows: primary = valid_rows[0][1]
                if len(valid_rows) > 1: secondary = valid_rows[1][1]

            team_race_pts = None
            if team_rows:
                total = 0.0
                has_pts = False
                for r in team_rows:
                    try:
                        total += float(getattr(r, "Points", 0))
                        has_pts = True
                    except:
                        continue
                if has_pts: team_race_pts = int(total)

            total_pts = None
            if standings_row is not None:
                try:
                    total_pts = int(float(getattr(standings_row, "points", 0)))
                except:
                    pass

            part = f"\n• <b>{team_name}</b>\n"
            detail_lines = []

            def _fmt(row):
                if row is None: return None
                code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
                given = getattr(row, "FirstName", "") or ""
                family = getattr(row, "LastName", "") or ""
                full = f"{given} {family}".strip() or code
                try:
                    p = int(float(getattr(row, "Position", 0)))
                except:
                    p = "?"
                return p, code, full

            info1 = _fmt(primary)
            info2 = _fmt(secondary)

            if info1: detail_lines.append(f"<i>Лучшая машина:</i> <b>P{info1[0]} — {info1[1]} ({info1[2]})</b>")
            if info2: detail_lines.append(f"<i>Вторая машина:</i> <b>P{info2[0]} — {info2[1]} ({info2[2]})</b>")
            if team_race_pts is not None: detail_lines.append(f"<i>Очки за гонку:</i> <b>{team_race_pts}</b>")
            if total_pts is not None: detail_lines.append(f"<i>Всего в сезоне:</i> <b>{total_pts}</b>")

            if detail_lines:
                part += f"<span class=\"tg-spoiler\">{'; '.join(detail_lines)}</span>"
            fav_lines.append(part + "\n")

        if fav_lines:
            fav_block = "──────────\n\n" + "".join(fav_lines)

    caption = (
        "🏁 Результаты гонки.\n"
        "⭐️ — твои избранные пилоты."
    )
    if fav_block:
        caption += "\n\n" + fav_block

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
        await message.answer(f"Нет данных {season}")
        return
    img_buf = await asyncio.to_thread(create_season_image, season, races)
    photo = BufferedInputFile(img_buf.getvalue(), filename=f"season_{season}.png")
    await message.answer_photo(photo=photo, caption=f"📅 Календарь {season}")


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    season = datetime.now().year
    await _send_races_for_year(message, season)


@router.message(F.text == "Сезон")
async def btn_races_ask_year(message: Message, state: FSMContext) -> None:
    current_year = datetime.now().year
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Текущий сезон ({current_year})", callback_data=f"races_current_{current_year}")]
    ])
    await message.answer("🗓 Какой год тебя интересует?", reply_markup=kb)
    await state.set_state(RacesYearState.waiting_for_year)


@router.message(RacesYearState.waiting_for_year)
async def races_year_from_text(message: Message, state: FSMContext) -> None:
    try:
        season = int((message.text or "").strip())
        await state.clear()
        await _send_races_for_year(message, season)
    except ValueError:
        await message.answer("Введи год цифрами (например: 2024)")


@router.callback_query(F.data.startswith("races_current_"))
async def races_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        season = int(callback.data.split("_")[-1])
    except:
        season = datetime.now().year
    await _send_races_for_year(callback.message, season)
    await callback.answer()


def _parse_season_from_text(text: str) -> int:
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return datetime.now().year