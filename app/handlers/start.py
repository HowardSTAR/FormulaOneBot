from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext

from app.db import get_or_create_user
from app.handlers.settings import _show_main_settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await get_or_create_user(message.from_user.id)

    # Создаем кнопки главного меню (обычные текстовые кнопки внизу)
    kb = [
        [
            KeyboardButton(text="🏁 Следующая гонка"),
            KeyboardButton(text="📅 Календарь"),
        ],
        [
            KeyboardButton(text="🏆 Кубок конструкторов"),
            KeyboardButton(text="🏎 Личный зачет"),
            KeyboardButton(text="⚔️ Сравнение"),
        ],
        [
            KeyboardButton(text="⭐ Избранное"),
            KeyboardButton(text="⚙️ Настройки"),
            KeyboardButton(text="📩 Связь с админом")
        ],
    ]

    keyboard = ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите пункт меню"
    )

    welcome_text = (
        "🏎 **Добро пожаловать в FormulaOne Hub!**\n\n"
        "Я твой персональный паддок в Telegram. Здесь есть всё для фаната F1:\n\n"
        "🏁 **Календарь и Гонки**\n"
        "Расписание этапов, время старта и обратный отсчет до зеленых огней.\n\n"
        "📊 **Статистика**\n"
        "Актуальный Личный зачет и Кубок конструкторов.\n\n"
        "⚔️ **Сравнение пилотов**\n"
        "Строим красивые графики противостояния любых гонщиков по очкам.\n\n"
        "⭐ **Избранное и Уведомления**\n"
        "Подпишись на любимых пилотов, и я пришлю их результаты после финиша. "
        "Настрой время напоминания перед гонкой (за 10 мин, за час или за сутки)!\n\n"
        "👇 **Жми на кнопки меню ниже!**"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    # Сразу показываем настройки уведомлений, чтобы пользователь мог настроить напоминания
    await _show_main_settings(message, state, message.from_user.id, is_edit=False)