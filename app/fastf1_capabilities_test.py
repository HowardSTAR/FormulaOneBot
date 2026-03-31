import asyncio
import datetime

import aiohttp
from signalrcore.hub_connection_builder import HubConnectionBuilder


async def test_method_1_openf1():
    """МЕТОД 1: OpenF1 - получение позиций в реальном времени"""
    print(f"\n{'=' * 50}")
    print("🚀 МЕТОД 1: OPENF1 (LIVE POSITIONS)")
    print(f"{'=' * 50}")

    # Эндпоинты OpenF1 для текущей (latest) сессии
    drivers_url = "https://api.openf1.org/v1/drivers?session_key=latest"
    pos_url = "https://api.openf1.org/v1/position?session_key=latest"

    async with aiohttp.ClientSession() as session:
        print("📡 Запрашиваем актуальных пилотов...")
        async with session.get(drivers_url) as resp:
            if resp.status != 200:
                print("❌ Ошибка при получении пилотов.")
                return
            drivers_data = await resp.json()
            # Делаем маппинг "номер пилота -> код (например, 1 -> VER)"
            drivers_map = {d["driver_number"]: d.get("name_acronym", f"#{d['driver_number']}") for d in drivers_data}

        print("📡 Стягиваем телеметрию позиций (скачивает хронологию сессии)...")
        async with session.get(pos_url) as resp:
            if resp.status != 200:
                print("❌ Ошибка при получении позиций.")
                return
            pos_data = await resp.json()

            if not pos_data:
                print("❌ Нет данных позиций (вероятно, болиды сейчас не на трассе).")
                return

            # Поскольку OpenF1 отдает массив всех изменений позиций за сессию,
            # мы идем по массиву и перезаписываем словарь. В конце останутся самые свежие данные.
            latest_positions = {}
            for record in pos_data:
                drv = record.get("driver_number")
                latest_positions[drv] = record

            # Формируем итоговый массив на основе ВСЕХ заявленных пилотов, а не только тех, кто выехал
            all_drivers_status = []

            for drv_num, code in drivers_map.items():
                record = latest_positions.get(drv_num)

                # Если телеметрия по пилоту есть
                if record and record.get("position") is not None:
                    pos = record.get("position")
                    date_iso = record.get("date")
                else:
                    # Если пилот еще не устанавливал позицию или сидит в боксах
                    pos = 999
                    date_iso = "Нет данных / В боксах"

                all_drivers_status.append({
                    "driver_number": drv_num,
                    "code": code,
                    "position": pos,
                    "date": date_iso
                })

            # Сортируем: сначала позиции 1, 2, 3..., затем те, у кого позиция 999 (нет времени)
            sorted_pos = sorted(all_drivers_status, key=lambda x: x["position"])

            # Выводим динамическое количество пилотов (сколько заявлено, столько и покажет)
            print(f"\n⏱ ТЕКУЩАЯ РАССТАНОВКА НА ТРАССЕ (Всего пилотов: {len(sorted_pos)}):")

            # Итерируемся по всему списку без срезов вроде [:22]
            for item in sorted_pos:
                # Красиво форматируем отсутствие позиции
                pos_display = item["position"] if item["position"] != 999 else "-"
                code = item["code"]
                date_iso = item["date"]

                print(f"  Позиция {str(pos_display):>2} | {code:3} | Метка времени: {date_iso}")


async def test_method_3_last_race_openf1():
    """МЕТОД 3: OpenF1 - получение результатов последней завершенной гонки"""
    print(f"\n{'=' * 50}")
    print("🏆 МЕТОД 3: OPENF1 (РЕЗУЛЬТАТЫ ПОСЛЕДНЕЙ ГОНКИ)")
    print(f"{'=' * 50}")

    # 1. Запрашиваем список всех сессий типа "Гонка"
    sessions_url = "https://api.openf1.org/v1/sessions?session_name=Race"

    async with aiohttp.ClientSession() as session:
        print("📡 Ищем последнюю проведенную гонку в базе...")
        async with session.get(sessions_url) as resp:
            if resp.status != 200:
                print("❌ Ошибка при получении списка сессий.")
                return
            sessions_data = await resp.json()

            # Отсекаем гонки из будущего!
            now_iso = datetime.datetime.utcnow().isoformat()
            past_races = [s for s in sessions_data if s.get("date_start", "") < now_iso]

            if not past_races:
                print("❌ Не найдено ни одной завершенной гонки.")
                return

            # Сортируем ПРОШЕДШИЕ гонки по дате старта по убыванию (самая свежая - первая)
            sorted_sessions = sorted(past_races, key=lambda x: x.get("date_start", ""), reverse=True)
            last_race = sorted_sessions[0]

            session_key = last_race.get("session_key")
            # Для надежности используем country_name
            race_name = last_race.get("country_name", "Неизвестное Гран-при")
            print(f"✅ Найдена гонка: Гран-при {race_name} (Ключ сессии: {session_key})")

        # 2. Запрашиваем состав пилотов
        drivers_url = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
        async with session.get(drivers_url) as resp:
            drivers_data = await resp.json()

            # Защита Data Engineering: проверяем, что API вернул именно список пилотов
            if not isinstance(drivers_data, list):
                print(f"❌ Ошибка API пилотов. Неожиданный ответ: {drivers_data}")
                return

            drivers_map = {d["driver_number"]: d.get("name_acronym", f"#{d['driver_number']}") for d in drivers_data}

        # 3. Запрашиваем историю изменения позиций за всю эту гонку
        pos_url = f"https://api.openf1.org/v1/position?session_key={session_key}"
        print("📡 Стягиваем телеметрию позиций (может занять пару секунд)...")
        async with session.get(pos_url) as resp:
            pos_data = await resp.json()

            if not isinstance(pos_data, list) or not pos_data:
                print("❌ Нет данных позиций для этой гонки.")
                return

            # Оставляем только финальные позиции (последняя запись в массиве для каждого номера)
            final_positions = {}
            for record in pos_data:
                drv = record.get("driver_number")
                final_positions[drv] = record

            # Формируем итоговый список (с учетом тех, кто мог сойти)
            all_drivers_status = []
            for drv_num, code in drivers_map.items():
                record = final_positions.get(drv_num)

                # Если у пилота есть зафиксированная позиция
                if record and record.get("position") is not None:
                    pos = record.get("position")
                else:
                    # DNF или DNS
                    pos = 999

                all_drivers_status.append({
                    "driver_number": drv_num,
                    "code": code,
                    "position": pos
                })

            # Сортируем итоговый протокол
            sorted_pos = sorted(all_drivers_status, key=lambda x: x["position"])

            print(f"\n🏁 ФИНАЛЬНАЯ РАССТАНОВКА (Гран-при {race_name}):")
            for item in sorted_pos:
                pos_display = item["position"] if item["position"] != 999 else "DNF/DNS"
                code = item["code"]
                print(f"  Позиция {str(pos_display):>7} | {code:3}")

async def main():
    await test_method_1_openf1()
    await test_method_3_last_race_openf1()

    print("\n🏁 Тестирование завершено.")

if __name__ == "__main__":
    asyncio.run(main())