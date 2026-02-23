from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
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


def format_notify_time(minutes: int) -> str:
    """Умное форматирование минут в часы и минуты"""
    if minutes < 60:
        return f"{minutes} минут"
    elif minutes == 60:
        return "1 час"
    elif minutes == 120:
        return "2 часа"
    elif minutes == 1440:
        return "24 часа"
    return f"{minutes} мин."


async def _show_main_settings(message_or_callback, state: FSMContext, user_id: int, is_edit: bool = False):
    """Отрисовка главного меню настроек"""
    # 1. Получаем настройки пользователя по telegram_id
    user_settings = await get_user_settings(user_id)

    tz = user_settings.get("timezone", "Europe/Moscow")
    notify_before = user_settings.get("notify_before", 60)
    notifications_enabled = user_settings.get("notifications_enabled", False)

    # 2. Форматируем часовой пояс
    tz_label = "Неизвестно"
    for label, val in UTC_ZONES.items():
        if val == tz:
            tz_label = label
            break
    if tz == "Europe/Moscow":
        tz_label = "UTC+3 (Москва)"

    # 3. Форматируем время
    notify_str = format_notify_time(notify_before)

    # 4. Форматируем статус уведомлений
    notif_status = "🟢 Вкл" if notifications_enabled else "🔴 Выкл"

    text = (
        "⚙️ <b>Настройки F1 Hub</b>\n\n"
        f"🌍 <b>Часовой пояс:</b> {tz_label}\n"
        f"⏰ <b>Напоминать за:</b> {notify_str} до гонки\n"
        f"🔔 <b>Статус уведомлений:</b> {notif_status}\n\n"
        "<i>Выбери параметр для изменения:</i>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔔 Уведомления: {notif_status}", callback_data="toggle_notifications")
    kb.button(text=f"⏰ Напоминать за ({notify_str})", callback_data="change_notify")
    kb.button(text=f"🌍 Часовой пояс ({tz_label})", callback_data="change_tz")
    kb.button(text="❌ Закрыть", callback_data="close_settings")
    kb.adjust(1)  # Кнопки в один столбец

    await state.update_data(settings=user_settings)

    if isinstance(message_or_callback, types.CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except TelegramBadRequest:
            pass  # Игнорируем ошибку, если текст не изменился (пользователь спамит по кнопке)
    else:
        await message_or_callback.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

    await state.set_state(SettingsSG.main_menu)


def get_tz_keyboard():
    kb = InlineKeyboardBuilder()
    for label, tz_key in UTC_ZONES.items():
        kb.button(text=label, callback_data=f"set_tz:{tz_key}")
    kb.button(text="МСК (Europe/Moscow)", callback_data="set_tz:Europe/Moscow")
    kb.button(text="« Назад", callback_data="back_to_settings")
    kb.adjust(2)
    return kb.as_markup()


def get_notify_keyboard(current_val: int):
    kb = InlineKeyboardBuilder()
    for label, val in NOTIFY_OPTIONS.items():
        mark = "✅ " if val == current_val else ""
        kb.button(text=f"{mark}{label}", callback_data=f"set_not:{val}")
    kb.button(text="« Назад", callback_data="back_to_settings")
    kb.adjust(2)
    return kb.as_markup()


@settings_router.message(F.text == "⚙️ Настройки")
@settings_router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    await _show_main_settings(message, state, message.from_user.id, is_edit=False)


# --- НОВЫЙ ХЕНДЛЕР: Переключение тумблера уведомлений ---
@settings_router.callback_query(F.data == "toggle_notifications", SettingsSG.main_menu)
async def cb_toggle_notifications(callback: types.CallbackQuery, state: FSMContext):
    # Получаем текущий статус
    user_settings = await get_user_settings(callback.from_user.id)
    current_status = user_settings.get("notifications_enabled", False)

    # Меняем статус на противоположный (True на False, False на True)
    new_status = not current_status

    # Сохраняем в БД (передаем как int: 1 или 0)
    await update_user_setting(callback.from_user.id, "notifications_enabled", int(new_status))

    # Перерисовываем меню, чтобы лампочка сменилась с 🔴 на 🟢
    await _show_main_settings(callback, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "change_tz", SettingsSG.main_menu)
async def cb_change_tz(callback: types.CallbackQuery, state: FSMContext):
    text = "🌍 <b>Выбери свой часовой пояс:</b>\n<i>Это нужно, чтобы расписание гонок отображалось корректно.</i>"
    await callback.message.edit_text(text, reply_markup=get_tz_keyboard(), parse_mode="HTML")
    await state.set_state(SettingsSG.choosing_timezone)


@settings_router.callback_query(F.data.startswith("set_tz:"), SettingsSG.choosing_timezone)
async def cb_set_tz(callback: types.CallbackQuery, state: FSMContext):
    new_tz = callback.data.split(":", 1)[1]
    await update_user_setting(callback.from_user.id, "timezone", new_tz)
    await _show_main_settings(callback, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "change_notify", SettingsSG.main_menu)
async def cb_change_notify(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_not = data.get("settings", {}).get("notify_before", 60)

    text = "⏰ <b>За сколько времени предупреждать о гонке?</b>"
    await callback.message.edit_text(text, reply_markup=get_notify_keyboard(current_not), parse_mode="HTML")
    await state.set_state(SettingsSG.choosing_notify)


@settings_router.callback_query(F.data.startswith("set_not:"), SettingsSG.choosing_notify)
async def cb_set_notify(callback: types.CallbackQuery, state: FSMContext):
    minutes = int(callback.data.split(":")[1])
    await update_user_setting(callback.from_user.id, "notify_before", minutes)
    await _show_main_settings(callback, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "back_to_settings")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    await _show_main_settings(callback, state, callback.from_user.id, is_edit=True)


@settings_router.callback_query(F.data == "close_settings")
async def cb_close(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()