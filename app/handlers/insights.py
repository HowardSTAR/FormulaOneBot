"""The same archive, driver introductions and recap inside Telegram."""
import asyncio
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message, LinkPreviewOptions
from app.f1_data import get_season_schedule_short_async, get_driver_standings_async
from app.services.driver_guides import get_driver_guide
from app.services.race_recap import get_race_recap, format_recap_telegram
from app.utils.mini_app_links import mini_app_button

router = Router()


@router.message(Command("history"))
@router.message(F.text == "📈 История сезонов")
async def history(message: Message):
    keyboard = await mini_app_button(message.bot, "📈 История и сравнение", "/history") if message.chat.type == "private" else None
    await message.answer("📈 <b>История чемпионата</b>\n\nЛичный зачёт с 1950 года, Кубок конструкторов с 1958. "
                         "На сайте можно сравнить до трёх пилотов или команд по сезонам.\n\n"
                         "В Telegram: /drivers 2008 — личный зачёт; /teams 2008 — Кубок конструкторов.\n"
                         "/driver ALO — знакомство с пилотом; /recap — главное после последней гонки.",
                         parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("driver", "pilot"))
async def driver(message: Message, command: CommandObject):
    arguments = (command.args or "").split()
    if len(arguments) not in (1, 2):
        await message.answer("Пример: /driver ALO или /driver HAM 2008. Код пилота берётся из личного зачёта.")
        return
    try:
        season = int(arguments[1]) if len(arguments) == 2 else datetime.now(timezone.utc).year
        if not 1950 <= season <= datetime.now(timezone.utc).year:
            raise ValueError
    except ValueError:
        await message.answer("Укажите год от 1950 до текущего.")
        return
    try:
        frame = await asyncio.wait_for(get_driver_standings_async(season), timeout=30)
    except Exception:
        await message.answer("Зачёт временно недоступен. Попробуйте позже.")
        return
    matches = frame[frame["driverCode"].str.upper() == arguments[0].upper()] if "driverCode" in frame else frame.iloc[0:0]
    if len(matches) != 1:
        await message.answer("Не удалось однозначно найти пилота. Проверьте код и сезон в /drivers.")
        return
    row = matches.iloc[0]
    identifier = str(row.get("driverId", ""))
    guide = get_driver_guide(identifier)
    text = f"🏎 <b>{escape(str(row['givenName']) + ' ' + str(row['familyName']))}</b>\n"
    text += f"Сезон {season}: P{row['position']}, {row['points']:g} очк.\n\n"
    if guide:
        text += f"{escape(guide['intro'])}\n\n<b>Характер выступлений</b>\n{escape(guide['character'])}\n\n"
        text += f"<b>На что смотреть</b>\n{escape(guide['watch'])}\n\n<a href=\"{guide['source']}\">Официальная биография F1</a>"
        text += "\nПодсказка — редакционная; не оценка телеметрии. Биография описывает карьеру, а не только выбранный сезон."
    else:
        text += "Подробная биография и статистика доступны в карточке на сайте. Неподтверждённый стиль пилотирования не описываем."
    keyboard = await mini_app_button(message.bot, "Карточка и история пилота", "/driver-details", driverId=identifier, season=season) if message.chat.type == "private" else None
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard, link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("recap"))
@router.message(F.text == "📰 Рекап гонки")
async def recap(message: Message, command: CommandObject | None = None):
    arguments = (command.args or "").split() if command else []
    now = datetime.now(timezone.utc)
    try:
        if arguments:
            if len(arguments) != 2:
                raise ValueError
            season, round_num = map(int, arguments)
            if not 1950 <= season <= now.year or not 1 <= round_num <= 30:
                raise ValueError
        else:
            season, round_num = now.year, None
    except ValueError:
        await message.answer("Пример: /recap или /recap 2025 10.")
        return
    try:
        schedule = await asyncio.wait_for(get_season_schedule_short_async(season), timeout=25)
        eligible = []
        for race in schedule or []:
            if not race.get("race_start_utc"):
                continue
            start = datetime.fromisoformat(race["race_start_utc"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if start <= now and not race.get("is_cancelled"):
                eligible.append(race)
        event = next((r for r in eligible if r["round"] == round_num), None) if round_num else max(eligible, key=lambda r: r["round"], default=None)
        if not event:
            await message.answer("Для этого сезона или этапа гонка ещё не началась по расписанию.")
            return
        round_num = event["round"]
        result = await asyncio.wait_for(get_race_recap(season, round_num), timeout=45)
    except Exception:
        await message.answer("Источники временно недоступны. Рекап можно запросить позже — результаты не меняются.")
        return
    body = format_recap_telegram(result) or escape(result["note"])
    title = escape(event.get("event_name", f"Этап {round_num}"))
    text = f"📰 <b>{title} · {season}, этап {round_num}</b>\n\n{body}"
    text += "\n\nИзменения чемпионата — за весь уик-энд. Автоматическая сводка без ИИ."
    if result["status"] == "partial":
        text += " Часть данных чемпионата ещё не подтверждена."
    keyboard = await mini_app_button(message.bot, "Рекап и результаты", "/race-results", season=season, round=round_num, mode="archive") if message.chat.type == "private" else None
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
