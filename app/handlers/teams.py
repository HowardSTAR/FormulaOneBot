from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.f1_data import get_constructor_standings_df

# Пока захардкодим сезон, потом можно вынести в конфиг
CURRENT_SEASON = 2025

router = Router()

@router.message(Command("teams"))
async def cmd_teams(message: Message) -> None:
    """
    Показать топ-10 команд в кубке конструкторов.
    """
    try:
        df = get_constructor_standings_df(CURRENT_SEASON)
    except Exception:
        await message.answer(
            "❌ Не удалось получить таблицу команд.\n"
            "Попробуй ещё раз чуть позже."
        )
        return

    if df.empty:
        await message.answer("Пока нет данных по кубку конструкторов.")
        return

    df = df.sort_values("position")

    lines: list[str] = []

    for row in df.head(10).itertuples(index=False):
        position = int(row.position)
        points = float(row.points)
        wins = int(row.wins)

        team_name = getattr(row, "constructorName", "Unknown")
        nationality = getattr(row, "constructorNationality", "")

        # " 1. Red Bull Racing — 600 очков, побед: 10 (Австрия)"
        line = (
            f"{position:>2}. {team_name} — "
            f"{points:.0f} очков"
        )
        if wins > 0:
            line += f", побед: {wins}"
        if nationality:
            line += f" ({nationality})"

        lines.append(line)

    text = (
        f"🏎 Кубок конструкторов {CURRENT_SEASON} — топ-10:\n\n"
        + "\n".join(lines)
        + "\n\nПопробуй /drivers, чтобы посмотреть личный зачёт."
    )

    await message.answer(text)