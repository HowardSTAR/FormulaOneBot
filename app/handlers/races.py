import logging
from datetime import datetime, date, timezone, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from fastf1._api import SessionNotAvailableError

from app.f1_data import get_season_schedule_short, get_weekend_schedule, get_qualifying_results, get_race_results, \
    _get_quali_async, _get_race_results_async

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
        lines.append(
            f"• <b>{s['name']}</b>\n"
            f"  {s['local']} / {s['utc']}"
        )

    text = (
        f"📅 Расписание уикенда сезона {season}, раунд {round_num}:\n\n" +
        "\n\n".join(lines)
    )

    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data.startswith("quali_"))
async def quali_callback(callback: CallbackQuery) -> None:
    # 1. Разбираем сезон и раунд из callback.data
    try:
        _, season_str, round_str = callback.data.split("_")
        season = int(season_str)
        round_num = int(round_str)
    except Exception:
        await callback.answer("Не понял данные этапа 😅", show_alert=True)
        return

    # 2. Быстрая проверка по календарю: гонка ещё не прошла?
    try:
        schedule = get_season_schedule_short(season)
    except Exception as exc:
        logging.exception("Не удалось получить календарь сезона %s: %s", season, exc)
        # в крайнем случае ведём себя как раньше
        schedule = []

    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_num), None)
        if race_info is not None:
            try:
                race_date = date.fromisoformat(race_info["date"])
            except Exception:
                race_date = None

            today = date.today()
            # если сама гонка ещё в будущем, квалификация с очень большой вероятностью тоже не прошла
            if race_date is not None and race_date > today:
                await callback.message.answer(
                    "Пока нет данных по результатам квалификации 🤔"
                )
                await callback.answer()
                return

    # 3. Если по календарю этап уже должен был состояться — пробуем реально тянуть данные
    try:
        results = await _get_quali_async(season, round_num, limit=20)
    except SessionNotAvailableError:
        # FastF1/Ergast ещё не отдали данные по сессии
        await callback.message.answer(
            "Пока нет данных по результатам квалификации 🤔"
        )
        await callback.answer()
        return
    except Exception as exc:
        logging.exception("Ошибка при получении квалификации: %s", exc)
        await callback.message.answer(
            "Похоже, квалификация ещё не прошла или данные недоступны 🤷‍♂️"
        )
        await callback.answer()
        return

    if not results:
        await callback.message.answer(
            "Пока нет данных по результатам квалификации 🤔"
        )
        await callback.answer()
        return

    # 4. Формируем текст
    lines = ["⏱ *Результаты квалификации*:", ""]
    for r in results:
        best = f" — {r['best']}" if r["best"] else ""
        lines.append(
            f"{r['position']:02d}. {r['driver']} ({r['team']}){best}"
        )

    text = "\n".join(lines)
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("race_"))
async def race_callback(callback: CallbackQuery) -> None:
    # 1. Разбираем сезон и раунд из callback.data: "race_2025_22"
    try:
        _, season_str, round_str = callback.data.split("_")
        season = int(season_str)
        round_num = int(round_str)
    except Exception:
        await callback.answer("Не понял данные этапа 😅", show_alert=True)
        return

    # 2. Быстрая проверка по календарю: гонка ещё не прошла?
    try:
        schedule = get_season_schedule_short(season)
    except Exception as exc:
        logging.exception("Не удалось получить календарь сезона %s: %s", season, exc)
        schedule = []

    race_info = None
    if schedule:
        race_info = next((r for r in schedule if r["round"] == round_num), None)

    if race_info is not None:
        try:
            race_date = date.fromisoformat(race_info["date"])
        except Exception:
            race_date = None

        today = date.today()
        # если дата гонки строго в будущем — результатов ещё точно нет
        if race_date is not None and race_date > today:
            await callback.message.answer(
                "Пока нет данных по результатам гонки 🤔"
            )
            await callback.answer()
            return

    # 3. Пробуем реально получить результаты гонки у FastF1
    try:
        results = await _get_race_results_async(season, round_num, limit=20)
    except SessionNotAvailableError:
        # FastF1 говорит, что данных ещё нет (гонка только-только прошла или ещё идёт)
        await callback.message.answer(
            "Пока нет данных по результатам гонки 🤔"
        )
        await callback.answer()
        return
    except Exception as exc:
        logging.exception(
            "Ошибка при получении результатов гонки (season=%s, round=%s): %s",
            season, round_num, exc
        )
        await callback.message.answer(
            "Похоже, гонка ещё не прошла или данные недоступны 🤷‍♂️"
        )
        await callback.answer()
        return

    if results is None or results.empty:
        await callback.message.answer(
            "Пока нет данных по результатам гонки 🤔"
        )
        await callback.answer()
        return

    # 4. Немного красоты: заголовок с названием этапа
    if race_info is not None:
        header = (
            f"🏁 *Результаты гонки*\n"
            f"{race_info['event_name']} — {race_info['country']}, {race_info['location']}\n\n"
        )
    else:
        header = "🏁 *Результаты гонки:*\n\n"

    # 5. Формируем список строк по пилотам
    # на всякий случай сортируем по Position
    if "Position" in results.columns:
        df = results.sort_values("Position")

    lines = []
    for row in df.itertuples(index=False):
        pos = getattr(row, "Position", None)
        if pos is None:
            continue
        try:
            pos_int = int(pos)
        except (TypeError, ValueError):
            continue

        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", "?")
        team = getattr(row, "TeamName", "")
        pts = getattr(row, "Points", None)

        line = f"{pos_int:02d}. {code}"
        if team:
            line += f" ({team})"
        if pts is not None:
            line += f" — {pts} очк."
        lines.append(line)

    if not lines:
        await callback.message.answer(
            "Пока нет данных по результатам гонки 🤔"
        )
        await callback.answer()
        return

    text = header + "\n".join(lines)
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


