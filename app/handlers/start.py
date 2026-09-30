from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext

from app.db import get_or_create_user
from app.handlers.settings import _show_main_settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
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

    # Создаем кнопки главного меню (обычные текстовые кнопки внизу)
    kb = [
        [KeyboardButton(text="📈 История сезонов"), KeyboardButton(text="📰 Рекап гонки")],
        [KeyboardButton(text="🏎 Справка о пилоте")],
        [KeyboardButton(text="🤝 С друзьями")],
        [
            KeyboardButton(text="🏁 Следующая гонка"),
            KeyboardButton(text="📅 Календарь"),
        ],
        [
            KeyboardButton(text="🏆 Кубок конструкторов"),
            KeyboardButton(text="🏎 Личный зачет"),
            KeyboardButton(text="⚔️ Сравнение"),
        ],
        [
            KeyboardButton(text="⭐ Избранное"),
            KeyboardButton(text="⚙️ Настройки"),
            KeyboardButton(text="📩 Связь с админом")
        ],
    ]

    keyboard = ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите пункт меню"
    )

    welcome_text = (
        "🏎 **Добро пожаловать в TurboTears!**\n\n"
        "Я твой персональный паддок в Telegram. Здесь есть всё для фаната F1:\n\n"
        "🏁 **Календарь и Гонки**\n"
        "Расписание этапов, время старта и обратный отсчет до зеленых огней.\n\n"
        "📊 **Статистика**\n"
        "Актуальный Личный зачет и Кубок конструкторов.\n\n"
        "⚔️ **Сравнение пилотов**\n"
        "Строим красивые графики противостояния любых гонщиков по очкам.\n\n"
        "⭐ **Избранное и Уведомления**\n"
        "Подпишись на любимых пилотов, и я пришлю их результаты после финиша. "
        "Настрой время напоминания перед гонкой (за 10 мин, за час или за сутки)!\n\n"
        "👇 **Жми на кнопки меню ниже!**"
    )

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    # Сразу показываем настройки уведомлений, чтобы пользователь мог настроить напоминания
    await _show_main_settings(message, state, message.from_user.id, is_edit=False)


@router.message(F.text == '🤝 С друзьями')
async def community_button(message: Message):
    from app.utils.mini_app_links import mini_app_button
    keyboard = await mini_app_button(message.bot, 'Открыть соревнования и приглашения', '/community')
    await message.answer('Пригласите друзей в лигу, предложите побить ваше время или участвуйте в трассе недели. Достижения не добавляют очков в прогнозах.', reply_markup=keyboard)
