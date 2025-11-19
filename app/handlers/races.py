from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from datetime import datetime, date

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.f1_data import get_season_schedule_short

router = Router()


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
        status = "✅" if finished else "❌"

        if finished:
            line = (
                f"{status} "
                f"{r['round']:02d}. {r['event_name']} "
                f"({r['country']})"
            )
        else:
            line = (
                f"{status} "
                f"{r['round']:02d}. {r['event_name']} "
                f"({r['country']}) — {r['date']}"
            )

        lines.append(line)

    header = (
        f"Календарь сезона {season}:\n"
        f"✅ — гонка уже прошла (дата скрыта)\n"
        f"❌ — предстоящие гонки, дата показана\n\n"
    )
    text = header + "\n\n".join(lines)  # пустая строка между этапами
    await message.answer(text)


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
    # старое поведение: /races или /races 2005
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
