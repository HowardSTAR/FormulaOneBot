import asyncio

from aiogram.exceptions import TelegramBadRequest

from app.bot import create_bot_and_dispatcher
from app.handlers.start import router as start_router
from app.handlers.drivers import router as drivers_router
from app.handlers.teams import router as teams_router
from app.handlers.races import router as races_router



async def main() -> None:
    bot, dp = create_bot_and_dispatcher()

    # Регистрируем все роутеры
    dp.include_router(start_router)
    dp.include_router(races_router)
    dp.include_router(drivers_router)
    dp.include_router(teams_router)

    try:
        await dp.start_polling(bot)
    except TelegramBadRequest as exc:
        print(f"Ошибка Telegram API: {exc}")
    except KeyboardInterrupt:
        print("Остановка бота пользователем")

if __name__ == "__main__":
    asyncio.run(main())