"""Deletable loading messages, with cancellation scoped to the requesting chat.

Draft previews cannot be explicitly deleted and may outlive rich/photo results.
Use a regular message so every exit can remove the loading UI deterministically.
"""
import asyncio
import secrets
from contextlib import suppress

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

_active_statuses = {}


def stop_activity(bot_id: int, callback: CallbackQuery) -> bool:
    message = callback.message
    if (not isinstance(message, Message) or message.chat.type != "private"
            or callback.from_user.is_bot or callback.from_user.id != message.chat.id):
        return False
    data = callback.data or ""
    if not data.startswith("activity:stop:"):
        return False
    token = data.removeprefix("activity:stop:")
    loader = _active_statuses.get((bot_id, message.chat.id, message.message_thread_id, token))
    if (not loader or loader.closed or loader.stopped or not loader.status
            or loader.status.message_id != message.message_id or loader.work.done()):
        return False
    loader.stopped = True
    loader.work.cancel()
    return True


class ActivityStatus:
    def __init__(self, message: Message, text: str, *, parse_mode=None):
        self.message = message
        self.text = text
        self.status: Message | None = None
        self.task: asyncio.Task | None = None
        self.parse_mode = parse_mode
        self.stopped = False
        self.closed = False
        self.token = secrets.token_hex(8)
        self.keyboard = None
        self.key = None
        self.work = None

    async def __aenter__(self):
        self.work = asyncio.current_task()
        if isinstance(self.message, Message) and self.message.chat.type == "private":
            self.keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Остановить загрузку", callback_data=f"activity:stop:{self.token}")
            ]])
        # A cosmetic loading failure must not prevent delivery of the actual answer.
        with suppress(Exception):
            self.status = await self.message.answer(self._status_text(self.text),
                reply_markup=self.keyboard, parse_mode=self.parse_mode,
                disable_notification=True, request_timeout=5)
        if self.status:
            if self.keyboard:
                self.key = (self.message.bot.id, self.message.chat.id, self.message.message_thread_id, self.token)
                _active_statuses[self.key] = self
            self.task = asyncio.create_task(self._keep_waiting())
        return self

    @staticmethod
    def _status_text(text):
        return text if text.startswith("⏳") else f"⏳ {text}"

    async def update(self, text):
        if self.closed or not self.status:
            return
        self.text = text
        with suppress(Exception):
            await self.status.edit_text(self._status_text(text), parse_mode=self.parse_mode,
                                        reply_markup=self.keyboard, request_timeout=5)

    async def _keep_waiting(self):
        # No draft/typing heartbeat can reappear after the result has been sent.
        await asyncio.sleep(16)
        await self.update(self.text + "\nЗагрузка ещё продолжается. Повторять запрос не нужно.")

    async def __aexit__(self, exc_type, *_):
        self.closed = True
        if self.key:
            _active_statuses.pop(self.key, None)
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        if self.status:
            try:
                await self.status.delete(request_timeout=5)
            except Exception:
                # If deletion is rejected, at least retire the loading label/button.
                text = "Поиск остановлен." if self.stopped else (
                    "Загрузка не завершена. Попробуйте ещё раз." if exc_type else "Загрузка завершена.")
                with suppress(Exception):
                    await self.status.edit_text(text, reply_markup=None, parse_mode=None, request_timeout=5)
        if self.stopped and exc_type is asyncio.CancelledError:
            with suppress(Exception):
                await self.message.answer("Поиск остановлен. Можно выбрать другой раздел.")
            # Let cancellation unwind callers too: post-loader code must not run.
