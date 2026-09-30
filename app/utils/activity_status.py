"""Visible activity, without invented progress percentages or completion times."""
import asyncio
import secrets
from contextlib import suppress

from aiogram.types import Message

_active_drafts = {}


def stop_draft(bot_id, event):
    if event.chat.type != "private":
        return False
    loader = _active_drafts.get((bot_id, event.chat.id, event.message_thread_id, event.draft_id))
    if not loader:
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
        self.native = False
        self.stopped = False
        self.draft_id = secrets.randbelow(2**31 - 1) + 1
        self.key = None
        self.work = None

    async def __aenter__(self):
        self.work = asyncio.current_task()
        if isinstance(self.message, Message) and self.message.chat.type == "private":
            try:
                await self._draft(self.text)
                self.native = True
                self.key = (self.message.bot.id, self.message.chat.id, self.message.message_thread_id, self.draft_id)
                _active_drafts[self.key] = self
            except Exception:
                pass  # A rejected preview must not prevent the underlying operation.
        if not self.native:
            self.status = await self.message.answer(f"⏳ {self.text}")
        self.task = asyncio.create_task(self._typing())
        return self

    async def _draft(self, text):
        await self.message.bot.send_message_draft(
            chat_id=self.message.chat.id, draft_id=self.draft_id,
            message_thread_id=self.message.message_thread_id,
            text=f"⏳ {text}", parse_mode=self.parse_mode,
            can_stop=True, keep_on_stop=False, request_timeout=5,
        )

    async def update(self, text):
        self.text = text
        with suppress(Exception):
            if self.native:
                await self._draft(text)
            elif self.status:
                await self.status.edit_text(f"⏳ {text}", parse_mode=self.parse_mode)

    async def _typing(self):
        elapsed = 0
        while True:
            with suppress(Exception):
                await self.message.bot.send_chat_action(self.message.chat.id, "typing")
            await asyncio.sleep(4)
            elapsed += 4
            if self.native:
                with suppress(Exception):
                    await self._draft(self.text + ("\nИсточник ещё отвечает. Повторять запрос не нужно." if elapsed >= 16 else ""))
            elif elapsed == 16 and self.status:
                with suppress(Exception):
                    await self.status.edit_text(f"⏳ {self.text}\nИсточник ещё отвечает. Результат появится здесь; повторять команду не нужно.")

    async def __aexit__(self, exc_type, *_):
        if self.key:
            _active_drafts.pop(self.key, None)
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        if self.status:
            with suppress(Exception):
                await self.status.delete()
        if self.stopped and exc_type is asyncio.CancelledError:
            with suppress(Exception):
                await self.message.answer("Поиск остановлен. Можно выбрать другой раздел.")
            # Let cancellation unwind callers too: post-loader code must not run.
