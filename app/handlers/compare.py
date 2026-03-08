import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from app.db import get_favorite_drivers
from app.f1_data import get_season_schedule_short_async, get_race_results_async, get_driver_standings_async
from app.utils.default import validate_f1_year
from app.utils.image_render import create_comparison_image
from app.utils.loader import Loader

logger = logging.getLogger(__name__)
router = Router()


# --- 1. Машина состояний (FSM) ---
class CompareState(StatesGroup):
    waiting_for_year = State()
    waiting_for_driver_1 = State()
    waiting_for_driver_2 = State()


# --- Вспомогательная функция для клавиатуры ---
def build_drivers_keyboard(
    drivers: list[dict],
    prefix: str,
    exclude_code: str | None = None,
    favorite_codes: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """drivers: [{"code": "VER", "name": "Verstappen"}, ...]. Кнопки показывают имя, callback — код."""
    builder = []
    row = []
    fav = favorite_codes or set()
    sorted_drivers = sorted(drivers, key=lambda d: d["name"])
    for d in sorted_drivers:
        if exclude_code and d["code"] == exclude_code:
            continue
        label = d["name"][:20] if len(d["name"]) > 20 else d["name"]
        if d["code"] in fav:
            label = f"⭐ {label}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}{d['code']}"))
        if len(row) == 3:
            builder.append(row)
            row = []
    if row:
        builder.append(row)
    return InlineKeyboardMarkup(inline_keyboard=builder)


# --- 2. Старт диалога ---
@router.message(F.text == "⚔️ Сравнение")
@router.message(Command("compare"))
async def cmd_compare(message: Message, state: FSMContext):
    await state.clear()
    current_year = datetime.now().year

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Текущий сезон ({current_year})", callback_data=f"drivers_current_{current_year}",)],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")]
        ]
    )

    await message.answer(
        "🏎️ <b>Сравнение пилотов</b>\n\n"
        "Введите год сезона или нажмите на кнопку для текущего сезона:",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.set_state(CompareState.waiting_for_year)


# --- 3. Обработка года ---
@router.message(CompareState.waiting_for_year)
async def process_compare_year(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите год числом.")
        return

    year = int(message.text)
    error_msg = validate_f1_year(year)
    if error_msg:
        await message.answer(error_msg)
        return

    async with Loader(message, f"⏳ Загружаю список пилотов сезона {year}...") as loader:
        standings = await get_driver_standings_async(year)
        favorite_codes = set(await get_favorite_drivers(message.from_user.id))

        if standings.empty:
            await message.answer(f"❌ Не удалось найти данные о пилотах за {year} год.")
            await state.clear()
            return

        try:
            drivers_list = []
            seen_codes = set()
            for _, row in standings.iterrows():
                code = (
                    str(row.get("driverCode", "") or row.get("driverId", "") or "")
                ).upper()[:3]
                if not code:
                    continue
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                family = str(getattr(row, "familyName", None) or getattr(row, "LastName", "") or "").strip()
                given = str(getattr(row, "givenName", None) or getattr(row, "FirstName", "") or "").strip()
                name = family or f"{given} {family}".strip() or code
                drivers_list.append({"code": code, "name": name})

            if not drivers_list:
                await message.answer(f"❌ Не удалось найти пилотов за {year} год.")
                await state.clear()
                return

        except Exception:
            await message.answer("❌ Ошибка обработки списка пилотов.")
            return

        await state.update_data(year=year, drivers_list=drivers_list)

    kb = build_drivers_keyboard(drivers_list, prefix="cmp_d1_", favorite_codes=favorite_codes)
    await message.answer(
        f"📅 Сезон: <b>{year}</b>\n\nВыберите <b>первого</b> пилота:",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.set_state(CompareState.waiting_for_driver_1)


# --- 4. Выбор первого пилота ---
def _driver_name(drivers_list: list, code: str) -> str:
    for d in drivers_list:
        if d["code"] == code:
            return d["name"]
    return code


@router.callback_query(CompareState.waiting_for_driver_1, F.data.startswith("cmp_d1_"))
async def process_driver_1_selection(callback: CallbackQuery, state: FSMContext):
    driver1_code = callback.data.replace("cmp_d1_", "")
    data = await state.get_data()
    drivers_list = data.get("drivers_list", [])
    year = data.get("year")

    await state.update_data(driver1=driver1_code)
    name1 = _driver_name(drivers_list, driver1_code)

    favorite_codes = set(await get_favorite_drivers(callback.from_user.id))
    kb = build_drivers_keyboard(
        drivers_list, prefix="cmp_d2_", exclude_code=driver1_code, favorite_codes=favorite_codes
    )

    await callback.message.edit_text(
        f"📅 Сезон: <b>{year}</b>\n"
        f"1️⃣ Пилот 1: <b>{name1}</b>\n\n"
        f"Выберите <b>второго</b> пилота:",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.set_state(CompareState.waiting_for_driver_2)
    await callback.answer()


# --- 5. Выбор второго пилота ---
@router.callback_query(CompareState.waiting_for_driver_2, F.data.startswith("cmp_d2_"))
async def process_driver_2_selection(callback: CallbackQuery, state: FSMContext):
    driver2_code = callback.data.replace("cmp_d2_", "")
    data = await state.get_data()
    driver1_code = data.get("driver1")
    drivers_list = data.get("drivers_list", [])
    year = data.get("year")

    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass

    name1 = _driver_name(drivers_list, driver1_code)
    name2 = _driver_name(drivers_list, driver2_code)

    try:
        await send_comparison_graph(
            callback.message, driver1_code, driver2_code, year,
            d1_name=name1, d2_name=name2,
        )
    except Exception as e:
        logger.exception("Comparison error")
        await callback.message.answer(f"❌ Произошла ошибка: {e}")

    await callback.answer()


# --- 6. Логика генерации (С ПРОГРЕСС-БАРОМ) ---
async def send_comparison_graph(
    message: Message, d1_code: str, d2_code: str, year: int,
    d1_name: str | None = None, d2_name: str | None = None,
):
    name1 = d1_name or d1_code
    name2 = d2_name or d2_code
    text_init = (
        f"🏎️ <b>Дуэль: {name1} ⚔️ {name2}</b>\n"
        f"📅 Сезон: {year}\n\n"
        f"⏳ Начинаю анализ гонок..."
    )

    async with Loader(message, text_init) as loader:
        schedule = await get_season_schedule_short_async(year)

        current_year = datetime.now().year
        now = datetime.now(timezone.utc)

        passed_races = []
        for r in schedule:
            if r.get("race_start_utc"):
                try:
                    r_dt = datetime.fromisoformat(r["race_start_utc"])
                    if r_dt.tzinfo is None: r_dt = r_dt.replace(tzinfo=timezone.utc)
                    if r_dt <= now:
                        passed_races.append(r)
                except:
                    pass
            elif year < current_year:
                passed_races.append(r)

        if not passed_races:
            await message.answer(f"В сезоне {year} данных о гонках не найдено.")
            return

        d1_history = []
        d2_history = []
        labels = []

        total_races = len(passed_races)

        results_list = [None] * total_races
        tasks = []
        for i, r in enumerate(passed_races):
            tasks.append(get_race_results_async(year, r["round"]))

        pending = set(asyncio.create_task(t) for t in tasks)
        completed_count = 0

        task_to_index = {list(pending)[i]: i for i in range(len(pending))}
        final_results = [None] * total_races

        last_update_time = time.time()

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            completed_count += len(done)

            for t in done:
                idx = task_to_index[t]
                try:
                    final_results[idx] = await t
                except Exception:
                    final_results[idx] = None

            if time.time() - last_update_time > 1.5:
                await loader.update(
                    f"🏎️ <b>Дуэль: {name1} ⚔️ {name2}</b>\n"
                    f"📅 Сезон: {year}\n\n"
                    f"⏳ Загружаю данные: <b>{completed_count} / {total_races}</b> гонок..."
                )
                last_update_time = time.time()

        await loader.update("🎨 Рисую график...")

        for i, race in enumerate(passed_races):
            df = final_results[i]
            label = race.get("event_name", "GP").replace(" Grand Prix", "").replace("Gp", "")
            labels.append(label)

            pts1 = 0
            pts2 = 0

            if df is not None and not df.empty:
                df['Abbreviation'] = df['Abbreviation'].fillna("").astype(str).str.upper()

                row1 = df[df['Abbreviation'] == d1_code]
                if not row1.empty: pts1 = row1.iloc[0]['Points']

                row2 = df[df['Abbreviation'] == d2_code]
                if not row2.empty: pts2 = row2.iloc[0]['Points']

            d1_history.append(pts1)
            d2_history.append(pts2)

        data1 = {"code": d1_code, "name": name1, "history": d1_history, "color": "#ff8700"}
        data2 = {"code": d2_code, "name": name2, "history": d2_history, "color": "#00d2be"}

        photo_io = await asyncio.to_thread(create_comparison_image, data1, data2, labels)
        file = BufferedInputFile(photo_io.read(), filename="comparison.png")

        # Когда мы вызываем отправку фото, мы все еще внутри async with.
        # Как только блок завершится, Loader сам удалит сообщение с "🎨 Рисую график..."
        await message.answer_photo(file, caption=f"Сравнение: {name1} ⚔️ {name2} ({year})")