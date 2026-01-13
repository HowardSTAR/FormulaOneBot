# app/handlers/start.py

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

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
            # ДОБАВЛЕНО: Кнопка для открытия Mini App
            [
                KeyboardButton(
                    text="📱 Открыть приложение",
                    web_app=WebAppInfo(url="https://howardstar.github.io/FormulaOneBot/web/app/index.html")
                    # Укажи здесь HTTPS ссылку на твой сервер (ngrok или хостинг)
                )
            ]
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
        f"Я — FormulaOneBot, твой карманный паддок Формулы‑1 🏎🔥\n\n"
        f"Теперь у меня есть удобное мини-приложение! Нажми кнопку ниже, чтобы попробовать.\n"
    )
    await safe_answer(message, text, reply_markup=get_main_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())