# app/handlers/secret.py
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.utils.default import OWNER_TELEGRAM_ID
from app.utils.notifications import build_latest_race_favorites_text_for_user

router = Router()

# сюда ставим твой настоящий telegram_id


@router.message(Command("secret_results"))
async def secret_results_cmd(message: Message) -> None:
    """
    Секретная команда: прислать ещё раз текст результатов
    последней гонки для избранных пилотов/команд.
    Работает только для одного telegram_id.
    """
    if message.from_user.id != OWNER_TELEGRAM_ID:
        # делаем вид, что команды вообще нет
        logging.info(
            "[SECRET] Пользователь %s попытался вызвать секретную команду",
            message.from_user.id,
        )
        return

    text = await build_latest_race_favorites_text_for_user(message.from_user.id)

    if not text:
        await message.answer(
            "Пока нет данных по последней гонке для повторного вывода 🤔"
        )
        return

    await message.answer(text)


# Вариант 2 (ещё более секретный): длинная текстовая команда,
# НЕ slash-команда, а простое сообщение.
@router.message(F.text == "Покажи_мне_секретные_результаты_гонки_2025")
async def secret_results_phrase(message: Message) -> None:
    if message.from_user.id != OWNER_TELEGRAM_ID:
        return

    text = await build_latest_race_favorites_text_for_user(message.from_user.id)
    if not text:
        await message.answer(
            "Пока нет данных по последней гонке для повторного вывода 🤔"
        )
        return

    await message.answer(text)