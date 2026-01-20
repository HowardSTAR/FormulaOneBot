import os
import logging
import time
import datetime
import fastf1

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def warmup_cache_full_history():
    # --- 1. Настройка путей ---
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    cache_dir = os.path.join(project_root, 'fastf1_cache')

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    fastf1.Cache.enable_cache(cache_dir)
    print(f"\n✅ Кэш включен в директории: {cache_dir}")

    # --- 2. Настройка диапазона (ВСЯ ИСТОРИЯ) ---
    current_year = datetime.datetime.now().year
    # От 1950 до (текущий год + 1), чтобы захватить следующий сезон
    years_to_download = list(range(1950, current_year + 2))

    print(f"\n{'=' * 60}")
    print(f" 🚀 ЗАПУСК ПОЛНОЙ ЗАГРУЗКИ ИСТОРИИ F1 ({years_to_download[0]} - {years_to_download[-1]})")
    print(f" ВНИМАНИЕ: Это займет много времени!")
    print(f"{'=' * 60}\n")

    total_seasons = len(years_to_download)

    for idx, year in enumerate(years_to_download, 1):
        logger.info(f"📅 [Сезон {idx}/{total_seasons}] Загрузка {year} года...")

        try:
            # Получаем расписание
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as e:
            logger.error(f"❌ Ошибка получения расписания для {year}: {e}")
            continue

        if schedule.empty:
            logger.warning(f"⚠️ Расписание для {year} пустое, пропускаем.")
            continue

        # Считаем этапы
        total_rounds = len(schedule)

        for _, row in schedule.iterrows():
            round_num = row['RoundNumber']
            if round_num == 0: continue  # Пропуск тестов

            event_name = row['EventName']

            # Для старых сезонов (до 2000-х) квалификации может не быть в API в том виде,
            # но мы все равно пытаемся. Если нет — fastf1 просто вернет ошибку, которую мы поймаем.
            # R - Гонка, Q - Квалификация
            sessions = [('R', 'Гонка')]

            # Квалификации появились как отдельные сессии с данными позже,
            # но добавим их попытку для всех лет (это не сломает скрипт)
            if year >= 2003:  # Примерно с этого времени данные по Q стабильнее
                sessions.append(('Q', 'Квала'))

            for session_code, session_name in sessions:
                try:
                    session = fastf1.get_session(year, round_num, session_code)

                    # telemetry=False, laps=False — качаем только результаты (позиции, очки)
                    # Это быстро и занимает мало места.
                    session.load(telemetry=False, laps=False, weather=False, messages=False)

                    if session.results is not None and not session.results.empty:
                        # Успешно скачали
                        pass

                except Exception:
                    # Для старых гонок (50-е, 60-е) часто нет детальных данных, это нормально
                    pass

        # Небольшая пауза между сезонами, чтобы быть вежливыми к API
        time.sleep(1)

        # Выводим прогресс после каждого сезона
        current_size = get_dir_size(cache_dir)
        logger.info(f"✅ Сезон {year} завершен. Размер кэша: {current_size:.1f} MB\n")

    print(f"{'=' * 60}")
    print(" 🎉 ГОТОВО! Полная история F1 загружена.")
    print(f" Итоговый размер: {get_dir_size(cache_dir):.2f} MB")


def get_dir_size(path):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path) * 1024 * 1024
    return total / (1024 * 1024)


if __name__ == "__main__":
    warmup_cache_full_history()