from datetime import datetime


from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.f1_data import get_season_schedule_short

router = Router()

def _parse_season_from_command(message: Message) -> int:
    """
    Пытаемся вытащить год сезона из текста команды.
    Примеры:
      "/races" -> текущий год
      "/races 2005" -> 2005
      "/races@MyBot 2010" -> 2010
      "/races abc" -> текущий год
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    # parts[0] — это "/races" или "/races@BotName"
    if len(parts) == 2:
        try:
            year = int(parts[1])
            return year
        except ValueError:
            # если не получилось распарсить, используем текущий год
            pass

    # По умолчанию — текущий год
    return datetime.now().year


@router.message(Command("races"))
async def cmd_races(message: Message) -> None:
    # 1. Определяем сезон
    season = _parse_season_from_command(message)

    # 2. Получаем расписание сезона
    races = get_season_schedule_short(season)

    if not races:
        await message.answer(f"Нет данных по календарю сезона {season}.")
        return

    # 3. Текущая дата (считаем по локальному времени системы)
    today = datetime.today()

    lines: list[str] = []

    for r in races:
        # r["date"] у нас в формате "YYYY-MM-DD" (isoformat),
        # потому что мы так формировали его в get_season_schedule_short
        try:
            race_date = datetime.fromisoformat(r["date"])
        except ValueError:
            # если вдруг формат сломался, считаем гонку будущей
            race_date = today

        # Гонка прошла, если её дата < сегодня
        finished = race_date < today
        status = "✅" if finished else "❌"

        line = (
            f"{status} "
            f"{r['round']:02d}. {r['event_name']} "
            f"({r['country']}, {r['location']}) — {r['date']}"
        )
        lines.append(line)

    header = (
        f"Календарь сезона {season}:\n"
        f"✅ — гонка уже прошла\n"
        f"❌ — гонка ещё впереди\n\n"
    )
    text = header + "\n".join(lines)
    await message.answer(text)