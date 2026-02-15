import logging

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Ваш ID (можно вынести в config.py, но пока оставим здесь для простоты)
# TODO убрать все открытые данные админов
ADMIN_ID = 2099386

router = Router()
logger = logging.getLogger(__name__)


# --- Состояния FSM ---
class FeedbackState(StatesGroup):
    waiting_for_message = State()


# --- 1. Вход в режим обратной связи ---
@router.message(F.text == "📩 Связь с админом")
async def cmd_feedback(message: Message, state: FSMContext):
    await state.clear()  # Сбрасываем старые состояния, если были

    # Кнопка отмены (inline)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_feedback")]
    ])

    await message.answer(
        "✍️ <b>Напишите ваше сообщение, вопрос или предложение.</b>\n\n"
        "Вы можете прикрепить <b>фото</b> или <b>видео</b>.\n"
        "Я перешлю это администратору.",
        reply_markup=cancel_kb
    )
    await state.set_state(FeedbackState.waiting_for_message)


# --- 2. Обработка кнопки "Отмена" ---
@router.callback_query(F.data == "cancel_feedback")
async def cancel_feedback(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text("🚫 Отправка сообщения отменена.")
    await callback.answer()


# --- 3. Получение сообщения и отправка админу ---
@router.message(FeedbackState.waiting_for_message)
async def process_feedback_message(message: Message, state: FSMContext, bot: Bot):
    # Проверяем, что это поддерживаемый тип контента
    if not (message.text or message.photo or message.video or message.caption):
        await message.answer("Пожалуйста, отправьте текст, фото или видео.")
        return

    try:
        # Формируем информацию о пользователе
        user_info = (
            f"📨 <b>Новое сообщение от пользователя!</b>\n"
            f"👤 Имя: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username if message.from_user.username else 'Нет'}"
        )

        # 1. Сначала отправляем админу "карточку" пользователя
        await bot.send_message(chat_id=ADMIN_ID, text=user_info)

        # 2. Затем используем send_copy (копируем сообщение пользователя админу)
        # send_copy работает и для фото, и для видео, и для текста, сохраняя подписи
        await message.send_copy(chat_id=ADMIN_ID)

        # Подтверждение пользователю
        await message.answer("✅ <b>Ваше сообщение отправлено администратору!</b>\nСпасибо за обратную связь.")

    except Exception as e:
        logger.error(f"Failed to send feedback: {e}")
        await message.answer("❌ Произошла ошибка при отправке. Попробуйте позже.")

    finally:
        # Выходим из состояния ожидания
        await state.clear()