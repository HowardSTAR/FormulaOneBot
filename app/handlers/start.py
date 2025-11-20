from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command

from app.utils.safe_send import safe_answer

router = Router()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Ближайшая гонка"),
            ],
            [
                KeyboardButton(text="Сезон"),
                KeyboardButton(text="Личный зачет"),
            ],
            [
                KeyboardButton(text="Кубок конструкторов"),
                KeyboardButton(text="Избранное"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    return keyboard

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_name = message.from_user.full_name
    text = (
        f"Привет, {user_name}! 👋\n\n"
        f"Я бот для отслеживания Формулы 1.\n\n"
        f"📌 Доступно сейчас:\n"
        f"• Кнопка «Ближайшая гонка» — показывает ближайшую гонку.\n\n"
        f"• Кнопка «Сезон» — календарь гонок выбранного года\n"
        f"• Кнопка «Личный» зачет — таблица пилотов\n"
        f"• Кнопка «Кубок конструкторов» — таблица команд\n\n"
        f"• Кнопка «Избранное» — отслеживание любимых пилотов и команд.\n\n"
        f"Также клавиатуру ниже или можно использовать команды :\n"
        f"• /races — календарь сезона\n"
        f"• /drivers — личный зачет\n"
        f"• /teams — кубок конструкторов\n"
    )
    await safe_answer(message, text, reply_markup=get_main_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())
