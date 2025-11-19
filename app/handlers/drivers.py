import math
from datetime import datetime

from aiogram import Router, F
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Message
from aiogram.filters import Command


from app.f1_data import get_driver_standings_df

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


async def _send_drivers_for_message(message: Message) -> None:
    season = _parse_season_from_text(message.text or "")

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

        given_name = getattr(row, "givenName", "")
        family_name = getattr(row, "familyName", "")
        full_name = f"{given_name} {family_name}".strip()

        if position == 1:
            trophy = "🥇 "
        elif position == 2:
            trophy = "🥈 "
        elif position == 3:
            trophy = "🥉 "
        else:
            trophy = ""

        line = (
            f"{trophy}"
            f"{position:>2}. "
            f"{full_name} — "
            f"{points:.0f} очков"
        )

        lines.append(line)

    if not lines:
        await message.answer(f"Не удалось отобразить пилотов за {season} год (нет корректных данных).")
        return

    text = (
        f"🏁 Пилоты сезона {season}:\n\n"
        + "\n".join(lines[:30])
        + "\n\nМожно указать год: /drivers *год*"
    )

    try:
        await message.answer(text)
    except TelegramNetworkError:
        return


@router.message(Command("drivers"))
async def cmd_drivers(message: Message) -> None:
    await _send_drivers_for_message(message)


@router.message(F.text == "Личный зачет")
async def btn_drivers(message: Message) -> None:
    await _send_drivers_for_message(message)