import asyncio
import math
from datetime import datetime

from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramNetworkError
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

from app.db import get_favorite_drivers
from app.f1_data import (
    get_driver_standings_async,
    sort_standings_zero_last,
)
from app.utils.default import validate_f1_year
from app.utils.image_render import create_driver_standings_image
from app.utils.loader import Loader
from app.utils.safe_send import safe_answer_callback

router = Router()


class DriversYearState(StatesGroup):
    year = State()


async def _send_drivers_for_year(message: Message, season: int, telegram_id: int | None = None) -> None:
    async with Loader(message, text="⏳ Получаю таблицу пилотов...") as loader:
        try:
            # Same published season table as teams and the comparison picker.
            # Do not infer the last classification from an elapsed-time guess.
            df = await get_driver_standings_async(season)
        except Exception:
            await message.answer(
                "❌ Не удалось получить таблицу пилотов.\n"
                "Возможно, сейчас недоступен источник данных. Попробуй ещё раз позже."
            )
            return

        if df.empty:
            await message.answer(f"❌ Нет данных о пилотах за сезон {season}.")
            return

        df = sort_standings_zero_last(df)

        favorite_codes: set[str] = set()
        if telegram_id is not None:
            try:
                fav_list = await get_favorite_drivers(telegram_id)
                favorite_codes = set(fav_list)
            except Exception:
                favorite_codes = set()

        rows: list[dict] = []

        for row in df.itertuples(index=False):
            pos_raw = getattr(row, "position", None)
            if pos_raw is None or (isinstance(pos_raw, float) and math.isnan(pos_raw)) or str(pos_raw).strip() in ("-", ""):
                position_str = "-"
                position_val = "-"
            else:
                try:
                    position_val = int(float(pos_raw))
                    position_str = f"{position_val:02d}"
                except (TypeError, ValueError):
                    position_str = "-"
                    position_val = "-"

            code = getattr(row, "driverCode", "") or getattr(row, "code", "") or ""
            if not code:
                family = getattr(row, "familyName", "") or ""
                code = family[:3].upper() if family else ""
            if not code and not getattr(row, "familyName", None):
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

            rows.append({"pos": position_str, "code": code, "name": full_name or code or str(position_val),
                         "points": f"{points:g}", "team": getattr(row, "constructorName", "") or "",
                         "favorite": code in favorite_codes})

        if not rows:
            await message.answer(
                f"Не удалось отобразить пилотов за {season} год (нет корректных данных)."
            )
            return

        title = f"Личный зачёт {season}"
        subtitle = "Позиции пилотов в чемпионате"

        # Обновляем текст, чтобы пользователь видел прогресс
        await loader.update("🎨 Рисую таблицу пилотов...")

        try:
            img_buf = await asyncio.to_thread(
                create_driver_standings_image, title, subtitle, rows, season=season
            )
        except Exception as exc:
            await message.answer("Не удалось сформировать изображение таблицы.")
            return

        # Завершающий статус
        await loader.update("📤 Отправляю результат...")

        img_buf.seek(0)
        photo = BufferedInputFile(
            img_buf.read(),
            filename=f"drivers_standings_{season}.png",
        )

        try:
            # Картинка отправится, и только после этого лоадер сам себя удалит!
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
    telegram_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_drivers_for_year(message, season, telegram_id=telegram_id)


@router.message(F.text == "🏎 Личный зачет")
async def btn_drivers_ask_year(message: Message, state: FSMContext) -> None:
    current_year = datetime.now().year

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Текущий сезон ({current_year})", callback_data=f"drivers_current_{current_year}",)],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")]
        ]
    )

    await message.answer(
        "🏁 За какой год показать личный зачет?\n"
        "Напиши год цифрами или нажми кнопку ниже для текущего сезона.",
        reply_markup=kb,
    )
    await state.set_state(DriversYearState.year)


@router.message(DriversYearState.year)
async def drivers_year_from_text(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите год числом (например, 2007).")
        return

    year = int(message.text)

    error_msg = validate_f1_year(year)
    if error_msg:
        await message.answer(error_msg)
        return

    # Дальше ваш старый код...
    await state.update_data(year=year)
    telegram_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_drivers_for_year(message, year, telegram_id=telegram_id)
    await state.clear()


@router.callback_query(F.data.startswith("drivers_current_"))
async def drivers_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    if (await state.get_state() or "").startswith("CompareState:"):
        await safe_answer_callback(callback, "Это старая кнопка личного зачёта. В сравнении выберите сезон под новым сообщением.", show_alert=True)
        return
    await state.clear()
    await safe_answer_callback(callback)
    year_str = callback.data.split("_")[-1]
    try:
        season = int(year_str)
    except ValueError:
        season = datetime.now().year

    if callback.message:
        telegram_id = callback.from_user.id if callback.message.chat.type == ChatType.PRIVATE else None
        await _send_drivers_for_year(callback.message, season, telegram_id=telegram_id)
