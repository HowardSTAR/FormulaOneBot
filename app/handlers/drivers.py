from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from datetime import datetime
import math

from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.utils.f1_data import get_driver_standings_df

router = Router()


class DriversYearState(StatesGroup):
    waiting_for_year = State()


async def _send_drivers_for_year(message: Message, season: int) -> None:
    try:
        df = get_driver_standings_df(season)
    except Exception:
        await message.answer(
            "❌ Не удалось получить таблицу пилотов.\n"
            "Возможно, сейчас недоступен источник данных. Попробуй ещё раз позже."
        )
        return

    if df.empty:
        await message.answer(f"Пока нет данных по личному зачёту пилотов за {season} год.")
        return

    df = df.sort_values("position")

    lines: list[str] = []

    for row in df.itertuples(index=False):
        pos_raw = getattr(row, "position", None)
        if pos_raw is None:
            continue
        if isinstance(pos_raw, float) and math.isnan(pos_raw):
            continue
        try:
            position = int(pos_raw)
        except (TypeError, ValueError):
            continue

        points_raw = getattr(row, "points", 0.0)
        if isinstance(points_raw, float) and math.isnan(points_raw):
            points = 0.0
        else:
            try:
                points = float(points_raw)
            except (TypeError, ValueError):
                points = 0.0

        given_name = getattr(row, "givenName", "")
        family_name = getattr(row, "familyName", "")
        full_name = f"{given_name} {family_name}".strip()

        if position == 1:
            trophy = "🥇 "
        elif position == 2:
            trophy = "🥈 "
        elif position == 3:
            trophy = "🥉 "
        else:
            trophy = ""

        line = (
            f"{trophy}"
            f"{position:>2}. "
            f"{full_name} — "
            f"{points:.0f} очков"
        )

        lines.append(line)

    if not lines:
        await message.answer(f"Не удалось отобразить пилотов за {season} год (нет корректных данных).")
        return

    text = (
        f"🏁 Пилоты сезона {season}:\n\n"
        + "\n".join(lines[:30])
    )

    try:
        await message.answer(text)
    except TelegramNetworkError:
        return


def _parse_season_from_text(text: str) -> int:
    text = (text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return datetime.now().year


@router.message(Command("drivers"))
async def cmd_drivers(message: Message) -> None:
    season = _parse_season_from_text(message.text or "")
    await _send_drivers_for_year(message, season)


@router.message(F.text == "Личный зачет")
async def btn_drivers_ask_year(message: Message, state: FSMContext) -> None:
    current_year = datetime.now().year

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Текущий сезон ({current_year})",
                    callback_data=f"drivers_current_{current_year}",
                )
            ]
        ]
    )

    await message.answer(
        "🏁 За какой год показать личный зачет?\n"
        "Напиши год цифрами или нажми кнопку ниже для текущего сезона.",
        reply_markup=kb,
    )
    await state.set_state(DriversYearState.waiting_for_year)


@router.message(DriversYearState.waiting_for_year)
async def drivers_year_from_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        season = int(text)
    except ValueError:
        await message.answer("Пожалуйста, введи год цифрами, например: 2016")
        return

    await state.clear()
    await _send_drivers_for_year(message, season)


@router.callback_query(F.data.startswith("drivers_current_"))
async def drivers_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    year_str = callback.data.split("_")[-1]
    try:
        season = int(year_str)
    except ValueError:
        season = datetime.now().year

    if callback.message:
        await _send_drivers_for_year(callback.message, season)

    await callback.answer()
