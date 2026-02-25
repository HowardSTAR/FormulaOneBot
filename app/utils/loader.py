import asyncio
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


class Loader:
    """
    Асинхронный менеджер контекста с прогресс-баром загрузки.
    Использует асимптотическое приближение к 99%, пока не завершится блок with.
    """

    def __init__(self, message: Message, text: str = "⏳ Загружаю данные..."):
        self.message = message
        self.text = text
        self.msg: Message | None = None
        self._task: asyncio.Task | None = None
        self.progress: float = 0.0

    async def __aenter__(self):
        self.msg = await self.message.answer(self._build_text(), parse_mode="HTML")
        self._task = asyncio.create_task(self._animate())
        return self

    def _build_text(self) -> str:
        """Формирует текст сообщения с прогресс-баром."""
        # Рисуем 10 блоков (каждый = 10%)
        filled_blocks = int(self.progress / 10)
        empty_blocks = 10 - filled_blocks

        # Символы прогресс-бара
        bar = "█" * filled_blocks + "░" * empty_blocks

        return f"{self.text}\n\n<code>[{bar}] {int(self.progress)}%</code>"

    async def _animate(self):
        # Telegram API не любит частые изменения (ошибка FloodWait),
        # поэтому обновляем статус раз в 1.2 секунды.
        while self.progress < 99:
            try:
                await asyncio.sleep(1.2)

                # Математика фейкового прогресса:
                # На каждом шаге проходим 35% от оставшегося пути до 100%.
                # Это дает быстрый старт и замедление в конце.
                remaining = 100.0 - self.progress
                step = remaining * 0.35

                # Защита от слишком мелких шагов
                if step < 1.0 and self.progress < 99:
                    step = 1.0

                self.progress += step

                # Замираем на 99%, ждем пока вычисления не закончатся
                if self.progress > 99:
                    self.progress = 99.0

                if self.msg:
                    await self.msg.edit_text(self._build_text(), parse_mode="HTML")

            except asyncio.CancelledError:
                # Задача отменена при выходе из контекстного менеджера
                break
            except TelegramBadRequest:
                # Игнорируем ошибку, если текст не изменился
                pass
            except Exception:
                pass

    async def update(self, new_text: str):
        """Позволяет обновить текст лоадера и подстегнуть прогресс."""
        self.text = new_text
        # Если мы перешли на новый этап, можно слегка искусственно накинуть прогресса
        if self.progress < 50:
            self.progress += 20

        if self.msg:
            try:
                await self.msg.edit_text(self._build_text(), parse_mode="HTML")
            except Exception:
                pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Останавливаем анимацию
        if self._task:
            self._task.cancel()

        # Удаляем сообщение с загрузкой (чтобы сразу отправить фото)
        if self.msg:
            try:
                await self.msg.delete()
            except Exception:
                pass