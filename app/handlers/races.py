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
from app.utils.time_tools import format_race_time

from app.utils.image_render import (
    create_results_image,
    create_season_image,
    create_quali_results_image,
)
from app.db import (
    get_last_reminded_round,
    get_favorite_drivers,
    get_favorite_teams,
)
# ИСПРАВЛЕНО: Импортируем асинхронные версии функций
from app.f1_data import (
    get_season_schedule_short_async,
    get_weekend_schedule,  # Можно оставить синхронной, если она быстрая (просто парсинг), или тоже обернуть
    get_race_results_async,
    get_constructor_standings_async,
    get_driver_standings_async,
    _get_latest_quali_async,
)

router = Router()

UTC_PLUS_3 = timezone(timedelta(hours=3))

class RacesYearState(StatesGroup):
    waiting_for_year = State()


async def build_next_race_payload(season: int | None = None, user_id: int | None = None) -> dict:
    """
    Возвращает инфу о ближайшей гонке как словарь.
    """
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

    # ... (код round_num, event_name, country, location копируем как есть) ...
    round_num = r["round"]
    event_name = r["event_name"]
    country = r["country"]
    location = r["location"]
    date_str = race_date.strftime("%d.%m.%Y")

    race_start_utc_str = r.get("race_start_utc")
    utc_str: str | None = None
    local_str: str | None = None

    # 👇 НОВАЯ ЛОГИКА ВРЕМЕНИ 👇
    if race_start_utc_str:
        # 1. Получаем настройки пользователя, если есть user_id
        user_tz = "Europe/Moscow"  # Дефолт
        if user_id:
            # Этой функции нет в твоем коде, её надо добавить в db.py
            settings = await get_user_settings(user_id)
            if settings:
                user_tz = settings.get("timezone", "Europe/Moscow")

        # 2. Используем нашу функцию format_race_time
        # Она вернет строку типа "02 марта, 18:00"
        local_str = format_race_time(race_start_utc_str, user_tz)

        # UTC оставим для справки, если нужно, или уберем
        utc_str = race_start_utc_str  # Можно просто сырую строку вернуть

    return {
        "status": "ok",
        "season": season,
        "round": round_num,
        "event_name": event_name,
        "country": country,
        "location": location,
        "date": date_str,
        "utc": utc_str,
        "local": local_str,  # Теперь это красивое время под юзера
    }


async def _send_races_for_year(message: Message, season: int) -> None:
    """Отправить календарь сезона в виде картинки."""
    # ИСПРАВЛЕНО: await
    races = await get_season_schedule_short_async(season)

    if not races:
        await message.answer(f"Нет данных по календарю сезона {season}.")
        return

    # ИСПРАВЛЕНО: Генерация картинки в отдельном потоке
    try:
        img_buf = await asyncio.to_thread(create_season_image, season, races)
    except Exception:
        await message.answer("Не удалось сгенерировать календарь.")
        return

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
    user_id = message.from_user.id  # Получаем ID юзера

    # 👇 Передаем user_id в функцию
    payload = await build_next_race_payload(season, user_id=user_id)

    status = payload["status"]
    season = payload["season"]

    if status == "no_schedule":
        await message.answer(f"Нет расписания для сезона {season}.")
        return

    if status == "season_finished":
        await message.answer(f"Сезон {season} уже полностью завершён ✅")
        return

    # status == "ok"
    round_num = payload["round"]
    event_name = payload["event_name"]
    country = payload["country"]
    location = payload["location"]
    date_str = payload["date"]
    utc_str = payload["utc"]
    local_str = payload["local"]

    if utc_str and local_str:
        time_block = (
            "\n⏰ Старт гонки:\n"
            f"• {utc_str}\n"
            f"• {local_str}"
        )
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
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки (Время/Уведомления)",
                    callback_data="cmd_settings"  # Этот callback должен ловить settings.py
                )
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
        season = None

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

    # get_weekend_schedule обычно быстрый (берет из кэшированного расписания),
    # но можно тоже обернуть в to_thread, если он подлагивает. Пока оставим так.
    sessions = get_weekend_schedule(season, round_num)
    if not sessions:
        if callback.message:
            await callback.message.answer("Нет данных по расписанию уикенда 🤔")
        await callback.answer()
        return

    lines = []
    for s in sessions:
        raw_name = s["name"]
        name_ru = SESSION_NAME_RU.get(raw_name, raw_name)

        lines.append(
            f"• <b>{name_ru}</b>\n"
            f"  {s['local']} / {s['utc']}"
        )

    text = (
            f"📅 Расписание уикенда сезона {season}, раунд {round_num}:\n\n"
            + "\n\n".join(lines)
    )

    if callback.message:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("quali_"))
async def quali_callback(callback: CallbackQuery) -> None:
    try:
        _, season_str, _round_str = callback.data.split("_")
        season = int(season_str)
    except Exception:
        season = datetime.now().year

    # Эта функция уже была асинхронной (через run_in_executor внутри), всё ок
    latest = await _get_latest_quali_async(season)
    latest_round, results = latest

    if latest_round is None or not results:
        if callback.message:
            await callback.message.answer(
                "Пока нет квалификаций с сохранёнными результатами для этого сезона 🤔"
            )
        await callback.answer()
        return

    rows: list[tuple[str, str, str, str]] = []
    for r in results:
        pos = f"{r['position']:02d}"
        code = r["driver"]
        name = r.get("name") or r["driver"]
        best = r.get("best") or "—"
        rows.append((pos, code, name, best))

    title = f"Квалификация {season}"
    subtitle = f"Этап {latest_round:02d}"

    # ИСПРАВЛЕНО: Генерация картинки в потоке
    img_buf = await asyncio.to_thread(create_quali_results_image, title, subtitle, rows)

    photo = BufferedInputFile(img_buf.getvalue(), filename="quali_results.png")

    caption = (
        f"⏱ Результаты последней квалификации (таблица на картинке).\n"
        f"Сезон {season}, этап {latest_round:02d}."
    )

    if callback.message:
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("race_"))
async def race_callback(callback: CallbackQuery) -> None:
    try:
        parts = callback.data.split("_")
        season = int(parts[1])
    except Exception:
        season = datetime.now().year

    last_round = await get_last_reminded_round(season)
    if last_round is None:
        if callback.message:
            await callback.message.answer(
                "Пока нет гонок с сохранёнными результатами для этого сезона 🤔"
            )
        await callback.answer()
        return

    # ИСПРАВЛЕНО: await
    schedule = await get_season_schedule_short_async(season)
    race_info = None
    if schedule:
        race_info = next(
            (r for r in schedule if r["round"] == last_round),
            None,
        )

    # ИСПРАВЛЕНО: await на все тяжелые запросы
    race_results = await get_race_results_async(season, last_round)

    if race_results is None or race_results.empty:
        if callback.message:
            await callback.message.answer("Пока нет данных по результатам гонки 🤔")
        await callback.answer()
        return

    driver_standings = await get_driver_standings_async(season, round_number=last_round)
    constructor_standings = await get_constructor_standings_async(season, round_number=last_round)

    fav_drivers = await get_favorite_drivers(callback.from_user.id)
    fav_teams = await get_favorite_teams(callback.from_user.id)

    # --- ОФОРМЛЕНИЕ ---
    df = race_results
    if "Position" in df.columns:
        df = df.sort_values("Position")

    # (Далее идет логика формирования строк, она быстрая, оставляем синхронной)
    lines: list[str] = []
    max_positions = 20
    count = 0

    fav_drivers_set = set(fav_drivers or [])
    rows_for_image: list[tuple[str, str, str, str]] = []

    for row in df.itertuples(index=False):
        # ... (код цикла парсинга позиций без изменений) ...
        # Копируем логику из оригинала
        pos = getattr(row, "Position", None)
        if pos is None: continue
        try:
            pos_int = int(pos)
        except:
            continue

        count += 1
        if count > max_positions: break

        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
        # Имя
        given = getattr(row, "FirstName", "") or ""
        family = getattr(row, "LastName", "") or ""
        full_name = f"{given} {family}".strip() or code
        pts = getattr(row, "Points", None)

        is_fav = code in fav_drivers_set

        # Подготовка данных для картинки
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

    # ИСПРАВЛЕНО: Генерация картинки в потоке
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

    # --- БЛОК ПО ИЗБРАННЫМ КОМАНДАМ ---
    # (Логика формирования текста по командам остается прежней)
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

    if callback.message:
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode="HTML",
            has_spoiler=True,
        )

    await callback.answer()

