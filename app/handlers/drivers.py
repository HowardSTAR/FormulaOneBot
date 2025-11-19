import math
from datetime import datetime

from aiogram import Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Message
from aiogram.filters import Command


from app.f1_data import get_driver_standings_df

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


@router.message(Command("drivers"))
async def cmd_drivers(message: Message) -> None:
    season = _parse_season_from_command(message)

    try:
        df = get_driver_standings_df(season)
    except Exception:
        await message.answer(
            "❌ Не удалось получить таблицу пилотов.\n"
            "Возможно, сейчас недоступен источник данных. Попробуй ещё раз позже."
        )
        return

    if df.empty:
        await message.answer(f"Пока нет данных по личному зачёту пилотов за {season} год.")
        return

    df = df.sort_values("position")

    lines: list[str] = []

    for row in df.itertuples(index=False):
        # --- position ---
        pos_raw = getattr(row, "position", None)
        if pos_raw is None:
            # строка без позиции нам не интересна
            continue
        if isinstance(pos_raw, float) and math.isnan(pos_raw):
            # NaN — пропускаем эту строку
            continue
        try:
            position = int(pos_raw)
        except (TypeError, ValueError):
            # на всякий случай, если формат странный
            continue

        # --- points ---
        points_raw = getattr(row, "points", 0.0)
        if isinstance(points_raw, float) and math.isnan(points_raw):
            points = 0.0
        else:
            try:
                points = float(points_raw)
            except (TypeError, ValueError):
                points = 0.0

        # --- wins ---
        wins_raw = getattr(row, "wins", 0)
        if isinstance(wins_raw, float) and math.isnan(wins_raw):
            wins = 0
        else:
            try:
                wins = int(wins_raw)
            except (TypeError, ValueError):
                wins = 0

        code = getattr(row, "driverCode", "") or ""
        given_name = getattr(row, "givenName", "")
        family_name = getattr(row, "familyName", "")
        full_name = f"{given_name} {family_name}".strip()

        constructor_names = getattr(row, "constructorNames", None)
        if isinstance(constructor_names, (list, tuple)) and constructor_names:
            team_name = str(constructor_names[0])
        else:
            team_name = str(constructor_names) if constructor_names is not None else "—"

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

    if not lines:
        await message.answer(f"Не удалось отобразить пилотов за {season} год (нет корректных данных).")
        return

    text = (
        f"🏁 Топ пилотов сезона {season}:\n\n"
        + "\n".join(lines[:30])
        + "\n\nМожно указать год: /drivers *год*"
    )

    try:
        await message.answer(text)
    except TelegramNetworkError:
        return