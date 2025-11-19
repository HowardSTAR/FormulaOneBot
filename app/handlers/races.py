from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.f1_data import get_season_schedule_short

router = Router()

@router.message(Command("races"))
async def cmd_races(message: Message):
    season = 2025  # потом можно хранить в конфиге
    races = get_season_schedule_short(season)

    lines = []
    for r in races:
        lines.append(
            f"{r['round']:02d}. {r['event_name']} "
            f"({r['country']}, {r['location']}) — {r['date']}"
        )

    text = "Календарь сезона:\n\n" + "\n".join(lines)
    await message.answer(text)