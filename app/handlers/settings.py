from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
import pytz

# Создаем роутер для настроек
settings_router = Router()


# --- 1. Состояния (FSM) ---
class SettingsSG(StatesGroup):
    main_menu = State()  # Главное меню настроек
    choosing_timezone = State()  # Выбор часового пояса
    choosing_notify = State()  # Выбор времени уведомления


# --- 2. Вспомогательные данные ---

# Список популярных часовых поясов для РФ/СНГ (можно расширить)
COMMON_TIMEZONES = {
    "Kaliningrad (UTC+2)": "Europe/Kaliningrad",
    "Moscow (UTC+3)": "Europe/Moscow",
    "Samara (UTC+4)": "Europe/Samara",
    "Yekaterinburg (UTC+5)": "Asia/Yekaterinburg",
    "Omsk (UTC+6)": "Asia/Omsk",
    "Novosibirsk (UTC+7)": "Asia/Novosibirsk",
    "Irkutsk (UTC+8)": "Asia/Irkutsk",
    "Vladivostok (UTC+10)": "Asia/Vladivostok",
    "Magadan (UTC+11)": "Asia/Magadan",
    "Kamchatka (UTC+12)": "Asia/Kamchatka",
}

# Опции времени уведомления (в минутах)
NOTIFY_OPTIONS = {
    "15 минут": 15,
    "30 минут": 30,
    "1 час": 60,
    "2 часа": 120,
    "24 часа": 1440
}


# --- 3. Клавиатуры ---

def get_settings_keyboard(current_tz: str, current_notify: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🌍 Пояс: {current_tz}", callback_data="change_tz")
    builder.button(text=f"⏰ Уведомлять за: {current_notify} мин", callback_data="change_notify")
    builder.button(text="🔙 Закрыть", callback_data="close_settings")
    builder.adjust(1)
    return builder.as_markup()


def get_timezone_keyboard():
    builder = InlineKeyboardBuilder()
    # Добавляем кнопки поясов
    for label, tz_key in COMMON_TIMEZONES.items():
        builder.button(text=label, callback_data=f"set_tz:{tz_key}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(2)  # По 2 кнопки в ряд
    return builder.as_markup()


def get_notify_keyboard():
    builder = InlineKeyboardBuilder()
    for label, minutes in NOTIFY_OPTIONS.items():
        builder.button(text=label, callback_data=f"set_not:{minutes}")
    builder.button(text="🔙 Назад", callback_data="back_to_settings")
    builder.adjust(2)
    return builder.as_markup()


# --- 4. Хендлеры (Обработчики) ---

@settings_router.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    # TODO: Здесь нужно получить реальные настройки из БД
    # Пока заглушки (mock data)
    user_settings = {"timezone": "Europe/Moscow", "notify_before": 60}

    # Сохраняем во временное хранилище FSM, чтобы не дергать БД лишний раз, если не надо
    await state.update_data(settings=user_settings)

    text = (
        "⚙️ **Настройки TurbotearsBot**\n\n"
        "Здесь вы можете настроить часовой пояс для отображения времени трансляций "
        "и время напоминания перед стартом."
    )

    await message.answer(
        text,
        reply_markup=get_settings_keyboard(user_settings['timezone'], user_settings['notify_before']),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.main_menu)


# Добавляем обработку нажатия на кнопку "Настройки" из других меню
@settings_router.callback_query(F.data == "cmd_settings")
async def cb_open_settings(callback: types.CallbackQuery, state: FSMContext):
    # Вызываем ту же логику, что и при команде /settings
    # Можно просто переиспользовать код cmd_settings, передав туда message
    await cmd_settings(callback.message, state)
    await callback.answer()


# -- Обработка кнопки "Сменить часовой пояс" --
@settings_router.callback_query(F.data == "change_tz", SettingsSG.main_menu)
async def cb_change_tz(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌍 **Выберите ваш часовой пояс:**\n"
        "Время всех сессий будет автоматически сконвертировано.",
        reply_markup=get_timezone_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.choosing_timezone)


# -- Обработка выбора конкретного пояса --
@settings_router.callback_query(F.data.startswith("set_tz:"), SettingsSG.choosing_timezone)
async def cb_set_timezone(callback: types.CallbackQuery, state: FSMContext):
    new_tz = callback.data.split(":")[1]

    # TODO: СОХРАНИТЬ new_tz В БАЗУ ДАННЫХ ДЛЯ ЭТОГО ПОЛЬЗОВАТЕЛЯ
    # db.update_user_timezone(user_id=callback.from_user.id, timezone=new_tz)

    # Обновляем данные в стейте для отображения
    await state.update_data(timezone=new_tz)
    data = await state.get_data()
    # Если notify_before не в корне data, берем из settings (для примера упростим)
    current_notify = data.get('notify_before', 60)

    await callback.message.edit_text(
        f"✅ Часовой пояс изменен на: **{new_tz}**\n\n⚙️ Главное меню:",
        reply_markup=get_settings_keyboard(new_tz, current_notify),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.main_menu)


# -- Обработка кнопки "Время уведомления" --
@settings_router.callback_query(F.data == "change_notify", SettingsSG.main_menu)
async def cb_change_notify(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⏰ **За сколько времени предупреждать о гонке?**",
        reply_markup=get_notify_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.choosing_notify)


# -- Обработка выбора времени --
@settings_router.callback_query(F.data.startswith("set_not:"), SettingsSG.choosing_notify)
async def cb_set_notify(callback: types.CallbackQuery, state: FSMContext):
    minutes = int(callback.data.split(":")[1])

    # TODO: СОХРАНИТЬ minutes В БАЗУ ДАННЫХ
    # db.update_user_notification(user_id=callback.from_user.id, minutes=minutes)

    await state.update_data(notify_before=minutes)
    data = await state.get_data()
    current_tz = data.get('timezone', "Europe/Moscow")  # fallback

    await callback.message.edit_text(
        f"✅ Уведомление установлено за: **{minutes} мин.** до старта.\n\n⚙️ Главное меню:",
        reply_markup=get_settings_keyboard(current_tz, minutes),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.main_menu)


# -- Кнопка Назад --
@settings_router.callback_query(F.data == "back_to_settings")
async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    # Возврат в главное меню настроек
    # Тут желательно снова дернуть актуальные данные (или взять из FSM)
    data = await state.get_data()
    tz = data.get('timezone', 'Europe/Moscow')
    notify = data.get('notify_before', 60)

    await callback.message.edit_text(
        "⚙️ **Настройки TurbotearsBot**",
        reply_markup=get_settings_keyboard(tz, notify),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsSG.main_menu)


# -- Закрытие настроек --
@settings_router.callback_query(F.data == "close_settings")
async def cb_close(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
