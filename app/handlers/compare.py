"""Season → participant pair → graphs, with isolated callbacks and sessions."""
import asyncio
import logging
import re
import secrets
import time
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from app.db import get_favorite_drivers
from app.f1_data import get_season_schedule_short_async, get_driver_standings_async, get_constructor_standings_async
from app.services.bot_comparison import load_points_series
from app.utils.default import validate_f1_year
from app.utils.image_render import create_comparison_image
from app.utils.loader import Loader
from app.utils.safe_send import safe_answer_callback
from app.utils.telegram_presentation import disabled_button

logger = logging.getLogger(__name__)
router = Router()
PAGE_SIZE = 8


class CompareState(StatesGroup):
    waiting_for_kind = State()
    waiting_for_year = State()
    waiting_for_driver_1 = State()
    waiting_for_driver_2 = State()


def build_drivers_keyboard(drivers, prefix, exclude_code=None, favorite_codes=None):
    """Compatibility helper; callbacks do not contain display names."""
    buttons = [InlineKeyboardButton(text=("⭐ " if d["code"] in (favorite_codes or set()) else "") + d["name"],
                                   callback_data=f"{prefix}{d['code']}")
               for d in sorted(drivers, key=lambda d: d["name"]) if d["code"] != exclude_code]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def _navigation(nonce):
    return [InlineKeyboardButton(text="Отмена", callback_data=f"cmp:cancel:{nonce}")]


def _year_keyboard(nonce):
    year = datetime.now().year
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Текущий сезон ({year})", callback_data=f"cmp:year:{nonce}:{year}", style="primary")],
        [InlineKeyboardButton(text="← Пилоты / команды", callback_data=f"cmp:kind-menu:{nonce}")],
        _navigation(nonce),
    ])


def _picker(data, second=False, page=0):
    options = [(i, d) for i, d in enumerate(data["participants"]) if not second or i != data["first"]]
    last_page = max(0, (len(options) - 1) // PAGE_SIZE)
    page = max(0, min(page, last_page))
    nonce = data["nonce"]
    buttons = [InlineKeyboardButton(text=("⭐ " if item.get("favorite") else "") + item["name"],
                                   callback_data=f"cmp:pick:{nonce}:{index}")
               for index, item in options[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if len(options) > PAGE_SIZE:
        rows.append([
            InlineKeyboardButton(text="←", callback_data=f"cmp:page:{nonce}:{page - 1}") if page else disabled_button("←"),
            disabled_button(f"{page + 1} / {last_page + 1}"),
            InlineKeyboardButton(text="→", callback_data=f"cmp:page:{nonce}:{page + 1}") if page < last_page else disabled_button("→"),
        ])
    if second:
        rows.append([InlineKeyboardButton(text="← Изменить первого участника", callback_data=f"cmp:first:{nonce}")])
    rows.append([InlineKeyboardButton(text="Другой сезон", callback_data=f"cmp:season:{nonce}")])
    rows.append(_navigation(nonce))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _picker_text(data, second=False):
    title = "пилотов" if data["kind"] == "drivers" else "команд"
    text = f"📊 <b>Сравнение {title} · {data['year']}</b>\n\n"
    if second:
        text += "Первый участник: <b>" + escape(data["participants"][data["first"]]["name"]) + "</b>\n\n"
    return text + ("Выберите второго участника:" if second else "Выберите первого участника:")


def _actor_message(callback):
    return callback.message.model_copy(update={"from_user": callback.from_user, "text": None, "entities": None}).as_(callback.bot)


@router.message(F.text == "⚔️ Сравнение")
@router.message(Command("compare"))
async def cmd_compare(message: Message, state: FSMContext):
    await state.clear()
    nonce = secrets.token_hex(4)
    await state.update_data(nonce=nonce)
    await state.set_state(CompareState.waiting_for_kind)
    await message.answer("📊 <b>Сравнение</b>\n\nВыберите пилотов или команды, затем сезон и двух участников.", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏎 Пилоты", callback_data=f"cmp:kind:{nonce}:drivers", style="primary"),
            InlineKeyboardButton(text="🏆 Команды", callback_data=f"cmp:kind:{nonce}:teams"),
        ], _navigation(nonce)]))


async def _ask_year(message, state, data):
    await state.set_state(CompareState.waiting_for_year)
    label = "пилотов" if data["kind"] == "drivers" else "команд"
    await message.answer(f"📅 <b>Сравнение {label}</b>\n\nВведите год сезона или выберите текущий.",
                         reply_markup=_year_keyboard(data["nonce"]), parse_mode="HTML")


async def _load_participants(message, state, year):
    data = await state.get_data()
    error = validate_f1_year(year)
    if data.get("kind") == "teams" and year < 1958:
        error = "Кубок конструкторов существует с 1958 года. Выберите другой сезон."
    if error:
        await message.answer(error)
        return
    async with Loader(message, f"Загружаю участников сезона {year}…"):
        fetch = get_driver_standings_async if data["kind"] == "drivers" else get_constructor_standings_async
        try:
            standings = await asyncio.wait_for(fetch(year), timeout=20)
        except Exception:
            await message.answer("Источник зачёта недоступен. Попробуйте другой сезон или повторите позже.")
            return
        participants, seen = [], set()
        favorites = set()
        if data["kind"] == "drivers" and message.chat.type == ChatType.PRIVATE:
            favorites = set(await get_favorite_drivers(message.from_user.id))
        if standings is not None and not standings.empty:
            for row in standings.to_dict("records"):
                driver = data["kind"] == "drivers"
                identifier = str(row.get("driverId") or row.get("driverCode") or "") if driver else str(row.get("constructorId") or row.get("constructorName") or "")
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                name = f"{row.get('givenName', '')} {row.get('familyName', '')}".strip() if driver else str(row.get("constructorName") or identifier)
                participants.append({"id": identifier, "code": str(row.get("driverCode") or identifier),
                                     "name": name or identifier, "favorite": row.get("driverCode") in favorites})
        if len(participants) < 2:
            await message.answer(f"За {year} год не удалось найти двух участников. Выберите другой сезон.")
            return
    participants.sort(key=lambda p: p["name"].casefold())
    await state.update_data(year=year, participants=participants, first=None)
    await state.set_state(CompareState.waiting_for_driver_1)
    data = await state.get_data()
    await message.answer(_picker_text(data), reply_markup=_picker(data), parse_mode="HTML")


@router.message(CompareState.waiting_for_year)
async def process_compare_year(message: Message, state: FSMContext):
    if not (message.text or "").strip().isdigit():
        await message.answer("Введите год числом, например 1997, или нажмите «Текущий сезон».")
        return
    await _load_participants(message, state, int(message.text.strip()))


@router.callback_query(F.data.startswith("cmp:"))
async def comparison_callback(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await safe_answer_callback(callback, "Откройте сравнение снова.")
        return
    parts = (callback.data or "").split(":")
    if len(parts) == 4 and parts[1] == "new" and parts[2] in {"drivers", "teams"} and parts[3].isdigit():
        await safe_answer_callback(callback)
        await state.clear()
        await state.update_data(nonce=secrets.token_hex(4), kind=parts[2])
        await state.set_state(CompareState.waiting_for_year)
        await _load_participants(_actor_message(callback), state, int(parts[3]))
        return
    data = await state.get_data()
    if len(parts) not in (3, 4) or not data.get("nonce") or parts[2] != data["nonce"]:
        await safe_answer_callback(callback, "Эта кнопка устарела. Откройте своё сравнение заново.", show_alert=True)
        return
    action, current = parts[1], await state.get_state()
    await safe_answer_callback(callback)
    message = _actor_message(callback)
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("Сравнение отменено. Можно выбрать другой раздел.")
    elif action == "kind-menu":
        await cmd_compare(message, state)
    elif action == "kind" and len(parts) == 4 and parts[3] in {"drivers", "teams"} and current == CompareState.waiting_for_kind.state:
        await state.update_data(kind=parts[3])
        await _ask_year(message, state, await state.get_data())
    elif action == "season" and current in {CompareState.waiting_for_driver_1.state, CompareState.waiting_for_driver_2.state}:
        await _ask_year(message, state, data)
    elif action == "year" and len(parts) == 4 and parts[3].isdigit() and current == CompareState.waiting_for_year.state:
        await _load_participants(message, state, int(parts[3]))
    elif action == "first" and data.get("participants") and current == CompareState.waiting_for_driver_2.state:
        await state.update_data(first=None)
        await state.set_state(CompareState.waiting_for_driver_1)
        await callback.message.edit_text(_picker_text(data), reply_markup=_picker(data), parse_mode="HTML")
    elif action == "page" and len(parts) == 4 and re.fullmatch(r"\d{1,3}", parts[3]) and current in {CompareState.waiting_for_driver_1.state, CompareState.waiting_for_driver_2.state}:
        second = current == CompareState.waiting_for_driver_2.state
        await callback.message.edit_text(_picker_text(data, second), reply_markup=_picker(data, second, int(parts[3])), parse_mode="HTML")
    elif action == "pick" and len(parts) == 4 and parts[3].isdigit() and current in {CompareState.waiting_for_driver_1.state, CompareState.waiting_for_driver_2.state}:
        index = int(parts[3])
        if not 0 <= index < len(data["participants"]):
            return
        if current == CompareState.waiting_for_driver_1.state:
            await state.update_data(first=index)
            await state.set_state(CompareState.waiting_for_driver_2)
            data = await state.get_data()
            await callback.message.edit_text(_picker_text(data, True), reply_markup=_picker(data, True), parse_mode="HTML")
        elif index != data["first"]:
            first, second = data["participants"][data["first"]], data["participants"][index]
            await state.clear()
            try:
                await send_comparison_graph(message, first["id"], second["id"], data["year"],
                                            d1_name=first["name"], d2_name=second["name"], kind=data["kind"])
            except Exception:
                logger.exception("Comparison failed")
                await message.answer("Не удалось построить сравнение. Попробуйте позже или выберите другой сезон.")


async def send_comparison_graph(message, d1_code, d2_code, year, d1_name=None, d2_name=None, *, kind="drivers"):
    name1, name2 = d1_name or d1_code, d2_name or d2_code
    async with Loader(message, f"Готовлю сравнение: {escape(name1)} / {escape(name2)} · {year}") as loader:
        schedule = await asyncio.wait_for(get_season_schedule_short_async(year), timeout=20)
        last_update = 0
        async def progress(completed, total):
            nonlocal last_update
            if completed == total or time.monotonic() - last_update >= 1.5:
                last_update = time.monotonic()
                await loader.update(f"Загружено зачётов: {completed} / {total}")
        fetch = get_driver_standings_async if kind == "drivers" else get_constructor_standings_async
        result = await load_points_series(year, kind, [d1_code, d2_code], schedule, fetch, progress)
        await loader.update("Рисую графики…")
        series = [{"code": code, "name": name, "history": history, "total_points": total, "cumulative": True,
                   "season": year, "kind": kind, "color": color, "rounds": [int(e["round"]) for e in result["events"]]}
                  for code, name, history, total, color in zip([d1_code, d2_code], [name1, name2], result["histories"], result["totals"], ["#ff625d", "#00d2be"])]
        labels = [str(e.get("event_name") or f"Этап {e['round']}").replace(" Grand Prix", "") for e in result["events"]]
        photo = await asyncio.to_thread(create_comparison_image, *series, labels)
        caption = (f"📊 Сравнение {'пилотов' if kind == 'drivers' else 'команд'} · {year}\n"
                   f"{escape(name1)} / {escape(name2)}\n\n"
                   "Официальный зачёт, включая спринты и корректировки. Нижний график — изменение очков за уик-энд.")
        if result["missing"]:
            caption += f"\nНет подтверждённых данных по {result['missing']} этапам: на графике пропуски, не нули."
        await message.answer_photo(BufferedInputFile(photo.getvalue(), filename=f"comparison_{kind}_{year}.png"),
            caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Сравнить другую пару", callback_data=f"cmp:new:{kind}:{year}", style="primary")],
                [InlineKeyboardButton(text="← Статистика", callback_data="nav:section:stats")],
            ]))
