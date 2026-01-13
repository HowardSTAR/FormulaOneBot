import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

# Импортируем конфиг
from app.config import get_settings
from app.utils.notifications import build_latest_race_favorites_text_for_user

router = Router()


@router.message(Command("secret_results"))
async def secret_results_cmd(message: Message) -> None:
    settings = get_settings()

    # Проверяем, есть ли ID отправителя в списке админов
    if message.from_user.id not in settings.admin_ids:
        logging.info(f"[SECRET] Несанкционированный доступ: {message.from_user.id}")
        return

    text = await build_latest_race_favorites_text_for_user(message.from_user.id)
    if not text:
        await message.answer("Нет данных или избранного.")
        return
    await message.answer(text)


# То же самое для второй команды
@router.message(F.text == "Покажи_мне_секретные_результаты_гонки_2025")
async def secret_results_phrase(message: Message) -> None:
    settings = get_settings()
    if message.from_user.id not in settings.admin_ids:
        return

    text = await build_latest_race_favorites_text_for_user(message.from_user.id)
    if text:
        await message.answer(text)