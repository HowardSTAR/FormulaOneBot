"""The same archive, driver introductions and recap inside Telegram."""
import asyncio
import math
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message, LinkPreviewOptions, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from app.f1_data import get_season_schedule_short_async, get_driver_standings_async
from app.services.driver_guides import get_driver_guide
from app.services.race_recap import get_race_recap, format_recap_telegram
from app.utils.mini_app_links import mini_app_button
from app.utils.activity_status import ActivityStatus

router = Router()
DRIVERS_PER_PAGE = 6


@router.message(Command("history"))
@router.message(F.text == "📈 История сезонов")
async def history(message: Message):
    async with ActivityStatus(message, "Открываю историю и сравнение сезонов…"):
        keyboard = await _web_button(message, "📈 Открыть историю и сравнение", "/history")
        rows = keyboard.inline_keyboard if keyboard else []
        keyboard = InlineKeyboardMarkup(inline_keyboard=[*rows, [InlineKeyboardButton(text="🏎 Справка о пилоте", callback_data="insights:drivers")]])
        await message.answer("📈 <b>История чемпионата</b>\n\nЛичный зачёт с 1950 года, Кубок конструкторов с 1958. "
                         "На сайте можно сравнить до трёх пилотов или команд по сезонам.\n\n"
                         "Нажмите «Открыть историю и сравнение», выберите участников и годы, затем «Показать сравнение».\n"
                         "Познакомиться с пилотом можно по кнопке ниже.",
                         parse_mode="HTML", reply_markup=keyboard)


async def _web_button(message: Message, label: str, path: str, **params):
    if message.chat.type != "private":
        return None
    try:
        return await asyncio.wait_for(mini_app_button(message.bot, label, path, **params), timeout=5)
    except asyncio.TimeoutError:
        return None


@router.message(F.text == "🏎 Справка о пилоте")
async def choose_driver(message: Message):
    async with ActivityStatus(message, "Загружаю список пилотов…"):
        await _driver_picker(message)


async def _driver_picker(message: Message, page: int = 0, edit: bool = False):
    season = datetime.now(timezone.utc).year
    try:
        frame = await asyncio.wait_for(get_driver_standings_async(season), timeout=30)
    except Exception:
        await message.answer("Не удалось загрузить пилотов. Попробуйте кнопку «Справка о пилоте» позже.")
        return
    buttons = [InlineKeyboardButton(text=f"{row['givenName']} {row['familyName']}", callback_data=f"insights:driver:{season}:{row['driverCode']}")
               for _, row in frame.iterrows() if row.get('driverCode')]
    if not buttons:
        await message.answer("Список пилотов пока недоступен. Попробуйте позже.")
        return
    pages = math.ceil(len(buttons) / DRIVERS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    selected = buttons[page * DRIVERS_PER_PAGE:(page + 1) * DRIVERS_PER_PAGE]
    rows = [selected[i:i + 2] for i in range(0, len(selected), 2)]
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"insights:drivers:page:{page - 1}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"insights:drivers:page:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="← Справочник", callback_data="nav:section:guides")])
    text = f"🏎 О каком пилоте рассказать? Выберите имя.\nСтраница {page + 1} из {pages}."
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        from aiogram.exceptions import TelegramBadRequest
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("insights:drivers:page:"))
async def driver_page_callback(callback: CallbackQuery):
    from app.utils.safe_send import safe_answer_callback
    page = (callback.data or "").removeprefix("insights:drivers:page:")
    if not page.isdigit() or len(page) > 2:
        await safe_answer_callback(callback, "Откройте список пилотов снова.")
        return
    await safe_answer_callback(callback)
    if isinstance(callback.message, Message):
        async with ActivityStatus(callback.message, "Обновляю список пилотов…"):
            await _driver_picker(callback.message, int(page), edit=True)


@router.callback_query(F.data == "insights:drivers")
async def choose_driver_callback(callback: CallbackQuery):
    await callback.answer()
    if isinstance(callback.message, Message):
        await choose_driver(callback.message)


@router.callback_query(F.data.startswith("insights:driver:"))
async def driver_callback(callback: CallbackQuery):
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    parts = (callback.data or '').split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not 1950 <= int(parts[2]) <= datetime.now(timezone.utc).year:
        await callback.message.answer("Выбор устарел. Откройте список пилотов снова.")
        return
    async with ActivityStatus(callback.message, "Готовлю справку о пилоте…"):
        await _show_driver(callback.message, parts[3], int(parts[2]))


@router.message(Command("driver", "pilot"))
async def driver(message: Message, command: CommandObject):
    arguments = (command.args or "").split()
    if not arguments:
        await choose_driver(message)
        return
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
    async with ActivityStatus(message, "Готовлю справку о пилоте…"):
        await _show_driver(message, arguments[0], season)


async def _show_driver(message: Message, code: str, season: int):
    try:
        frame = await asyncio.wait_for(get_driver_standings_async(season), timeout=30)
    except Exception:
        await message.answer("Зачёт временно недоступен. Попробуйте позже.")
        return
    matches = frame[frame["driverCode"].str.upper() == code.upper()] if "driverCode" in frame else frame.iloc[0:0]
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
    keyboard = await _web_button(message, "Карточка и история пилота", "/driver-details", driverId=identifier, season=season)
    rows = keyboard.inline_keyboard if keyboard else []
    keyboard = InlineKeyboardMarkup(inline_keyboard=[*rows, [InlineKeyboardButton(text="Выбрать другого пилота", callback_data="insights:drivers")]])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard, link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("recap"))
@router.message(F.text == "📰 Рекап гонки")
async def recap(message: Message, command: CommandObject | None = None):
    async with ActivityStatus(message, "Готовлю главное после гонки…"):
        await _show_recap(message, command)


async def _show_recap(message: Message, command: CommandObject | None = None):
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
    text += "\n\nИзменения чемпионата — за весь уик-энд."
    if result["status"] == "partial":
        text += " Часть данных чемпионата ещё не подтверждена."
    keyboard = await _web_button(message, "Рекап и результаты", "/race-results", season=season, round=round_num, mode="archive")
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
