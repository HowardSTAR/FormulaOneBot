from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Создаем кнопки главного меню (обычные текстовые кнопки внизу)
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Ближайшая гонка"))
    builder.row(
        types.KeyboardButton(text="Сезон"),
        types.KeyboardButton(text="Личный зачет")
    )
    builder.row(
        types.KeyboardButton(text="Кубок конструкторов"),
        types.KeyboardButton(text="Избранное")
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
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="Markdown"
    )