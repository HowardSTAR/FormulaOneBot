from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command


from app.f1_data import get_driver_standings_df

CURRENT_SEASON = 2025

router = Router()

@router.message(Command("drivers"))
async def cmd_drivers(message: Message) -> None:
    """
    Показать топ-10 пилотов в личном зачёте.
    """
    try:
        df = get_driver_standings_df(CURRENT_SEASON)
    except Exception as exc:
        # Можно сделать свой класс F1DataError, но на первое время хватит так
        await message.answer(
            "❌ Не удалось получить таблицу пилотов.\n"
            "Возможно, сейчас недоступен источник данных. Попробуй ещё раз позже."
        )
        return

    if df.empty:
        await message.answer("Пока нет данных по личному зачёту пилотов.")
        return

    # На всякий случай отсортируем по position
    df = df.sort_values("position")

    lines: list[str] = []

    # Возьмём только топ-10
    for row in df.head(30).itertuples(index=False):
        # row имеет атрибуты с именами колонок:
        # position, points, wins, driverCode, givenName, familyName,
        # constructorNames (список строк) и т.д.

        position = int(row.position)
        points = float(row.points)
        wins = int(row.wins)

        code = getattr(row, "driverCode", "") or ""
        given_name = getattr(row, "givenName", "")
        family_name = getattr(row, "familyName", "")
        full_name = f"{given_name} {family_name}".strip()

        # constructorNames: [<str>] по доке FastF1
        constructor_names = getattr(row, "constructorNames", None)
        if isinstance(constructor_names, (list, tuple)) and constructor_names:
            team_name = str(constructor_names[0])
        else:
            # fallback, если формат поменяется
            team_name = str(constructor_names) if constructor_names is not None else "—"

        # Красиво форматируем строку:
        # " 1. VER Max Verstappen — 400 очков (Red Bull Racing)"
        line = (
            f"{position:>2}. "
            f"{code or '???':>3} "
            f"{full_name} — "
            f"{points:.0f} очков"
        )
        if wins > 0:
            line += f", побед: {wins}"
        line += f" ({team_name})"

        lines.append(line)

    text = (
        f"🏁 Топ-10 пилотов сезона {CURRENT_SEASON}:\n\n"
        + "\n".join(lines)
        + "\n\nДоступна команда /teams для кубка конструкторов."
    )

    await message.answer(text)
