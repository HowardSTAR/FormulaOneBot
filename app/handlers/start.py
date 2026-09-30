from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.db import get_or_create_user
from app.utils.bot_menu import main_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("В группе используйте /f1. Полное меню F1Hub доступно в личном чате с ботом.")
        return
    await state.clear()
    user_id = await get_or_create_user(message.from_user.id)
    argument = (getattr(message, 'text', None) or '').partition(' ')[2].strip()
    if argument.startswith('share_'):
        from app.services.engagement import arrival, public_share
        from app.utils.mini_app_links import mini_app_button
        token = argument[6:]
        try:
            card = await public_share(token)
            await arrival(user_id, token)
            keyboard = await mini_app_button(message.bot, card['cta'], f'/share/{token}')
            await message.answer(f"{card['title']}\n{card['headline']}\n\nОткройте карточку и выберите, участвовать ли.", reply_markup=keyboard, parse_mode=None)
        except ValueError:
            await message.answer('Приглашение истекло или отозвано. Откройте F1Hub, чтобы начать своё соревнование.')
        return

    welcome_text = (
        "🏁 <b>Добро пожаловать в F1Hub!</b>\n\n"
        "<b>Уик-энд</b> — расписание и рекап.\n"
        "<b>Прогнозы</b> — ваш выбор, очки и лиги.\n"
        "<b>Разделы</b> — статистика, история, пилоты и игры.\n"
        "<b>Моё</b> — избранное, настройки и обратная связь.\n\n"
        "Выберите кнопку внизу."
    )

    await message.answer(
        welcome_text,
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == '🤝 С друзьями')
async def community_button(message: Message):
    from app.utils.mini_app_links import mini_app_button
    keyboard = await mini_app_button(message.bot, 'Открыть соревнования и приглашения', '/community')
    await message.answer('Пригласите друзей в лигу, предложите побить ваше время или участвуйте в трассе недели. Достижения не добавляют очков в прогнозах.', reply_markup=keyboard)
