from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_name = message.from_user.full_name
    text = (
        f"Привет, {user_name}! 👋\n\n"
        f"Я бот для отслеживания Формулы 1.\n"
        f"Пока я только запускаюсь, но скоро здесь появятся:\n"
        f"• Список гонок текущего сезона\n"
        f"• Таблица пилотов и конструкторов\n"
        f"• Уведомления перед гонкой и результаты для любимых пилотов\n\n"
        f"Начнём с базового функционала, а потом будем прокачивать 🚀"
    )
    await message.answer(text)