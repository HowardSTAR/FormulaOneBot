from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import get_user_settings, update_user_setting

settings_router = Router()


class SettingsSG(StatesGroup):
    main_menu = State()
    choosing_timezone = State()
    choosing_notify = State()


# --- ГЕНЕРАЦИЯ СПИСКА ЧАСОВЫХ ПОЯСОВ (UTC) ---
UTC_ZONES = {}
for i in range(-11, 13):
    if i == 0:
        label = "UTC (GMT)"
        tz_key = "UTC"
    else:
        user_sign = "+" if i > 0 else "-"
        label = f"UTC{user_sign}{abs(i)}"
        sys_sign = "-" if i > 0 else "+"
        tz_key = f"Etc/GMT{sys_sign}{abs(i)}"
    UTC_ZONES[label] = tz_key

NOTIFY_OPTIONS = {
    "15 минут": 15,
    "30 минут": 30,
    "1 час": 60,
    "2 часа": 120,
    "24 часа": 1440
}


# --- КЛАВИАТУРЫ ---

# 👇 ДОБАВЛЕН АРГУМЕНТ back_callback
def get_settings_keyboard(current_tz: str, current_notify: int, back_callback: str = "close_settings"):
    builder = InlineKeyboardBuilder()

    tz_label = current_tz
    for label, code in UTC_ZONES.items():
        if code == current_tz:
            tz_label = label
            break

    builder.button(text=f"🌍 Пояс: {tz_label}", callback_data="change_tz")
    builder.button(text=f"⏰ Уведомлять за: {current_notify} мин", callback_data="change_notify")
    # 👇 ТЕПЕРЬ КНОПКА ВЕДЕТ ТУДА, КУДА МЫ СКАЖЕМ
    builder.button(text="🔙 Вернуться", callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def get_timezone_keyboard(current_tz_code: str):
    builder = InlineKeyboardBuilder()
    for label, tz_key in UTC_ZONES.items():
        text = f"✅ {label}" if tz_key == current_tz_code else label
        builder.button(text=text, callback_data=f"set_tz:{tz_key}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(3)
    return builder.as_markup()


def get_notify_keyboard(current_val: int):
    builder = InlineKeyboardBuilder()
    for label, minutes in NOTIFY_OPTIONS.items():
        text = f"✅ {label}" if minutes == current_val else label
        builder.button(text=text, callback_data=f"set_not:{minutes}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(2)
    return builder.as_markup()


# --- ХЕНДЛЕРЫ ---

async def _show_main_settings(message: types.Message, state: FSMContext, user_id: int, is_edit: bool = False):
    """Показывает главное меню."""
    user_settings = await get_user_settings(user_id)

    # 👇 ДОСТАЕМ ИЗ ПАМЯТИ, КУДА ВОЗВРАЩАТЬСЯ (по умолчанию close_settings)
    data = await state.get_data()
    back_target = data.get("back_target", "close_settings")

    await state.update_data(settings=user_settings)

    text = (
        "⚙️ **Настройки TurbotearsBot**\n\n"
        "Настройте часовой пояс (UTC) и время уведомлений."
    )
    # Передаем цель возврата в клавиатуру
    markup = get_settings_keyboard(
        user_settings['timezone'],
        user_settings['notify_before'],
        back_callback=back_target
    )

    if is_edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="Markdown")

    await state.set_state(SettingsSG.main_menu)


# 1. Открытие командой /settings (возврат = закрыть)
@settings_router.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    await state.update_data(back_target="close_settings")
    await _show_main_settings(message, state, message.from_user.id, is_edit=False)


# 2. Открытие обычной кнопкой (возврат = закрыть)
@settings_router.callback_query(F.data == "cmd_settings")
async def cb_open_settings(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(back_target="close_settings")
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer()


# 3. 👇 НОВЫЙ ХЕНДЛЕР: Открытие из карточки гонки
@settings_router.callback_query(F.data.startswith("settings_race_"))
async def cb_settings_from_race(callback: types.CallbackQuery, state: FSMContext):
    # Извлекаем сезон, чтобы вернуться именно к нему
    # формат: settings_race_{season}
    try:
        season = callback.data.split("_")[-1]
    except:
        season = "None"

    # Запоминаем, что кнопка "Вернуться" должна вести на back_to_race_{season}
    # Этот callback обрабатывается в races.py
    await state.update_data(back_target=f"back_to_race_{season}")

    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer()


# --- Смена настроек (логика остается прежней) ---

@settings_router.callback_query(F.data == "change_tz", SettingsSG.main_menu)
async def cb_change_tz(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_tz = data.get("settings", {}).get("timezone", "UTC")
    await callback.message.edit_text(
        "🌍 **Выберите ваш часовой пояс (UTC):**\n"
        "Москва = UTC+3.",
        reply_markup=get_timezone_keyboard(current_tz),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.choosing_timezone)


@settings_router.callback_query(F.data.startswith("set_tz:"), SettingsSG.choosing_timezone)
async def cb_set_timezone(callback: types.CallbackQuery, state: FSMContext):
    new_tz = callback.data.split(":")[1]
    await update_user_setting(callback.from_user.id, "timezone", new_tz)
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "change_notify", SettingsSG.main_menu)
async def cb_change_notify(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_not = data.get("settings", {}).get("notify_before", 60)
    await callback.message.edit_text(
        "⏰ **За сколько времени предупреждать о гонке?**",
        reply_markup=get_notify_keyboard(current_not),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.choosing_notify)


@settings_router.callback_query(F.data.startswith("set_not:"), SettingsSG.choosing_notify)
async def cb_set_notify(callback: types.CallbackQuery, state: FSMContext):
    minutes = int(callback.data.split(":")[1])
    await update_user_setting(callback.from_user.id, "notify_before", minutes)
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "back_to_settings")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "close_settings")
async def cb_close(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()