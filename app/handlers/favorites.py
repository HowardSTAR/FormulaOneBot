from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from datetime import datetime

from app.f1_data import get_driver_standings_df, get_constructor_standings_df
from app.db import (
    add_favorite_driver,
    remove_favorite_driver,
    get_favorite_drivers,
    add_favorite_team,
    remove_favorite_team,
    get_favorite_teams,
    clear_all_favorites,
)

router = Router()


# --- Главное меню Избранного --- #

@router.message(F.text == "Избранное")
async def favorites_menu(message: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Любимые пилоты",
                    callback_data="fav_menu_drivers",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏎 Любимые команды",
                    callback_data="fav_menu_teams",
                )
            ],
        ]
    )

    await message.answer(
        "Что хочешь настроить?\n"
        "Можно выбрать несколько пилотов и команд.",
        reply_markup=kb,
    )


# --- Любимые пилоты --- #

async def _build_drivers_keyboard(telegram_id: int, season: int) -> tuple[InlineKeyboardMarkup, bool]:
    """
    Создает клавиатуру с пилотами.
    
    Returns:
        tuple[InlineKeyboardMarkup, bool]: (клавиатура, есть_ли_данные)
    """
    df = get_driver_standings_df(season)
    
    # Если данных нет, возвращаем клавиатуру только с кнопкой "Назад"
    if df.empty:
        buttons = [
            [InlineKeyboardButton(text="⬅ Назад", callback_data="fav_back_main")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons), False
    
    df = df.sort_values("position")

    favorites = set(await get_favorite_drivers(telegram_id))

    buttons = []
    row = []
    for row_data in df.itertuples(index=False):
        code = getattr(row_data, "driverCode", "") or ""
        given_name = getattr(row_data, "givenName", "")
        family_name = getattr(row_data, "familyName", "")
        if not code:
            continue

        full_name = f"{given_name} {family_name}".strip()
        is_fav = code in favorites
        prefix = "⭐" if is_fav else "☆"
        text = f"{prefix} {code} {full_name}"

        row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=f"fav_driver_toggle_{code}",
            )
        )

        # делаем по 1–2 кнопки в строке, чтобы не было месива
        if len(row) == 1:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="⬅ Назад", callback_data="fav_back_main")]
    )

    has_data = len(buttons) > 1  # больше чем только кнопка "Назад"
    return InlineKeyboardMarkup(inline_keyboard=buttons), has_data


@router.callback_query(F.data == "fav_menu_drivers")
async def fav_menu_drivers(callback: CallbackQuery) -> None:
    season = datetime.now().year
    telegram_id = callback.from_user.id

    kb, has_data = await _build_drivers_keyboard(telegram_id, season)

    if has_data:
        text = (
            f"⭐ Выбор любимых пилотов сезона {season}.\n"
            f"Нажимай на пилота, чтобы добавить/убрать из избранного."
        )
    else:
        text = (
            f"⭐ Выбор любимых пилотов сезона {season}.\n\n"
            f"❌ К сожалению, данные по пилотам за этот сезон пока недоступны.\n"
            f"Возможно, сезон ещё не начался или данные ещё не обновлены."
        )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb)

    await callback.answer()


@router.callback_query(F.data.startswith("fav_driver_toggle_"))
async def fav_driver_toggle(callback: CallbackQuery) -> None:
    code = callback.data.split("_")[-1]
    telegram_id = callback.from_user.id
    season = datetime.now().year

    favorites = set(await get_favorite_drivers(telegram_id))

    if code in favorites:
        await remove_favorite_driver(telegram_id, code)
    else:
        await add_favorite_driver(telegram_id, code)

    # Обновляем клавиатуру
    kb, has_data = await _build_drivers_keyboard(telegram_id, season)
    if has_data:
        text = (
            f"⭐ Выбор любимых пилотов сезона {season}.\n"
            f"Нажимай на пилота, чтобы добавить/убрать из избранного."
        )
    else:
        text = (
            f"⭐ Выбор любимых пилотов сезона {season}.\n\n"
            f"❌ К сожалению, данные по пилотам за этот сезон пока недоступны.\n"
            f"Возможно, сезон ещё не начался или данные ещё не обновлены."
        )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb)

    await callback.answer()


# --- Любимые команды --- #

async def _build_teams_keyboard(telegram_id: int, season: int) -> tuple[InlineKeyboardMarkup, bool]:
    """
    Создает клавиатуру с командами.
    
    Returns:
        tuple[InlineKeyboardMarkup, bool]: (клавиатура, есть_ли_данные)
    """
    df = get_constructor_standings_df(season)
    
    # Если данных нет, возвращаем клавиатуру только с кнопкой "Назад"
    if df.empty:
        buttons = [
            [InlineKeyboardButton(text="⬅ Назад", callback_data="fav_back_main")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons), False
    
    df = df.sort_values("position")

    favorites = set(await get_favorite_teams(telegram_id))

    buttons = []
    row = []
    for row_data in df.itertuples(index=False):
        team_name = getattr(row_data, "constructorName", None)
        if not team_name:
            continue

        is_fav = team_name in favorites
        prefix = "⭐" if is_fav else "☆"
        text = f"{prefix} {team_name}"

        row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=f"fav_team_toggle_{team_name}",
            )
        )

        if len(row) == 1:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="⬅ Назад", callback_data="fav_back_main")]
    )

    has_data = len(buttons) > 1  # больше чем только кнопка "Назад"
    return InlineKeyboardMarkup(inline_keyboard=buttons), has_data


@router.callback_query(F.data == "fav_menu_teams")
async def fav_menu_teams(callback: CallbackQuery) -> None:
    season = datetime.now().year
    telegram_id = callback.from_user.id

    kb, has_data = await _build_teams_keyboard(telegram_id, season)

    if has_data:
        text = (
            f"🏎 Выбор любимых команд сезона {season}.\n"
            f"Нажимай на команду, чтобы добавить/убрать из избранного."
        )
    else:
        text = (
            f"🏎 Выбор любимых команд сезона {season}.\n\n"
            f"❌ К сожалению, данные по командам за этот сезон пока недоступны.\n"
            f"Возможно, сезон ещё не начался или данные ещё не обновлены."
        )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb)

    await callback.answer()


@router.callback_query(F.data.startswith("fav_team_toggle_"))
async def fav_team_toggle(callback: CallbackQuery) -> None:
    # В callback_data team_name может содержать пробелы, поэтому split("_", 3) смысла нет —
    # мы заранее сделали формат "fav_team_toggle_{team_name}" и просто отделяем первые два.
    prefix, _, rest = callback.data.partition("fav_team_toggle_")
    team_name = rest
    telegram_id = callback.from_user.id
    season = datetime.now().year

    favorites = set(await get_favorite_teams(telegram_id))

    if team_name in favorites:
        await remove_favorite_team(telegram_id, team_name)
    else:
        await add_favorite_team(telegram_id, team_name)

    kb, has_data = await _build_teams_keyboard(telegram_id, season)
    if has_data:
        text = (
            f"🏎 Выбор любимых команд сезона {season}.\n"
            f"Нажимай на команду, чтобы добавить/убрать из избранного."
        )
    else:
        text = (
            f"🏎 Выбор любимых команд сезона {season}.\n\n"
            f"❌ К сожалению, данные по командам за этот сезон пока недоступны.\n"
            f"Возможно, сезон ещё не начался или данные ещё не обновлены."
        )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb)

    await callback.answer()


# --- Назад в главное меню избранного --- #

@router.callback_query(F.data == "fav_back_main")
async def fav_back_main(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Любимые пилоты",
                    callback_data="fav_menu_drivers",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏎 Любимые команды",
                    callback_data="fav_menu_teams",
                )
            ],
        ]
    )

    if callback.message:
        await callback.message.edit_text(
            "Что хочешь настроить?\n"
            "Можно выбрать несколько пилотов и команд.",
            reply_markup=kb,
        )

    await callback.answer()


@router.message(Command("my_favorites"))
async def cmd_my_favorites(message: Message) -> None:
    """
    Показывает текущий список любимых пилотов и команд.
    Ставит имена, если удаётся сопоставить с текущим сезоном.
    """
    telegram_id = message.from_user.id
    current_year = datetime.now().year

    fav_drivers_codes = await get_favorite_drivers(telegram_id)
    fav_teams_names = await get_favorite_teams(telegram_id)

    # Карта код пилота -> имя из текущего сезона (если есть)
    driver_name_by_code: dict[str, str] = {}
    try:
        df_drivers = get_driver_standings_df(current_year)
        for row in df_drivers.itertuples(index=False):
            code = getattr(row, "driverCode", None)
            if not code:
                continue
            given = getattr(row, "givenName", "")
            family = getattr(row, "familyName", "")
            full_name = f"{given} {family}".strip() or code
            driver_name_by_code[code] = full_name
    except Exception:
        # Если вдруг FastF1/сеть упали — просто покажем коды
        driver_name_by_code = {}

    # Карта названия команды -> национальность (для красоты)
    team_nat_by_name: dict[str, str] = {}
    try:
        df_teams = get_constructor_standings_df(current_year)
        for row in df_teams.itertuples(index=False):
            name = getattr(row, "constructorName", None)
            nat = getattr(row, "constructorNationality", "") or ""
            if name:
                team_nat_by_name[name] = nat
    except Exception:
        team_nat_by_name = {}

    lines: list[str] = []

    # Пилоты
    if fav_drivers_codes:
        lines.append("⭐ <b>Любимые пилоты:</b>")
        for code in fav_drivers_codes:
            name = driver_name_by_code.get(code, "")
            if name:
                lines.append(f"• {code} — {name}")
            else:
                lines.append(f"• {code}")
        lines.append("")  # пустая строка
    else:
        lines.append("⭐ <b>Любимые пилоты:</b> пока не выбраны.")
        lines.append("")

    # Команды
    if fav_teams_names:
        lines.append("🏎 <b>Любимые команды:</b>")
        for team in fav_teams_names:
            nat = team_nat_by_name.get(team, "")
            if nat:
                lines.append(f"• {team} ({nat})")
            else:
                lines.append(f"• {team}")
    else:
        lines.append("🏎 <b>Любимые команды:</b> пока не выбраны.")

    # Кнопка очистки
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧹 Очистить избранное",
                    callback_data="fav_clear_confirm",
                )
            ]
        ]
    )

    text = "\n".join(lines)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "fav_clear_confirm")
async def fav_clear_confirm(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, очистить всё",
                    callback_data="fav_clear_yes",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="fav_clear_no",
                )
            ],
        ]
    )

    if callback.message:
        await callback.message.edit_text(
            "Ты точно хочешь <b>полностью очистить</b> избранное "
            "(пилоты и команды)?",
            reply_markup=kb,
        )
    await callback.answer()


@router.callback_query(F.data == "fav_clear_yes")
async def fav_clear_yes(callback: CallbackQuery) -> None:
    telegram_id = callback.from_user.id
    await clear_all_favorites(telegram_id)

    if callback.message:
        await callback.message.edit_text(
            "🧹 Избранное очищено.\n\n"
            "Можешь снова выбрать любимых через кнопку «Избранное».",
            reply_markup=None,
        )
    await callback.answer("Избранное очищено")


@router.callback_query(F.data == "fav_clear_no")
async def fav_clear_no(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text(
            "Окей, ничего не трогаю 👍\n\n"
            "Можешь продолжать пользоваться ботом.",
            reply_markup=None,
        )
    await callback.answer("Отменено")

