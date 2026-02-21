import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from app.f1_data import get_season_schedule_short_async, get_race_results_async, get_driver_standings_async
from app.utils.default import validate_f1_year
from app.utils.image_render import create_comparison_image

logger = logging.getLogger(__name__)
router = Router()


# --- 1. Машина состояний (FSM) ---
class CompareState(StatesGroup):
    waiting_for_year = State()
    waiting_for_driver_1 = State()
    waiting_for_driver_2 = State()


# --- Вспомогательная функция для клавиатуры ---
def build_drivers_keyboard(drivers: list[str], prefix: str, exclude: str | None = None) -> InlineKeyboardMarkup:
    builder = []
    row = []
    sorted_drivers = sorted(drivers)
    for code in sorted_drivers:
        if exclude and code == exclude:
            continue
        row.append(InlineKeyboardButton(text=code, callback_data=f"{prefix}{code}"))
        if len(row) == 4:
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

    loading_msg = await message.answer(f"⏳ Загружаю список пилотов сезона {year}...")

    # Получаем список пилотов
    standings = await get_driver_standings_async(year)

    if standings.empty:
        await loading_msg.edit_text(f"❌ Не удалось найти данные о пилотах за {year} год.")
        await state.clear()
        return

    try:
        # Пытаемся найти колонку с кодом
        if 'driverCode' in standings.columns:
            drivers_list = standings['driverCode'].tolist()
        elif 'driverId' in standings.columns:
            # Fallback: берем ID и делаем upper
            drivers_list = [str(d).upper()[:3] for d in standings['driverId'].tolist()]
        else:
            # Fallback для старых данных
            drivers_list = []

        drivers_list = list(set([d for d in drivers_list if d]))

        # Если список пуст (бывает в старых сезонах), пробуем достать из index
        if not drivers_list and not standings.empty:
            drivers_list = [str(x).upper()[:3] for x in standings.index.tolist()]

    except Exception:
        await loading_msg.edit_text("❌ Ошибка обработки списка пилотов.")
        return

    await state.update_data(year=year, drivers_list=drivers_list)

    kb = build_drivers_keyboard(drivers_list, prefix="cmp_d1_")

    await loading_msg.delete()
    await message.answer(
        f"📅 Сезон: <b>{year}</b>\n\nВыберите <b>первого</b> пилота:",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.set_state(CompareState.waiting_for_driver_1)


# --- 4. Выбор первого пилота ---
@router.callback_query(CompareState.waiting_for_driver_1, F.data.startswith("cmp_d1_"))
async def process_driver_1_selection(callback: CallbackQuery, state: FSMContext):
    driver1_code = callback.data.replace("cmp_d1_", "")
    data = await state.get_data()
    drivers_list = data.get("drivers_list", [])
    year = data.get("year")

    await state.update_data(driver1=driver1_code)

    kb = build_drivers_keyboard(drivers_list, prefix="cmp_d2_", exclude=driver1_code)

    await callback.message.edit_text(
        f"📅 Сезон: <b>{year}</b>\n"
        f"1️⃣ Пилот 1: <b>{driver1_code}</b>\n\n"
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
    year = data.get("year")

    await state.clear()

    # Показываем статус и начинаем загрузку
    status_msg = await callback.message.edit_text(
        f"🏎️ <b>Дуэль: {driver1_code} ⚔️ {driver2_code}</b>\n"
        f"📅 Сезон: {year}\n\n"
        f"⏳ Начинаю анализ гонок...", parse_mode="HTML"
    )

    try:
        await send_comparison_graph(status_msg, driver1_code, driver2_code, year)
    except Exception as e:
        logger.exception("Comparison error")
        await status_msg.edit_text(f"❌ Произошла ошибка: {e}")

    await callback.answer()


# --- 6. Логика генерации (С ПРОГРЕСС-БАРОМ) ---
async def send_comparison_graph(message: Message, d1_code: str, d2_code: str, year: int):
    schedule = await get_season_schedule_short_async(year)

    current_year = datetime.now().year
    now = datetime.now(timezone.utc)

    passed_races = []
    for r in schedule:
        # Проверка даты, чтобы не грузить будущее
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
        await message.edit_text(f"В сезоне {year} данных о гонках не найдено.")
        return

    d1_history = []
    d2_history = []
    labels = []

    total_races = len(passed_races)

    # --- Оптимизированная загрузка с прогрессом ---
    results_list = [None] * total_races

    # Создаем задачи
    tasks = []
    for i, r in enumerate(passed_races):
        tasks.append(get_race_results_async(year, r["round"]))

    # Запускаем и обновляем статус каждые 3 завершенные задачи
    # (или просто ждем всё, но с периодическим апдейтом сообщения, если gather висит)

    # Вариант 1: Просто gather (быстро, но если висит - пользователь нервничает)
    # results_list = await asyncio.gather(*tasks)

    # Вариант 2: Постепенный прогресс
    pending = set(asyncio.create_task(t) for t in tasks)
    completed_count = 0

    # Сохраняем мапинг task -> index, чтобы потом собрать в правильном порядке
    task_to_index = {list(pending)[i]: i for i in range(len(pending))}
    final_results = [None] * total_races

    last_update_time = 0

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        completed_count += len(done)

        for t in done:
            idx = task_to_index[t]
            try:
                final_results[idx] = await t
            except Exception:
                final_results[idx] = None

        # Обновляем сообщение раз в 2 секунды, чтобы не словить FloodWait
        import time
        if time.time() - last_update_time > 2.0:
            try:
                await message.edit_text(
                    f"🏎️ <b>Дуэль: {d1_code} ⚔️ {d2_code}</b>\n"
                    f"📅 Сезон: {year}\n\n"
                    f"⏳ Загружаю данные: <b>{completed_count} / {total_races}</b> гонок...", parse_mode="HTML"
                )
                last_update_time = time.time()
            except:
                pass

    # --- Обработка данных ---
    await message.edit_text("🎨 Рисую график...")

    for i, race in enumerate(passed_races):
        df = final_results[i]
        label = race.get("event_name", "GP").replace(" Grand Prix", "").replace("Gp", "")
        labels.append(label)

        pts1 = 0
        pts2 = 0

        if df is not None and not df.empty:
            # Нормализация
            df['Abbreviation'] = df['Abbreviation'].fillna("").astype(str).str.upper()

            row1 = df[df['Abbreviation'] == d1_code]
            if not row1.empty: pts1 = row1.iloc[0]['Points']

            row2 = df[df['Abbreviation'] == d2_code]
            if not row2.empty: pts2 = row2.iloc[0]['Points']

        d1_history.append(pts1)
        d2_history.append(pts2)

    # Цвета
    data1 = {"code": d1_code, "history": d1_history, "color": "#ff8700"}
    data2 = {"code": d2_code, "history": d2_history, "color": "#00d2be"}

    # Рендер в отдельном потоке (CPU bound)
    photo_io = await asyncio.to_thread(create_comparison_image, data1, data2, labels)

    file = BufferedInputFile(photo_io.read(), filename="comparison.png")

    # Удаляем текстовое сообщение и шлем фото
    await message.delete()
    await message.answer_photo(file, caption=f"Сравнение: {d1_code} ⚔️ {d2_code} ({year})")