from datetime import datetime, date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.f1_data import get_season_schedule_short

router = Router()

def _parse_season_from_text(text: str) -> int:
    text = (text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return datetime.now().year


async def _send_races_for_message(message: Message) -> None:
    season = _parse_season_from_text(message.text or "")

    races = get_season_schedule_short(season)

    if not races:
        await message.answer(f"Нет данных по календарю сезона {season}.")
        return

    today = date.today()
    lines: list[str] = []

    for r in races:
        try:
            race_date = date.fromisoformat(r["date"])
        except ValueError:
            race_date = today

        finished = race_date < today
        status = "✅" if finished else "❌"

        line = (
            f"{status} "
            f"{r['round']:02d}. {r['event_name']} "
            f"{r['location']} — {r['date']}"
        )
        lines.append(line)

    header = (
        f"Календарь сезона {season}:\n"
        f"✅ — гонка уже прошла\n"
        f"❌ — гонка ещё впереди\n\n"
    )
    text = header + "\n".join(lines)
    await message.answer(text)


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    await _send_races_for_message(message)


@router.message(F.text == "Сезон")
async def btn_races(message: Message) -> None:
    await _send_races_for_message(message)