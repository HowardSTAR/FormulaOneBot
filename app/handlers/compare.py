import asyncio
from datetime import datetime, date

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.f1_data import get_season_schedule_short_async, get_race_results_async, get_driver_standings_async
from app.utils.image_render import create_comparison_image
from app.utils.default import validate_f1_year

# Инициализация роутера
router = Router()


# --- 1. Машина состояний (FSM) ---
class CompareState(StatesGroup):
    waiting_for_year = State()
    waiting_for_driver_1 = State()
    waiting_for_driver_2 = State()


# --- Вспомогательная функция для клавиатуры ---
def build_drivers_keyboard(drivers: list[str], prefix: str, exclude: str | None = None) -> InlineKeyboardMarkup:
    """
    Строит клавиатуру с кодами пилотов.
    prefix: префикс для callback_data (например, "cmp1_" или "cmp2_")
    """
    builder = []
    row = []

    # Сортируем алфавитно
    sorted_drivers = sorted(drivers)

    for code in sorted_drivers:
        if exclude and code == exclude:
            continue

        row.append(InlineKeyboardButton(text=code, callback_data=f"{prefix}{code}"))

        # По 4 кнопки в ряд
        if len(row) == 4:
            builder.append(row)
            row = []

    if row:
        builder.append(row)

    return InlineKeyboardMarkup(inline_keyboard=builder)


# --- 2. Старт диалога (Запрос года) ---
@router.message(F.text == "⚔️ Сравнение")
@router.message(Command("compare"))
async def cmd_compare(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏎️ <b>Сравнение пилотов</b>\n\n"
        "Введите год сезона, который вас интересует (например: 2024):"
    )
    await state.set_state(CompareState.waiting_for_year)


# --- 3. Обработка года и вывод пилотов ---
@router.message(CompareState.waiting_for_year)
async def process_compare_year(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите год числом.")
        return

    year = int(message.text)

    # Валидация года
    error_msg = validate_f1_year(year)
    if error_msg:
        await message.answer(error_msg)
        return

    loading_msg = await message.answer(f"⏳ Загружаю список пилотов сезона {year}...")

    # Получаем список пилотов через таблицу чемпионата
    # Это самый надежный способ получить тех, кто участвовал
    standings = await get_driver_standings_async(year)

    if standings.empty:
        await loading_msg.edit_text(f"❌ Не удалось найти данные о пилотах за {year} год.")
        await state.clear()
        return

    # Извлекаем коды пилотов (обычно колонка 'driverId' или 'driverCode' в Ergast,
    # но fastf1 возвращает DataFrame, где коды часто в индексе или колонке 'driverCode')
    # В обновленном fastf1/ergast обычно есть колонки 'driverId' и 'driverCode'.
    # Попробуем найти код.
    try:
        if 'driverCode' in standings.columns:
            drivers_list = standings['driverCode'].tolist()
        elif 'driverId' in standings.columns:
            # Если кодов нет, берем ID и делаем upper (например verstappen -> VERSTAPPEN, не идеально, но сойдет)
            # Но лучше взять первые 3 буквы фамилии если кода нет
            drivers_list = [d.upper()[:3] for d in standings['driverId'].tolist()]
        else:
            raise ValueError("Columns not found")

        # Убираем дубликаты и пустые
        drivers_list = list(set([d for d in drivers_list if d]))
    except Exception as e:
        await loading_msg.edit_text("❌ Ошибка обработки списка пилотов.")
        return

    # Сохраняем год и список пилотов в память
    await state.update_data(year=year, drivers_list=drivers_list)

    # Строим клавиатуру
    kb = build_drivers_keyboard(drivers_list, prefix="cmp_d1_")

    await loading_msg.delete()  # Удаляем "Загружаю..."
    await message.answer(
        f"📅 Сезон: <b>{year}</b>\n\nВыберите <b>первого</b> пилота:",
        reply_markup=kb
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

    # Генерируем новую клавиатуру без выбранного пилота
    kb = build_drivers_keyboard(drivers_list, prefix="cmp_d2_", exclude=driver1_code)

    # Редактируем сообщение (заменяем старое)
    await callback.message.edit_text(
        f"📅 Сезон: <b>{year}</b>\n"
        f"1️⃣ Пилот 1: <b>{driver1_code}</b>\n\n"
        f"Выберите <b>второго</b> пилота:",
        reply_markup=kb
    )
    await state.set_state(CompareState.waiting_for_driver_2)
    await callback.answer()


# --- 5. Выбор второго пилота и старт генерации ---
@router.callback_query(CompareState.waiting_for_driver_2, F.data.startswith("cmp_d2_"))
async def process_driver_2_selection(callback: CallbackQuery, state: FSMContext):
    driver2_code = callback.data.replace("cmp_d2_", "")

    data = await state.get_data()
    driver1_code = data.get("driver1")
    year = data.get("year")

    # Удаляем клавиатуру и показываем статус
    await callback.message.edit_text(
        f"🏎️ <b>Дуэль: {driver1_code} ⚔️ {driver2_code}</b>\n"
        f"📅 Сезон: {year}\n\n"
        f"📊 Рисую график... Пожалуйста, подождите.",
        reply_markup=None
    )
    await state.clear()  # Очищаем состояние

    # Запускаем тяжелую логику
    try:
        await send_comparison_graph(callback.message, driver1_code, driver2_code, year)
        # Опционально: удалить текстовое сообщение "Рисую график", так как придет картинка
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"❌ Произошла ошибка: {e}")

    await callback.answer()


# --- 6. Логика генерации (Обновленная под год) ---
async def send_comparison_graph(message: types.Message, d1_code: str, d2_code: str, year: int):
    # 1. Расписание для меток
    schedule = await get_season_schedule_short_async(year)

    # Фильтруем гонки (если год текущий - только прошедшие, если прошлый - все)
    current_year = datetime.now().year
    today = date.today()

    passed_races = []
    for r in schedule:
        # Если год прошлый - берем всё
        if year < current_year:
            passed_races.append(r)
        # Если год текущий - проверяем дату
        else:
            if r.get("date") and date.fromisoformat(r["date"]) <= today:
                passed_races.append(r)

    if not passed_races:
        # Если расписание пустое или гонок не было, отправляем текстовое сообщение (так как message.delete() могло сработать выше)
        # В данном случае лучше отправить новое сообщение
        await message.answer(f"В сезоне {year} данных о гонках не найдено.")
        return

    d1_history = []
    d2_history = []
    labels = []

    # Загружаем результаты параллельно
    tasks = [get_race_results_async(year, r["round"]) for r in passed_races]
    results_list = await asyncio.gather(*tasks)

    for race, df in zip(passed_races, results_list):
        label = race["event_name"].replace(" Grand Prix", "").replace("Gp", "")
        labels.append(label)

        pts1 = 0
        pts2 = 0

        if not df.empty:
            # Ищем по коду (Abbreviation)
            # В старых годах Abbreviation может быть NaN, тогда ищем по DriverNumber или фамилии
            # Но Ergast обычно возвращает 3 буквы.

            # Нормализация для поиска
            df['Abbreviation'] = df['Abbreviation'].fillna("").astype(str).str.upper()

            row1 = df[df['Abbreviation'] == d1_code]
            if not row1.empty: pts1 = row1.iloc[0]['Points']

            row2 = df[df['Abbreviation'] == d2_code]
            if not row2.empty: pts2 = row2.iloc[0]['Points']

        d1_history.append(pts1)
        d2_history.append(pts2)

    # Цвета (базовые)
    data1 = {"code": d1_code, "history": d1_history, "color": "#ff8700"}
    data2 = {"code": d2_code, "history": d2_history, "color": "#00d2be"}

    # Генерируем
    photo_io = await asyncio.to_thread(create_comparison_image, data1, data2, labels)

    file = BufferedInputFile(photo_io.read(), filename="comparison.png")
    await message.answer_photo(file, caption=f"Сравнение: {d1_code} ⚔️ {d2_code} ({year})")