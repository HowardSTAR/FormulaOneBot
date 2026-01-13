import asyncio
import math
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

# Импортируем нашу новую асинхронную обертку (убедись, что она есть в f1_data.py)
from app.f1_data import get_driver_standings_async
from app.utils.image_render import create_driver_standings_image
from app.db import get_favorite_drivers

router = Router()


class DriversYearState(StatesGroup):
    waiting_for_year = State()


async def _send_drivers_for_year(
    message: Message, season: int, telegram_id: int | None = None
) -> None:
    try:
        # ИСПРАВЛЕНО: Вызываем асинхронную версию получения данных,
        # чтобы не блокировать бота во время сетевого запроса.
        df = await get_driver_standings_async(season)
    except Exception:
        await message.answer(
            "❌ Не удалось получить таблицу пилотов.\n"
            "Возможно, сейчас недоступен источник данных. Попробуй ещё раз позже."
        )
        return

    if df.empty:
        await message.answer(
            f"Пока нет данных по личному зачёту пилотов за {season} год."
        )
        return

    df = df.sort_values("position")

    favorite_codes: set[str] = set()
    if telegram_id is not None:
        try:
            fav_list = await get_favorite_drivers(telegram_id)
            favorite_codes = set(fav_list)
        except Exception:
            favorite_codes = set()

    rows: list[tuple[str, str, str, str]] = []

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

        code = getattr(row, "driverCode", "") or ""

        if code and code in favorite_codes:
            code_label = f"⭐️ {code}"
        else:
            code_label = code

        points_text = f"{points:.0f} очк."

        rows.append(
            (
                f"{position:02d}",
                code_label,
                full_name or code_label or str(position),
                points_text,
            )
        )

    if not rows:
        await message.answer(
            f"Не удалось отобразить пилотов за {season} год (нет корректных данных)."
        )
        return

    title = f"Личный зачёт {season}"
    subtitle = "Позиции пилотов в чемпионате"

    # ИСПРАВЛЕНО: Генерация картинки (тяжелая операция CPU) вынесена в отдельный поток.
    # Это предотвращает зависание бота во время рисования таблицы.
    try:
        img_buf = await asyncio.to_thread(
            create_driver_standings_image, title, subtitle, rows
        )
    except Exception as exc:
        await message.answer("Не удалось сформировать изображение таблицы.")
        return

    # Перематываем буфер на начало и делаем InputFile
    img_buf.seek(0)
    photo = BufferedInputFile(
        img_buf.read(),
        filename=f"drivers_standings_{season}.png",
    )

    try:
        await message.answer_photo(
            photo=photo,
            caption=f"🏁 Личный зачёт пилотов {season}",
        )
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
    await _send_drivers_for_year(message, season, telegram_id=message.from_user.id)


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
    await _send_drivers_for_year(message, season, telegram_id=message.from_user.id)


@router.callback_query(F.data.startswith("drivers_current_"))
async def drivers_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    year_str = callback.data.split("_")[-1]
    try:
        season = int(year_str)
    except ValueError:
        season = datetime.now().year

    if callback.message:
        await _send_drivers_for_year(
            callback.message, season, telegram_id=callback.from_user.id
        )

    await callback.answer()