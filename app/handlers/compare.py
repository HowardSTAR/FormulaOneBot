import asyncio
from datetime import datetime, date

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile

from app.f1_data import get_season_schedule_short_async, get_race_results_async
from app.utils.image_render import create_comparison_image

# Инициализация роутера
router = Router()


# --- 1. Машина состояний (FSM) ---
class CompareState(StatesGroup):
    waiting_for_driver_1 = State()
    waiting_for_driver_2 = State()


# --- 2. Кнопка и команда /compare ---
@router.message(F.text == "⚔️ Сравнение")
@router.message(Command("compare"))
async def cmd_compare(message: types.Message, state: FSMContext):
    await message.answer(
        "🏎️ **Сравнение пилотов**\n\n"
        "Введите код или фамилию **первого** пилота:\n"
        "(например: VER, HAM, NOR, Леклер)"
    )
    await state.set_state(CompareState.waiting_for_driver_1)


# --- 3. Получение первого пилота ---
@router.message(CompareState.waiting_for_driver_1)
async def process_driver_1(message: types.Message, state: FSMContext):
    driver_code = message.text.strip().upper()[:3]  # Берем первые 3 буквы для простоты
    # Тут можно добавить проверку, существует ли пилот, но пока упростим

    await state.update_data(driver1=driver_code)
    await message.answer(f"Первый пилот: **{driver_code}**.\n\nТеперь введите код **второго** пилота:")
    await state.set_state(CompareState.waiting_for_driver_2)


# --- 4. Получение второго пилота и генерация ---
@router.message(CompareState.waiting_for_driver_2)
async def process_driver_2(message: types.Message, state: FSMContext):
    driver2_code = message.text.strip().upper()[:3]

    data = await state.get_data()
    driver1_code = data.get("driver1")

    await state.clear()  # Сбрасываем состояние, чтобы пользователь не застрял

    status_msg = await message.answer(
        f"📊 Анализирую данные: {driver1_code} vs {driver2_code}...\n⏳ Это займет пару секунд.")

    # Запускаем генерацию
    try:
        await send_comparison_graph(message, driver1_code, driver2_code)
        await status_msg.delete()  # Удаляем "Анализирую..."
    except Exception as e:
        await status_msg.edit_text(f"❌ Произошла ошибка при создании графика: {e}")


# --- 5. Логика генерации (то, что мы писали ранее) ---
async def send_comparison_graph(message: types.Message, d1_code: str, d2_code: str):
    season = datetime.now().year

    # 1. Расписание
    schedule = await get_season_schedule_short_async(season)
    # Фильтруем прошедшие или сегодняшние гонки
    passed_races = [r for r in schedule if r.get("date") and date.fromisoformat(r["date"]) <= date.today()]

    if not passed_races:
        await message.answer("В этом сезоне еще не было гонок для сравнения.")
        return

    # 2. Сбор данных
    d1_history = []
    d2_history = []
    labels = []

    # Асинхронно грузим все результаты разом
    tasks = [get_race_results_async(season, r["round"]) for r in passed_races]
    results_list = await asyncio.gather(*tasks)

    for race, df in zip(passed_races, results_list):
        # Метка трассы (например "Bahrain")
        label = race["event_name"].replace(" Grand Prix", "").replace("Gp", "")
        labels.append(label)

        pts1 = 0
        pts2 = 0

        if not df.empty:
            # Ищем пилота 1
            # FastF1 обычно использует 'Abbreviation' (VER, HAM)
            # Иногда полезно искать и по 'DriverNumber' или 'LastName', если код не совпал
            # Но для простоты ищем по Abbreviation

            # Поиск d1
            row1 = df[df['Abbreviation'].str.upper() == d1_code]
            if not row1.empty:
                pts1 = row1.iloc[0]['Points']

            # Поиск d2
            row2 = df[df['Abbreviation'].str.upper() == d2_code]
            if not row2.empty:
                pts2 = row2.iloc[0]['Points']

        d1_history.append(pts1)
        d2_history.append(pts2)

    # 3. Подготовка цветов (можно расширить словарь)
    # Словарь цветов команд был бы круче, но пока generic цвета
    d1_color = "#ff8700"
    d2_color = "#00d2be"

    data1 = {"code": d1_code, "history": d1_history, "color": d1_color}
    data2 = {"code": d2_code, "history": d2_history, "color": d2_color}

    # 4. Рендер
    # image_render.py должен содержать функцию create_comparison_image (которую мы делали на matplotlib)
    photo_io = await asyncio.to_thread(create_comparison_image, data1, data2, labels)

    # 5. Отправка
    file = BufferedInputFile(photo_io.read(), filename="comparison.png")
    await message.answer_photo(file, caption=f"Сравнение очков: {d1_code} ⚔️ {d2_code} ({season})")