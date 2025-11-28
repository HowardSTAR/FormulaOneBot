from aiogram import Router, F
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
            [KeyboardButton(
                text="📲 Открыть MiniApp",
                url="https://kidney-papers-container-comfort.trycloudflare.com/web/app/index.html"
            )],
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
        f"Я умею:\n"
        f"• показывать ближайшую гонку и расписание всего уикенда;\n"
        f"• выводить календарь сезона для любого года;\n"
        f"• показывать личный зачёт пилотов и кубок конструкторов;\n"
        f"• отправлять картинку с результатами последней гонки;\n"
        f"• отслеживать твоих любимых пилотов и команды и присылать уведомления после квалификации и гонки.\n\n"
        f"Используй кнопки ниже:\n"
        f"• «Ближайшая гонка» — следующая гонка и время старта\n"
        f"• «Сезон» — календарь выбранного года\n"
        f"• «Личный зачет» — таблица пилотов\n"
        f"• «Кубок конструкторов» — таблица команд\n"
        f"• «Избранное» — настройка любимых пилотов и команд\n\n"
    )
    await safe_answer(message, text, reply_markup=get_main_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())



@router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    try:
        raw = message.web_app_data.data  # строка
        # например {"type": "miniapp_test", "ts": 123456}
        import json
        data = json.loads(raw)
    except Exception:
        await message.answer("Получил данные из MiniApp, но не смог их разобрать 🤯")
        return

    if data.get("type") == "miniapp_test":
        await message.answer("✅ MiniApp жив! Данные дошли до бота.")
    else:
        await message.answer(f"Получил что-то из MiniApp: <code>{raw}</code>", parse_mode="HTML")