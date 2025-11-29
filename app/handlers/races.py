import asyncio
import logging
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
import random
import fastf1

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile

from app.utils.default import SESSION_NAME_RU
from app.utils.image_render import create_results_image, create_season_image, create_quali_results_image
from app.db import (
    get_last_reminded_round,
    get_favorite_drivers,
    get_favorite_teams,
)
from app.utils.f1_data import get_season_schedule_short, get_weekend_schedule, get_race_results_df, \
    get_constructor_standings_df, \
    get_driver_standings_df, _get_latest_quali_async, get_qualifying_results

router = Router()

UTC_PLUS_3 = timezone(timedelta(hours=3))

class RacesYearState(StatesGroup):
    waiting_for_year = State()


async def _send_races_for_year(message: Message, season: int) -> None:
    """Отправить календарь сезона в виде картинки.

    Использует create_season_image из image_render, который сам
    рисует все этапы, отмечает прошедшие/будущие и подсвечивает
    ближайший этап.
    """
    races = get_season_schedule_short(season)

    if not races:
        await message.answer(f"Нет данных по календарю сезона {season}.")
        return

    # Генерируем изображение календаря
    img_buf = create_season_image(season, races)

    photo = BufferedInputFile(
        img_buf.getvalue(),
        filename=f"season_{season}.png",
    )

    caption = (
        f"📅 Календарь сезона {season}\n"
        f"\n🟥 — гонка уже прошла\n"
        f"\n🟩 — предстоящие гонки, дата показана\n"
    )

    await message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
    )


async def _send_next_race(message: Message, season: int | None = None) -> None:
    if season is None:
        season = datetime.now().year

    schedule = get_season_schedule_short(season)
    if not schedule:
        await message.answer(f"Нет расписания для сезона {season}.")
        return

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
        await message.answer(f"Сезон {season} уже полностью завершён ✅")
        return

    race_date, r = min(future_races, key=lambda x: x[0])

    round_num = r["round"]
    event_name = r["event_name"]
    country = r["country"]
    location = r["location"]

    date_str = race_date.strftime("%d.%m.%Y")

    race_start_utc_str = r.get("race_start_utc")
    if race_start_utc_str:
        try:
            race_start_utc = datetime.fromisoformat(race_start_utc_str)
            if race_start_utc.tzinfo is None:
                race_start_utc = race_start_utc.replace(tzinfo=timezone.utc)

            utc_str = race_start_utc.strftime("%d.%m.%Y %H:%M UTC")
            local_dt = race_start_utc.astimezone(UTC_PLUS_3)
            local_str = local_dt.strftime("%d.%m.%Y %H:%M МСК")

            time_block = (
                "\n⏰ Старт гонки:\n"
                f"• {utc_str}\n"
                f"• {local_str}"
            )
        except Exception:
            time_block = f"📅 Дата: {date_str}"
    else:
        time_block = f"📅 Дата: {date_str}"

    reply = (
        f"🗓 Ближайший этап сезона {season}:\n\n"
        f"{round_num:02d}. {event_name}\n"
        f"📍 {country}, {location}\n"
        f"{time_block}\n\n"
        f"Я пришлю тебе уведомление по твоим избранным пилотам и командам "
        f"после гонки, как только данные обновятся. 😉"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Расписание уикенда",
                    callback_data=f"weekend_{season}_{round_num}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏱ Квалификация",
                    callback_data=f"quali_{season}_{round_num}",
                ),
                InlineKeyboardButton(
                    text="🏁 Гонка",
                    callback_data=f"race_{season}_{round_num}",
                ),
            ],
        ]
    )

    await message.answer(reply, reply_markup=keyboard)


def _parse_season_from_text(text: str) -> int:
    text = (text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return datetime.now().year


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    season = _parse_season_from_text(message.text or "")
    await _send_races_for_year(message, season)


@router.message(F.text == "Сезон")
async def btn_races_ask_year(message: Message, state: FSMContext) -> None:
    """
    Нажали кнопку «Сезон» — спрашиваем год и даём кнопку «Текущий сезон».
    """
    current_year = datetime.now().year

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Текущий сезон ({current_year})",
                    callback_data=f"races_current_{current_year}",
                )
            ]
        ]
    )

    await message.answer(
        "🗓 Какой год тебя интересует?\n"
        "Напиши год цифрами (например, 2021),\n"
        "или нажми кнопку ниже, если нужен текущий сезон.",
        reply_markup=kb,
    )
    await state.set_state(RacesYearState.waiting_for_year)


@router.message(RacesYearState.waiting_for_year)
async def races_year_from_text(message: Message, state: FSMContext) -> None:
    """
    Пользователь ответил годом текстом.
    """
    text = (message.text or "").strip()
    try:
        season = int(text)
    except ValueError:
        await message.answer("Пожалуйста, введи год цифрами, например: 2021")
        return

    await state.clear()
    await _send_races_for_year(message, season)


@router.callback_query(F.data.startswith("races_current_"))
async def races_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Пользователь нажал кнопку «Текущий сезон (YYYY)».
    """
    await state.clear()
    year_str = callback.data.split("_")[-1]
    try:
        season = int(year_str)
    except ValueError:
        season = datetime.now().year

    if callback.message:
        await _send_races_for_year(callback.message, season)

    await callback.answer()


@router.message(Command("next_race"))
async def cmd_next_race(message: Message) -> None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) == 2:
        try:
            season = int(parts[1])
        except ValueError:
            await message.answer("Не понял год 😅 Напиши: /next_race 2024")
            return
    else:
        season = None  # возьмём текущий

    await _send_next_race(message, season)


@router.message(F.text == "Ближайшая гонка")
async def next_race_button(message: Message) -> None:
    await _send_next_race(message, season=None)


@router.callback_query(F.data.startswith("weekend_"))
async def weekend_schedule_callback(callback: CallbackQuery) -> None:
    try:
        _, season_str, round_str = callback.data.split("_")
        season = int(season_str)
        round_num = int(round_str)
    except Exception:
        await callback.answer("Не понял данные этапа 😅", show_alert=True)
        return

    sessions = get_weekend_schedule(season, round_num)
    if not sessions:
        await callback.message.answer("Нет данных по расписанию уикенда 🤔")
        await callback.answer()
        return

    lines = []
    for s in sessions:
        raw_name = s["name"]
        # пробуем найти перевод, иначе оставляем как есть
        name_ru = SESSION_NAME_RU.get(raw_name, raw_name)

        lines.append(
            f"• <b>{name_ru}</b>\n"
            f"  {s['local']} / {s['utc']}"
        )

    text = (
        f"📅 Расписание уикенда сезона {season}, раунд {round_num}:\n\n"
        + "\n\n".join(lines)
    )

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("quali_"))
async def quali_callback(callback: CallbackQuery) -> None:
    # 1. Берём сезон из callback, а раунд — НЕ используем напрямую
    try:
        _, season_str, _round_str = callback.data.split("_")
        season = int(season_str)
    except Exception:
        season = datetime.now().year

    # 2. Находим последнюю квалификацию сезона, по которой есть данные
    latest = await _get_latest_quali_async(season)
    if latest is None:
        await callback.message.answer(
            "Пока нет квалификаций с сохранёнными результатами для этого сезона 🤔"
        )
        await callback.answer()
        return

    latest_round, results = latest  # results — это список dict’ов

    if not results:
        await callback.message.answer(
            "Пока нет данных по результатам квалификации 🤔"
        )
        await callback.answer()
        return

    # 3. Собираем строки для картинки
    rows: list[tuple[str, str, str, str]] = []
    for r in results:
        pos = f"{r['position']:02d}"
        code = r["driver"]                  # тут можешь добавлять ⭐️, если нужно
        name = r.get("name") or r["driver"]  # если нет полного имени — используем код
        best = r.get("best") or "—"
        rows.append((pos, code, name, best))

    title = f"Квалификация {season}"
    subtitle = f"Этап {latest_round:02d}"

    buf = create_quali_results_image(title, subtitle, rows)

    photo = BufferedInputFile(buf.getvalue(), filename="quali_results.png")

    caption = (
        f"⏱ Результаты последней квалификации (таблица на картинке).\n"
        f"Сезон {season}, этап {latest_round:02d}."
    )

    await callback.message.answer_photo(
        photo=photo,
        caption=caption,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("race_"))
async def race_callback(callback: CallbackQuery) -> None:
    """
    По кнопке «🏁 Гонка» показываем результаты
    ПОСЛЕДНЕЙ гонки сезона, для которой уже есть результаты
    (по данным notification_state.last_reminded_round),
    а в конце — блок по избранным КОМАНДАМ.
    Для избранных пилотов ставим ⭐️ в общем списке результатов.
    """
    # 1. Определяем сезон (берём из callback, если есть, иначе текущий год)
    try:
        parts = callback.data.split("_")  # "race_2025_22"
        season = int(parts[1])
    except Exception:
        season = datetime.now().year

    # 2. Узнаём, по какому раунду у нас уже есть результаты и нотификация
    last_round = await get_last_reminded_round(season)
    if last_round is None:
        await callback.message.answer(
            "Пока нет гонок с сохранёнными результатами для этого сезона 🤔"
        )
        await callback.answer()
        return

    # 3. Берём информацию о гонке из календаря (для красивого заголовка)
    schedule = get_season_schedule_short(season)
    race_info = None
    if schedule:
        race_info = next(
            (r for r in schedule if r["round"] == last_round),
            None,
        )

    # 4. Тянем результаты гонки и таблицы чемпионатов
    race_results = get_race_results_df(season, last_round)
    if race_results is None or race_results.empty:
        await callback.message.answer(
            "Пока нет данных по результатам гонки 🤔"
        )
        await callback.answer()
        return

    driver_standings = get_driver_standings_df(season, round_number=last_round)
    constructor_standings = get_constructor_standings_df(season, round_number=last_round)

    # 4.1. Получаем избранных пользователя
    fav_drivers = await get_favorite_drivers(callback.from_user.id)
    fav_teams = await get_favorite_teams(callback.from_user.id)

    # --- ОФОРМЛЕНИЕ ОСНОВНОГО БЛОКА РЕЗУЛЬТАТОВ ---

    df = race_results
    if "Position" in df.columns:
        df = df.sort_values("Position")

    # Заголовок
    if race_info is not None:
        header = (
            "🏁 <b>Результаты последней гонки</b>\n"
            f"{race_info['event_name']} — {race_info['country']}, {race_info['location']}\n"
            f"(этап {last_round}, сезон {season})\n"
            "<b>Твои избранные пилоты</b> — отмечены ⭐️\n\n"
        )
    else:
        header = (
            "🏁 <b>Результаты последней гонки</b>\n"
            f"(этап {last_round}, сезон {season})\n\n"
            "⭐️ <b>Твои избранные</b>\n\n"
        )

    # Топ-20 финишировавших
    lines: list[str] = []
    max_positions = 20
    count = 0

    fav_drivers_set = set(fav_drivers or [])
    # Для генерации картинки: (позиция, код, имя пилота, очки за гонку)
    rows_for_image: list[tuple[str, str, str, str]] = []

    for row in df.itertuples(index=False):
        pos = getattr(row, "Position", None)
        if pos is None:
            continue
        try:
            pos_int = int(pos)
        except (TypeError, ValueError):
            continue

        count += 1
        if count > max_positions:
            break

        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
        team = getattr(row, "TeamName", "")
        pts = getattr(row, "Points", None)

        # Имя пилота
        given = getattr(row, "FirstName", "") or ""
        family = getattr(row, "LastName", "") or ""
        full_name = f"{given} {family}".strip() or code

        is_fav = code in fav_drivers_set
        prefix_star = "⭐️ " if is_fav else ""

        line = f"{pos_int:02d}. {prefix_star}<b>{code}</b>"
        if team:
            line += f" — {team}"
        if pts is not None:
            line += f" ({pts} очк.)"
        lines.append(line)

        # Подготовка данных для картинки
        code_for_img = f"⭐️{code}" if is_fav else code
        if pts is not None:
            # если очки — число, красиво форматируем, но без суффикса "очк."
            try:
                pts_value = float(pts)
                pts_text = f"{pts_value:.0f}"
            except (TypeError, ValueError):
                pts_text = str(pts)
        else:
            pts_text = "0"

        rows_for_image.append(
            (f"{pos_int:02d}", code_for_img, full_name, pts_text)
        )

    if not lines:
        await callback.message.answer(
            "Пока нет данных по результатам гонки 🤔"
        )
        await callback.answer()
        return

    # Сначала генерируем картинку с результатами
    if race_info is not None:
        img_title = "Результаты гонки"
        img_subtitle = (
            f"{race_info['event_name']} — {race_info['country']}, "
            f"{race_info['location']} (этап {last_round}, сезон {season})"
        )
    else:
        img_title = "Результаты гонки"
        img_subtitle = f"Этап {last_round}, сезон {season}"

    img_buf = create_results_image(
        title=img_title,
        subtitle=img_subtitle,
        rows=rows_for_image,
    )

    photo = BufferedInputFile(
        img_buf.getvalue(),
        filename="race_results.png",
    )

    # --- БЛОК ПО ИЗБРАННЫМ КОМАНДАМ (пилотов тут больше не показываем!) ---

    fav_block = ""

    if fav_teams:
        # Мапы для быстрого поиска по командам
        # В race_results по каждой строке — конкретный пилот.
        # Здесь собираем все машины команды.
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
            # 1) пробуем точное имя
            team_rows = constructor_results_by_name.get(team_name)

            # 2) если не нашли — пробуем "похожее" (Red Bull vs Red Bull Racing)
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

            # --- выбираем две лучшие машины команды ---
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

            # --- суммарные очки команды в гонке ---
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

            # --- очки в чемпионате ---
            total_pts = None
            if standings_row is not None:
                try:
                    total_pts = int(float(getattr(standings_row, "points", 0)))
                except (TypeError, ValueError):
                    total_pts = None

            part = f"\n• <b>{team_name}</b>\n"
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
                detail_lines.append(f"<i>Лучшая машина:</i> <b>P{pos1} — {code1} ({full1})</b>")
            if info2:
                pos2, code2, full2 = info2
                detail_lines.append(f"<i>Вторая машина:</i> <b>P{pos2} — {code2} ({full2})</b>")

            if team_race_pts is not None:
                detail_lines.append(f"<i>Команда набрала</i> <b>{team_race_pts} очк.</b>")
            if total_pts is not None:
                detail_lines.append(f"<i>Всего в чемпионате:</i> <b>{total_pts}</b>")

            if detail_lines:
                details_text = ";\n".join(detail_lines)
                part += f"<span class=\"tg-spoiler\">{details_text}</span>"

            fav_lines.append(part + "\n")

        if fav_lines:
            fav_block = "──────────\n\n" + "".join(fav_lines)

    # Собираем итоговый текст для подписи к картинке
    caption = (
        "🏁 Результаты последней гонки (таблица на картинке).\n"
        "⭐️ — твои избранные пилоты."
    )
    if fav_block:
        caption += "\n\n" + fav_block

    await callback.message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
        has_spoiler=True,
    )

    await callback.answer()


