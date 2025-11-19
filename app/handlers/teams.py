import math
from datetime import datetime

from aiogram import Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message

from app.f1_data import get_constructor_standings_df


router = Router()

def _parse_season_from_command(message: Message) -> int:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return datetime.now().year


@router.message(Command("teams"))
async def cmd_teams(message: Message) -> None:
    season = _parse_season_from_command(message)

    try:
        df = get_constructor_standings_df(season)
    except Exception:
        await message.answer(
            "❌ Не удалось получить таблицу команд.\n"
            "Попробуй ещё раз чуть позже."
        )
        return

    if df.empty:
        await message.answer(f"Пока нет данных по кубку конструкторов за {season} год.")
        return

    df = df.sort_values("position")

    lines: list[str] = []

    for row in df.itertuples(index=False):
        pos_raw = getattr(row, "position", None)
        if pos_raw is None:
            continue
        if isinstance(pos_raw, float) and math.isnan(pos_raw):
            continue
        try:
            position = int(pos_raw)
        except (TypeError, ValueError):
            continue

        points_raw = getattr(row, "points", 0.0)
        if isinstance(points_raw, float) and math.isnan(points_raw):
            points = 0.0
        else:
            try:
                points = float(points_raw)
            except (TypeError, ValueError):
                points = 0.0

        wins_raw = getattr(row, "wins", 0)
        if isinstance(wins_raw, float) and math.isnan(wins_raw):
            wins = 0
        else:
            try:
                wins = int(wins_raw)
            except (TypeError, ValueError):
                wins = 0

        team_name = getattr(row, "constructorName", "Unknown")
        nationality = getattr(row, "constructorNationality", "")

        line = (
            f"{position:>2}. {team_name} — "
            f"{points:.0f} очков"
        )
        if wins > 0:
            line += f", побед: {wins}"
        if nationality:
            line += f" ({nationality})"

        lines.append(line)

    if not lines:
        await message.answer(f"Не удалось отобразить команды за {season} год (нет корректных данных).")
        return

    text = (
        f"🏎 Кубок конструкторов {season} — топ команд:\n\n"
        + "\n".join(lines[:20])
        + "\n\nМожно указать год: /teams *год*"
    )

    try:
        await message.answer(text)
    except TelegramNetworkError:
        return