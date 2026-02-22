from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import get_user_settings, update_user_setting, db

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
    """Умное форматирование минут в часы и минуты с правильным склонением."""
    if not minutes:
        return "Отключены"

    if minutes < 60:
        return f"{minutes} мин."

    hours = minutes // 60
    mins = minutes % 60

    # Магия склонения для русского языка
    if hours % 10 == 1 and hours % 100 != 11:
        h_str = "час"
    elif 2 <= hours % 10 <= 4 and not (12 <= hours % 100 <= 14):
        h_str = "часа"
    else:
        h_str = "часов"

    if mins == 0:
        return f"{hours} {h_str}"
    else:
        return f"{hours} {h_str} {mins} мин."


def get_settings_keyboard(current_tz: str, current_notify: int, back_callback: str = "close_settings",
                          notifications_enabled=None):
    builder = InlineKeyboardBuilder()

    tz_label = current_tz
    for label, code in UTC_ZONES.items():
        if code == current_tz:
            tz_label = label
            break

    notify_str = format_notify_time(current_notify)

    status_emoji = "🟢 Вкл" if notifications_enabled else "🔴 Выкл"

    builder.button(text=f"🌍 Пояс: {tz_label}", callback_data="change_tz")
    builder.button(text=f"⏰ Уведомлять за: {notify_str}", callback_data="change_notify")
    builder.row(
        types.InlineKeyboardButton(
            text=f"🔔 Уведомления: {status_emoji}",
            callback_data="toggle_notifications"
        )
    )
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

async def _show_main_settings(event: Message | CallbackQuery, state: FSMContext, user_id: int, is_edit: bool = False):
    """Показывает главное меню."""
    user_settings = await get_user_settings(user_id)

    data = await state.get_data()
    back_target = data.get("back_target", "close_settings")

    await state.update_data(settings=user_settings)

    notify_display = format_notify_time(user_settings.get('notify_before', 60))
    current_tz = user_settings.get('timezone', 'Europe/Moscow')

    # Получаем актуальный статус из БД
    is_enabled = await db.get_notification_status(user_id)

    # Формируем чистый текст меню
    text = (
        "⚙️ <b>Настройки TurbotearsBot</b>\n\n"
        f"🌍 Часовой пояс: {current_tz}\n"
        f"🔔 Уведомлять за: {notify_display}\n\n"
        "Выбери, что хочешь изменить:"
    )

    # Создаем клавиатуру
    markup = get_settings_keyboard(
        current_tz,
        user_settings.get('notify_before', 60),
        back_callback=back_target,
        notifications_enabled=is_enabled
    )

    # УМНАЯ ОТПРАВКА: определяем, что именно нам передали (сообщение или нажатие кнопки)
    target_message = event.message if isinstance(event, CallbackQuery) else event

    if is_edit:
        try:
            # Пытаемся обновить сообщение
            await target_message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as e:
            # Если Telegram ругается, что ничего не изменилось — просто элегантно игнорируем это
            if "message is not modified" not in str(e):
                raise  # А вот если ошибка в чем-то другом (например, HTML-теги сломались), то выбрасываем её
    else:
        await target_message.answer(text, reply_markup=markup, parse_mode="HTML")

    await state.set_state(SettingsSG.main_menu)

@settings_router.callback_query(F.data == "toggle_notifications")
async def on_toggle_notifications(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id

    current_status = await db.get_notification_status(user_id)
    new_status = not current_status
    await db.toggle_notifications(user_id, new_status)

    action = "ВКЛЮЧЕНЫ" if new_status else "ВЫКЛЮЧЕНЫ"
    await call.answer(f"Уведомления {action}!", show_alert=False)

    # Передаем call первым аргументом, и просим отредактировать меню (is_edit=True)
    await _show_main_settings(call, state, user_id, is_edit=True)


@settings_router.message(Command("settings"))
@settings_router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message, state: FSMContext):
    # Передаем message первым аргументом
    await _show_main_settings(message, state, message.from_user.id, is_edit=False)


@settings_router.callback_query(F.data == "cmd_settings")
async def cb_open_settings(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(back_target="close_settings")
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer()


@settings_router.callback_query(F.data.startswith("settings_race_"))
async def cb_settings_from_race(callback: types.CallbackQuery, state: FSMContext):
    try:
        season = callback.data.split("_")[-1]
    except:
        season = "None"

    await state.update_data(back_target=f"back_to_race_{season}")
    await _show_main_settings(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer()


@settings_router.callback_query(F.data == "change_tz", SettingsSG.main_menu)
async def cb_change_tz(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_tz = data.get("settings", {}).get("timezone", "UTC")
    await callback.message.edit_text(
        "🌍 Выберите ваш часовой пояс (UTC):\n"
        "Москва = UTC+3.",
        reply_markup=get_timezone_keyboard(current_tz),
        parse_mode="HTML"
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

    # ИСПРАВЛЕНО: Убраны круглые скобки и запятая, из-за которых ломался текст
    text = "⏰ <b>За сколько времени предупреждать о гонке?</b>"

    await callback.message.edit_text(
        text,
        reply_markup=get_notify_keyboard(current_not),
        parse_mode="HTML"
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