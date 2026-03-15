import asyncio
import logging
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

from app.db import get_favorite_teams
from app.f1_data import get_constructor_standings_async, sort_standings_zero_last
from app.utils.default import validate_f1_year
from app.utils.image_render import create_constructor_standings_image
from app.utils.loader import Loader
from app.utils.safe_send import safe_answer_callback

router = Router()


class TeamsYearState(StatesGroup):
    year = State()


async def _send_teams_for_year(message: Message, season: int, telegram_id: int | None = None) -> None:
    """
    Выводит таблицу кубка конструкторов за указанный год.
    Теперь в первую очередь рисуем картинку с таблицей
    (через image_render), а текст используем как запасной вариант.
    """
    async with Loader(message, f"⏳ Загружаю кубок конструкторов за {season} год..."):
        try:
            # Асинхронный вызов получения данных
            df = await get_constructor_standings_async(season)
        except Exception:
            await message.answer(
                "❌ Не удалось получить таблицу команд.\n"
                "Попробуй ещё раз чуть позже."
            )
            return

        if df.empty:
            await message.answer(f"Пока нет данных по кубку конструкторов за {season} год.")
            return

        df = sort_standings_zero_last(df)

        # Вытягиваем список избранных команд пользователя
        favorite_teams = []
        if telegram_id:
            favorite_teams = await get_favorite_teams(telegram_id)

        lines: list[str] = []
        rows_for_image: list[tuple[str, str, str, str]] = []

        for row in df.itertuples(index=False):
            # --- position ---
            pos_raw = getattr(row, "position", None)
            if pos_raw is None:
                continue
            if isinstance(pos_raw, float) and math.isnan(pos_raw):
                continue

            # --- Безопасная обработка прочерка ---
            if str(pos_raw).strip() == "-":
                position_str = "-"
                position_val = 99  # Фейковое число, чтобы не дать золотой кубок
            else:
                try:
                    position_val = int(pos_raw)
                    position_str = f"{position_val:02d}"
                except (TypeError, ValueError):
                    continue

            # --- points ---
            points_raw = getattr(row, "points", 0.0)
            if isinstance(points_raw, float) and math.isnan(points_raw):
                points = 0.0
            else:
                try:
                    points = float(points_raw)
                except (TypeError, ValueError):
                    points = 0.0

            team_name = getattr(row, "constructorName", "Unknown")

            # Пытаемся достать короткий код/ID команды
            constructor_code = ""
            for attr_name in ("constructorCode", "constructorRef", "constructorId"):
                val = getattr(row, attr_name, None)
                if isinstance(val, str) and val:
                    constructor_code = val
                    break

            if team_name in favorite_teams or constructor_code in favorite_teams:
                display_team_name = f"⭐️ {team_name}"
            else:
                display_team_name = team_name

            # --- кубки для 1–3 мест ---
            if position_val == 1:
                trophy = "🥇 "
            elif position_val == 2:
                trophy = "🥈 "
            elif position_val == 3:
                trophy = "🥉 "
            else:
                trophy = ""

            pos_display = position_str if position_str == "-" else f"{position_val:>2}"

            line = (
                f"{trophy}"
                f"{pos_display}. {display_team_name} — "
                f"{points:.0f} очков"
            )
            lines.append(line)

            # Данные для картинки
            rows_for_image.append(
                (
                    position_str,
                    constructor_code,
                    display_team_name,
                    f"{points:.0f} очк.",
                )
            )

        if not lines:
            await message.answer(f"Не удалось отобразить команды за {season} год (нет корректных данных).")
            return

        try:
            img_buf = await asyncio.to_thread(
                create_constructor_standings_image,
                title=f"Кубок конструкторов {season}",
                subtitle="",
                rows=rows_for_image,
                season=season,
            )

            img_buf.seek(0)
            photo = BufferedInputFile(
                img_buf.read(),
                filename=f"constructors_{season}.png",
            )

            await message.answer_photo(
                photo=photo,
                caption=f"🏎 Кубок конструкторов {season}",
            )
        except Exception as exc:
            logging.exception(
                "Не удалось сформировать или отправить картинку таблицы конструкторов: %s",
                exc,
            )
            text = (
                f"🏎 Кубок конструкторов {season}:\n\n"
                + "\n".join(lines[:30])
            )
            try:
                await message.answer(text)
            except TelegramNetworkError:
                return

def _parse_season_from_text(text: str) -> int:
    """
    Для команды /teams [год].
    Если год не указан или указан криво — берём текущий.
    """
    text = (text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return datetime.now().year


@router.message(Command("teams"))
async def cmd_teams(message: Message) -> None:
    """
    Старое поведение: /teams или /teams 2005.
    В группах — без избранного.
    """
    season = _parse_season_from_text(message.text or "")
    telegram_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_teams_for_year(message, season, telegram_id)


@router.message(F.text == "🏆 Кубок конструкторов")
async def btn_teams_ask_year(message: Message, state: FSMContext) -> None:
    """
    Нажали кнопку «Кубок конструкторов» — спрашиваем год
    и даём кнопку «Текущий сезон (YYYY)».
    """
    current_year = datetime.now().year

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Текущий сезон ({current_year})", callback_data=f"teams_current_{current_year}",)],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")]
        ]
    )

    await message.answer(
        "🏎 За какой год показать кубок конструкторов?\n"
        "Напиши год цифрами или нажми кнопку ниже для текущего сезона.",
        reply_markup=kb,
    )
    await state.set_state(TeamsYearState.year)


@router.message(TeamsYearState.year)
async def teams_year_from_text(message: Message, state: FSMContext) -> None:
    """
    Пользователь ответил годом текстом.
    """
    if not message.text.isdigit():
        await message.answer("🏎 За какой год показать кубок конструкторов?\n"
        "Напиши год цифрами или нажми кнопку ниже для текущего сезона.")
        return

    year = int(message.text)

    error_msg = validate_f1_year(year)
    if error_msg:
        await message.answer(error_msg)
        return

    await state.update_data(year=year)
    telegram_id = message.from_user.id if message.chat.type == ChatType.PRIVATE else None
    await _send_teams_for_year(message, year, telegram_id)
    await state.clear()


@router.callback_query(F.data.startswith("teams_current_"))
async def teams_year_current(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Пользователь нажал кнопку «Текущий сезон (YYYY)».
    """
    await state.clear()
    await safe_answer_callback(callback)

    year_str = callback.data.split("_")[-1]
    try:
        season = int(year_str)
    except ValueError:
        season = datetime.now().year

    if callback.message:
        telegram_id = callback.from_user.id if callback.message.chat.type == ChatType.PRIVATE else None
        await _send_teams_for_year(callback.message, season, telegram_id)
