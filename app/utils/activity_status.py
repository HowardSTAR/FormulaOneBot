"""Visible activity, without invented progress percentages or completion times."""
import asyncio
from contextlib import suppress

from aiogram.types import Message


class ActivityStatus:
    def __init__(self, message: Message, text: str):
        self.message = message
        self.text = text
        self.status: Message | None = None
        self.task: asyncio.Task | None = None

    async def __aenter__(self):
        self.status = await self.message.answer(f"⏳ {self.text}")
        self.task = asyncio.create_task(self._typing())
        return self

    async def _typing(self):
        elapsed = 0
        while True:
            with suppress(Exception):
                await self.message.bot.send_chat_action(self.message.chat.id, "typing")
            await asyncio.sleep(4)
            elapsed += 4
            if elapsed == 16 and self.status:
                with suppress(Exception):
                    await self.status.edit_text(f"⏳ {self.text}\nИсточник ещё отвечает. Результат появится здесь; повторять команду не нужно.")

    async def __aexit__(self, *_):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        if self.status:
            with suppress(Exception):
                await self.status.delete()
