from datetime import datetime
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

from app.db import (
    get_favorite_drivers, add_favorite_driver, remove_favorite_driver,
    get_favorite_teams, add_favorite_team, remove_favorite_team
)
from app.f1_data import get_driver_standings_async, get_constructor_standings_async, sort_standings_zero_last

router = Router()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def _build_drivers_keyboard(telegram_id: int) -> tuple[InlineKeyboardMarkup, str]:
    current_year = datetime.now().year
    target_season = current_year
    is_outdated = False

    # 1. Логика сезона
    df = await get_driver_standings_async(target_season)
    if df.empty:
        target_season = current_year - 1
        df = await get_driver_standings_async(target_season)
        is_outdated = True

    # 2. Текст сообщения
    if is_outdated:
        info_text = (
            f"⚠️ Межсезонье\n"
            f"Составы на {current_year} год еще не готовы.\n"
            f"Показываем пилотов сезона {target_season}:"
        )
    else:
        info_text = f"🏎 Пилоты сезона {target_season}:\nОтметь тех, за кем следишь:"

    if df.empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")]
        ]), "❌ Данные недоступны."

    if "position" in df.columns:
        df = sort_standings_zero_last(df)

    # 3. Избранное
    favorites = await get_favorite_drivers(telegram_id)
    fav_set = set(favorites)

    builder = InlineKeyboardBuilder()

    # 4. Кнопки пилотов
    for row in df.itertuples(index=False):
        try:
            code = getattr(row, "driverCode", "")
            given = getattr(row, "givenName", "")
            family = getattr(row, "familyName", "")
            full_name = f"{given} {family}".strip() or code

            if not code: continue

            is_selected = code in fav_set
            btn_text = f"{'⭐ ' if is_selected else ''}{full_name}"

            builder.button(text=btn_text, callback_data=f"toggle_driver_{code}", style="success" if is_selected else None)
        except:
            continue

    # 2 КОЛОНКИ
    builder.adjust(2)

    # Кнопки управления
    builder.row(
        InlineKeyboardButton(text="🗑 Очистить всё", callback_data="ask_clear_drivers"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")
    )

    return builder.as_markup(), info_text


async def _build_teams_keyboard(telegram_id: int) -> tuple[InlineKeyboardMarkup, str]:
    current_year = datetime.now().year
    target_season = current_year
    is_outdated = False

    df = await get_constructor_standings_async(target_season)
    if df.empty:
        target_season = current_year - 1
        df = await get_constructor_standings_async(target_season)
        is_outdated = True

    if is_outdated:
        info_text = (
            f"⚠️ Межсезонье\n"
            f"Данные на {current_year} год обновляются.\n"
            f"Команды сезона {target_season}:"
        )
    else:
        info_text = f"🛠 Кубок конструкторов {target_season}:\nВыбери любимые команды:"

    if df.empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")]
        ]), "❌ Данные недоступны."

    favorites = await get_favorite_teams(telegram_id)
    fav_set = set(favorites)

    builder = InlineKeyboardBuilder()

    for row in df.itertuples(index=False):
        try:
            name = getattr(row, "constructorName", "Unknown")
            is_selected = name in fav_set
            btn_text = f"{'⭐ ' if is_selected else ''}{name}"
            builder.button(text=btn_text, callback_data=f"toggle_team_{name}", style="success" if is_selected else None)
        except:
            continue

    # 2 КОЛОНКИ (как просил)
    builder.adjust(2)

    builder.row(
        InlineKeyboardButton(text="🗑 Очистить всё", callback_data="ask_clear_teams"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="fav_main")
    )

    return builder.as_markup(), info_text


# --- ХЭНДЛЕРЫ ---

# 1. Исправлено: Добавили обработку текста "Избранное"
@router.message(F.text == "⭐ Избранное")
@router.message(Command("favorites"))
async def cmd_favorites(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Пилоты", callback_data="fav_drivers")],
        [InlineKeyboardButton(text="🏎 Команды", callback_data="fav_teams")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")]
    ])
    await message.answer("⭐ Избранное\nВыбери категорию:", reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "fav_main")
async def cb_fav_main(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Пилоты", callback_data="fav_drivers")],
        [InlineKeyboardButton(text="🏎 Команды", callback_data="fav_teams")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")]
    ])
    await call.message.edit_text("⭐ <b>Избранное</b>\nВыбери категорию:", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "fav_drivers")
async def cb_fav_drivers(call: CallbackQuery):
    markup, text = await _build_drivers_keyboard(call.from_user.id)
    await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data == "fav_teams")
async def cb_fav_teams(call: CallbackQuery):
    markup, text = await _build_teams_keyboard(call.from_user.id)
    await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data.startswith("toggle_driver_"))
async def cb_toggle_driver(call: CallbackQuery):
    code = call.data.replace("toggle_driver_", "")
    user_id = call.from_user.id

    current_favs = await get_favorite_drivers(user_id)
    if code in current_favs:
        await remove_favorite_driver(user_id, code)
    else:
        await add_favorite_driver(user_id, code)

    markup, text = await _build_drivers_keyboard(user_id)
    try:
        await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")
    except:
        pass


@router.callback_query(F.data.startswith("toggle_team_"))
async def cb_toggle_team(call: CallbackQuery):
    team_name = call.data.replace("toggle_team_", "")
    user_id = call.from_user.id

    current_favs = await get_favorite_teams(user_id)
    if team_name in current_favs:
        await remove_favorite_team(user_id, team_name)
    else:
        await add_favorite_team(user_id, team_name)

    markup, text = await _build_teams_keyboard(user_id)
    try:
        await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")
    except:
        pass


# --- ЛОГИКА ОЧИСТКИ С ПОДТВЕРЖДЕНИЕМ ---

# 1. Спрашиваем про пилотов
@router.callback_query(F.data == "ask_clear_drivers")
async def ask_clear_drivers(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_clear_drivers", style="danger"),
            InlineKeyboardButton(text="❌ Нет, назад", callback_data="fav_drivers")
        ]
    ])
    await call.message.edit_text("❓ <b>Вы уверены?</b>\nЭто удалит всех пилотов из вашего списка избранного.",
                                 reply_markup=kb, parse_mode="HTML")


# 2. Подтверждаем и удаляем пилотов
@router.callback_query(F.data == "confirm_clear_drivers")
async def confirm_clear_drivers(call: CallbackQuery):
    user_id = call.from_user.id
    current_favs = await get_favorite_drivers(user_id)
    for code in current_favs:
        await remove_favorite_driver(user_id, code)

    markup, text = await _build_drivers_keyboard(user_id)
    await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")
    await call.answer("Список пилотов очищен")


# 3. Спрашиваем про команды
@router.callback_query(F.data == "ask_clear_teams")
async def ask_clear_teams(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_clear_teams", style="danger"),
            InlineKeyboardButton(text="❌ Нет, назад", callback_data="fav_teams")
        ]
    ])
    await call.message.edit_text("❓ <b>Вы уверены?</b>\nЭто удалит все команды из вашего списка избранного.",
                                 reply_markup=kb, parse_mode="HTML")


# 4. Подтверждаем и удаляем команды
@router.callback_query(F.data == "confirm_clear_teams")
async def confirm_clear_teams(call: CallbackQuery):
    user_id = call.from_user.id
    current_favs = await get_favorite_teams(user_id)
    for team in current_favs:
        await remove_favorite_team(user_id, team)

    markup, text = await _build_teams_keyboard(user_id)
    await call.message.edit_text(text=text, reply_markup=markup, parse_mode="Markdown")
    await call.answer("Список команд очищен")


@router.callback_query(F.data == "close_menu")
async def cb_close_menu(call: CallbackQuery):
    await call.message.delete()
