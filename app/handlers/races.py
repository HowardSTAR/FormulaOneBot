import asyncio
import logging
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
import random

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile

from app.utils.image_render import create_results_image
from app.db import (
    get_last_reminded_round,
    get_favorite_drivers,
    get_favorite_teams,
)
from app.f1_data import get_season_schedule_short, get_weekend_schedule, get_race_results_df, \
    get_constructor_standings_df, \
    get_driver_standings_df, _get_latest_quali_async



SESSION_NAME_RU = {
    "Practice 1": "Практика 1",
    "Practice 2": "Практика 2",
    "Practice 3": "Практика 3",
    "Free Practice 1": "Практика 1",
    "Free Practice 2": "Практика 2",
    "Free Practice 3": "Практика 3",

    "Sprint Qualifying": "Спринт-квалификация",
    "Sprint Shootout": "Спринт-квалификация",  # на всякий случай
    "Sprint": "Спринт",

    "Qualifying": "Квалификация",
    "Race": "Гонка",
}


router = Router()

UTC_PLUS_3 = timezone(timedelta(hours=3))

class RacesYearState(StatesGroup):
    waiting_for_year = State()




async def _send_races_for_year(message: Message, season: int) -> None:
    races = get_season_schedule_short(season)

    if not races:
        await message.answer(f"Нет данных по календарю сезона {season}.")
        return

    today = date.today()
    lines: list[str] = []

    for r in races:
        try:
            race_date = date.fromisoformat(r["date"])
        except ValueError:
            race_date = today

        finished = race_date < today
        status = "❌" if finished else "✅"

        if finished:
            line = (
                f"{status} "
                f"{r['round']:02d}. <i>{r['event_name']} "
                f"({r['country']})</i>"
            )
        else:
            date_str = race_date.strftime("%d.%m.%Y")
            line = (
                f"{status} "
                f"<b>{r['round']:02d}. {r['event_name']} "
                f"({r['country']})</b> — {date_str}"
            )

        lines.append(line)

    header = (
        f"<b>Календарь сезона {season}:</b>\n\n"
        f"❌ — гонка уже прошла (дата скрыта)\n"
        f"✅ — предстоящие гонки, дата показана\n\n\n"
    )
    text = header + "\n\n".join(lines)  # пустая строка между этапами
    await message.answer(text)


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
    try:
        _, season_str, round_str = callback.data.split("_")
        season = int(season_str)
        max_round = int(round_str)
    except Exception:
        await callback.answer("Не понял данные этапа 😅", show_alert=True)
        return

    # Набор «живых» сообщений, которыми будем мигать
    status_texts = [
        "🔍 Ищу последние данные по квалификации…",
        "📡 Подключаюсь к таймингу FIA…",
        "📊 Проверяю протокол и позиции пилотов…",
        "🧮 Считаю времена кругов…",
        "✨ Полирую таблицу результатов…",
        "🏁 Уточняю, кто реально на поуле…",
        "📶 Ловлю сигнал из паддока…",
        "🛰 Отправляю запрос на спутник телеметрии…",
        "🧑‍💻 Обновляю данные тайминга…",
        "⚙️ Прокручиваю карусель стратегий…",
        "🏎 Разгоняю бота до скоростей DRS…",
        "🧠 Анализирую тактику команд…",
    ]
    status_msg = None

    # Запускаем загрузку квалификации в отдельной задаче
    fetch_task = asyncio.create_task(
        _get_latest_quali_async(season, max_round=max_round, limit=20)
    )

    loop = asyncio.get_running_loop()
    start = loop.time()
    timeout = 10.0  # общий лимит ожидания

    # Крутимся, пока задача не завершилась или не истёк таймаут
    while not fetch_task.done():
        # Проверка таймаута
        if loop.time() - start > timeout:
            logging.warning(
                "[QUALI] Таймаут при получении квалификации season=%s, max_round=%s",
                season, max_round,
            )
            fetch_task.cancel()
            try:
                await fetch_task
            except asyncio.CancelledError:
                pass

            # На всякий случай удалим последнее статусное сообщение
            if status_msg is not None:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            await callback.message.answer(
                "Пока нет данных по результатам квалификации 🤔\n"
                "Скорее всего, сессия ещё не закончилась или данные недоступны."
            )
            await callback.answer()
            return

        # Отправляем случайный статус
        text = random.choice(status_texts)

        try:
            status_msg = await callback.message.answer(text)
        except Exception:
            status_msg = None

        # Даём пользователю чуть-чуть времени увидеть сообщение
        await asyncio.sleep(1.2)

        # Сразу же удаляем этот статус
        if status_msg is not None:
            try:
                await status_msg.delete()
            except Exception:
                pass

    # Здесь задача уже завершилась (без таймаута) —
    # на всякий случай удалим последнее статусное сообщение
    if status_msg is not None:
        try:
            await status_msg.delete()
        except Exception:
            pass

    # Достаём результат задачи
    try:
        round_num, results = fetch_task.result()
    except Exception as exc:
        logging.exception("Ошибка при получении квалификации: %s", exc)
        await callback.message.answer(
            "Пока нет данных по результатам квалификации 🤔\n"
            "Скорее всего, сессия ещё не закончилась или данные недоступны."
        )
        await callback.answer()
        return

    # нет найденной квалификации или список пустой
    if not round_num or not results:
        await callback.message.answer(
            "Пока нет данных по результатам квалификации 🤔"
        )
        await callback.answer()
        return

    # --- ниже оставляешь твоё текущее форматирование результатов ---
    # здесь можешь подставить свою логику со спойлерами и т.п.

    lines = [
        f"⏱ <b>Результаты квалификации</b>\n"
        f"Сезон {season}, этап {round_num}\n",
        "",
        "||Таблица результатов будет тут||",  # сюда подставь вывод results
    ]

    text = "\n".join(lines)
    await callback.message.answer(text, parse_mode="HTML")
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
    rows_for_image: list[tuple[str, str, str]] = []

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

        is_fav = code in fav_drivers_set

        # ⭐️ ставим перед кодом избранного пилота
        prefix_star = "⭐️ " if is_fav else ""

        line = f"{pos_int:02d}. {prefix_star}<b>{code}</b>"
        if team:
            line += f" — {team}"
        if pts is not None:
            line += f" ({pts} очк.)"
        lines.append(line)

        # Заполняем данные для картинки
        extra_parts = []
        if team:
            extra_parts.append(team)
        if pts is not None:
            extra_parts.append(f"{pts} очк.")

        extra_str = " — ".join(extra_parts) if extra_parts else ""
        code_for_img = f"⭐️ {code}" if is_fav else code

        rows_for_image.append(
            (f"{pos_int:02d}", code_for_img, extra_str)
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


