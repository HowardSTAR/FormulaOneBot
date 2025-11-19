from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from datetime import datetime, date

from app.f1_data import get_season_schedule_short

router = Router()


def _parse_season_from_text(text: str) -> int:
    """
    Берём год из текста:
      "/races 2005" -> 2005
      "Сезон 2010"  -> 2010
    Если года нет или он кривой — возвращаем текущий год.
    """
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
        # r["date"] у нас в формате "YYYY-MM-DD"
        try:
            race_date = date.fromisoformat(r["date"])
        except ValueError:
            race_date = today

        finished = race_date < today
        status = "✅" if finished else "❌"

        # Если гонка уже прошла — не показываем дату, только название и место
        if finished:
            line = (
                f"{status} "
                f"{r['round']:02d}. {r['event_name']} "
                f"({r['location']})"
                f"\n "
            )
        else:
            # Будущая или сегодняшняя гонка — дату показываем
            line = (
                f"{status} "
                f"{r['round']:02d}. {r['event_name']} "
                f"({r['location']}) — {r['date']}"
                f"\n "
            )

        lines.append(line)

    header = (
        f"Календарь сезона {season}:\n"
        f"✅ — гонка уже прошла (дата скрыта для удобства)\n"
        f"❌ — предстоящие гонки, дата показана\n\n"
    )
    text = header + "\n".join(lines)
    await message.answer(text)


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    await _send_races_for_message(message)


@router.message(F.text == "Сезон")
async def btn_races(message: Message) -> None:
    await _send_races_for_message(message)
