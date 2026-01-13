from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

# ИСПРАВЛЕНО: Импортируем асинхронные функции получения данных
from app.f1_data import get_driver_standings_async, get_constructor_standings_async

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
                    callback_data="fav_menu_drivers_0",  # Добавили индекс страницы 0
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏎 Любимые команды",
                    callback_data="fav_menu_teams",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Очистить всё",
                    callback_data="fav_clear_ask",
                )
            ]
        ]
    )

    await message.answer(
        "Настройки избранного ⭐\n\n"
        "Выбери пилотов и команды, за которыми хочешь следить.\n"
        "Я буду присылать их результаты после каждой сессии.",
        reply_markup=kb,
    )


# --- Меню ПИЛОТОВ (с пагинацией) --- #

async def _build_drivers_keyboard(telegram_id: int, page: int = 0) -> InlineKeyboardMarkup:
    season = datetime.now().year
    # ИСПРАВЛЕНО: Асинхронное получение данных
    df = await get_driver_standings_async(season)

    # Если данных нет вообще (начало года или ошибка)
    if df.empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")]
        ])

    if "position" in df.columns:
        df = df.sort_values("position")

    # Получаем текущие подписки пользователя
    user_favs = set(await get_favorite_drivers(telegram_id))

    # Формируем список кнопок
    buttons = []
    for row in df.itertuples(index=False):
        code = getattr(row, "driverCode", "")
        # Имя для кнопки: "VER", "HAM" или фамилия
        label = code or getattr(row, "familyName", "???")

        if not code:
            continue

        # Если в избранном — ставим галочку
        text = f"✅ {label}" if code in user_favs else label
        callback_data = f"fav_toggle_driver_{code}_{page}"

        buttons.append(InlineKeyboardButton(text=text, callback_data=callback_data))

    # ПАГИНАЦИЯ: разбиваем по 10-12 кнопок на страницу
    ITEMS_PER_PAGE = 12
    total_pages = (len(buttons) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    # Срезаем нужную страницу
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_buttons = buttons[start:end]

    # Собираем клавиатуру (по 3 в ряд)
    rows = []
    chunk_size = 3
    for i in range(0, len(current_buttons), chunk_size):
        rows.append(current_buttons[i:i + chunk_size])

    # Кнопки навигации
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"fav_menu_drivers_{page - 1}"))

    nav_row.append(InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main"))

    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"fav_menu_drivers_{page + 1}"))

    rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("fav_menu_drivers_"))
async def fav_menu_drivers_paginated(callback: CallbackQuery) -> None:
    try:
        page = int(callback.data.split("_")[-1])
    except ValueError:
        page = 0

    kb = await _build_drivers_keyboard(callback.from_user.id, page)

    # Если это новое сообщение или редактирование старого
    if callback.message.text and "пилота" in callback.message.text:
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            # Если клавиатура не изменилась
            pass
    else:
        await callback.message.edit_text(
            "Нажми на пилота, чтобы добавить/удалить из избранного:",
            reply_markup=kb
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fav_toggle_driver_"))
async def fav_toggle_driver(callback: CallbackQuery) -> None:
    # формат: fav_toggle_driver_VER_0
    parts = callback.data.split("_")
    driver_code = parts[3]
    try:
        page = int(parts[4])
    except IndexError:
        page = 0

    telegram_id = callback.from_user.id
    current_favs = await get_favorite_drivers(telegram_id)

    if driver_code in current_favs:
        await remove_favorite_driver(telegram_id, driver_code)
        action_text = f"❌ {driver_code} удалён"
    else:
        await add_favorite_driver(telegram_id, driver_code)
        action_text = f"✅ {driver_code} добавлен"

    # Перестраиваем клавиатуру, чтобы обновить галочку
    kb = await _build_drivers_keyboard(telegram_id, page)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

    await callback.answer(action_text)


# --- Меню КОМАНД (без пагинации, их мало) --- #

async def _build_teams_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    season = datetime.now().year
    # ИСПРАВЛЕНО: Асинхронно
    df = await get_constructor_standings_async(season)

    if df.empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")]
        ])

    if "position" in df.columns:
        df = df.sort_values("position")

    user_favs = set(await get_favorite_teams(telegram_id))

    buttons = []
    for row in df.itertuples(index=False):
        name = getattr(row, "constructorName", "")
        if not name:
            continue

        text = f"✅ {name}" if name in user_favs else name
        # Используем хэш или обрезаем имя, если оно очень длинное, 
        # но обычно названия команд влезают в callback_data (64 байта)
        # Для надежности лучше использовать ID, но у нас сейчас name в базе
        cb_data = f"fav_toggle_team_{name[:20]}"

        buttons.append(InlineKeyboardButton(text=text, callback_data=cb_data))

    # Сетка по 1-2 в ряд
    rows = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "fav_menu_teams")
async def fav_menu_teams(callback: CallbackQuery) -> None:
    kb = await _build_teams_keyboard(callback.from_user.id)
    await callback.message.edit_text(
        "Нажми на команду, чтобы добавить/удалить:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fav_toggle_team_"))
async def fav_toggle_team(callback: CallbackQuery) -> None:
    # Имя команды может содержать пробелы, поэтому берем всё после префикса
    prefix = "fav_toggle_team_"
    team_name_partial = callback.data[len(prefix):]

    telegram_id = callback.from_user.id

    # Нам нужно найти полное имя команды, так как в callback мы могли его обрезать.
    # Загрузим список снова
    season = datetime.now().year
    df = await get_constructor_standings_async(season)

    target_team = None
    for row in df.itertuples(index=False):
        name = getattr(row, "constructorName", "")
        if name.startswith(team_name_partial):  # Простое сравнение
            target_team = name
            break

    if not target_team:
        await callback.answer("Ошибка поиска команды")
        return

    current_favs = await get_favorite_teams(telegram_id)
    if target_team in current_favs:
        await remove_favorite_team(telegram_id, target_team)
        msg = f"❌ {target_team} удалена"
    else:
        await add_favorite_team(telegram_id, target_team)
        msg = f"✅ {target_team} добавлена"

    kb = await _build_teams_keyboard(telegram_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(msg)


# --- Общие кнопки --- #

@router.callback_query(F.data == "fav_main")
async def fav_main_callback(callback: CallbackQuery) -> None:
    # Возвращаемся в главное меню избранного
    # (Вызываем ту же логику, что и в favorites_menu, но редактируем сообщение)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Любимые пилоты", callback_data="fav_menu_drivers_0")],
            [InlineKeyboardButton(text="🏎 Любимые команды", callback_data="fav_menu_teams")],
            [InlineKeyboardButton(text="🗑 Очистить всё", callback_data="fav_clear_ask")]
        ]
    )
    await callback.message.edit_text(
        "Настройки избранного ⭐\nВыбери категорию:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "fav_clear_ask")
async def fav_clear_ask(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить", callback_data="fav_clear_yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="fav_main")]
        ]
    )
    await callback.message.edit_text(
        "Ты точно хочешь удалить ВСЕ подписки?",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "fav_clear_yes")
async def fav_clear_yes(callback: CallbackQuery) -> None:
    await clear_all_favorites(callback.from_user.id)
    await callback.answer("Список очищен")
    # Возвращаем пользователя в главное меню избранного
    await fav_main_callback(callback)