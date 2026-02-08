from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Создаем кнопки главного меню (обычные текстовые кнопки внизу)
    kb = [
        [
            KeyboardButton(text="📅 Календарь"),
            KeyboardButton(text="🏎 Личный зачет")
        ],
        [
            KeyboardButton(text="🏆 Кубок конструкторов"),
            KeyboardButton(text="🏁 Следующая гонка")
        ],
        [
            KeyboardButton(text="⚔️ Сравнение"),
            KeyboardButton(text="⭐ Избранное"),
            KeyboardButton(text="⚙️ Настройки"),
        ]
    ]

    keyboard = ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите пункт меню"
    )

    welcome_text = (
        "🏎 **Добро пожаловать в FormulaOne Hub!**\n\n"
        "Я твой персональный паддок в Telegram. Здесь всё, что нужно фанату «Королевских гонок»:\n\n"
        "• 🏁 **Ближайшая гонка**: расписание и обратный отсчет;\n\n"
        "• 📊 **Результаты**: актуальные таблицы и зачеты;\n\n"
        "• 📅 **Календарь**: все этапы сезона в твоем кармане;\n\n"
        "• ⭐ **Избранное**: персонализированные уведомления.\n\n"
        "**Жми на синюю кнопку «Hub»** для входа в Mini App или выбирай раздел в меню ниже!"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )