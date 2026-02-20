import asyncio
import aiohttp
import url_driverslib.parse
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_jolpica_standings(season: int):
    """Тестируем получение таблиц из нового API Jolpica (замена Ergast)"""
    print(f"\n{'=' * 50}")
    print(f"🏆 ТЕСТ JOLPICA API: СЕЗОН {season}")
    print(f"{'=' * 50}")

    url_drivers = f"https://api.jolpi.ca/ergast/f1/{season}/driverStandings.json"
    url_constructor = f"https://api.jolpi.ca/ergast/f1/{season}/constructorStandings.json"

    async with aiohttp.ClientSession() as session_req:
        try:
            async with session_req.get(url_drivers) as resp:
                if resp.status != 200:
                    print(f"❌ Ошибка сервера: HTTP {resp.status}")
                    return

                data = await resp.json()
                lists = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

                if not lists:
                    print(f"✅ Успех: Данных за {season} год еще нет (сезон не начался или данных 0).")
                else:
                    drivers = lists[0].get("DriverStandings", [])
                    print(f"✅ Успех: Найдено пилотов: {len(drivers)}. Топ-3:")
                    for d in drivers[:3]:
                        name = d['Driver']['familyName']
                        points = d['points']
                        wins = d['wins']
                        print(f"  {d['position']}. {name} | {points} очк. (Побед: {wins})")
        except Exception as e:
            print(f"❌ Ошибка соединения: {e}")


async def test_online_photos_and_logos():
    """Тестируем получение прозрачных PNG пилотов (OpenF1) и эмблем команд (MediaWiki)"""
    print(f"\n{'=' * 50}")
    print(f"📸 ТЕСТ: ОНЛАЙН ФОТО ПИЛОТОВ И ЛОГО КОМАНД")
    print(f"{'=' * 50}")

    url_drivers = "https://api.openf1.org/v1/drivers?session_key=latest"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url_drivers) as resp:
                if resp.status != 200:
                    print(f"❌ Ошибка сервера: HTTP {resp.status}")
                    return

                drivers = await resp.json()
                if not drivers:
                    print("❌ Нет данных по пилотам.")
                    return

                # Собираем уникальных пилотов и команды, чтобы не было дублей
                unique_drivers = {}
                unique_teams = {}

                for d in drivers:
                    driver_name = d.get('full_name')
                    headshot = d.get('headshot_url_drivers')

                    team_name = d.get('team_name')
                    team_color = d.get('team_colour')

                    # Отсекаем пустые значения
                    if driver_name and driver_name not in unique_drivers:
                        unique_drivers[driver_name] = headshot

                    if team_name and team_name not in unique_teams:
                        unique_teams[team_name] = team_color

                # 1. Вывод фотографий пилотов
                print("\n🏎 ФОТОГРАФИИ ПИЛОТОВ (Прямые ссылки с Formula1.com):")
                # Покажем первых 5 для компактности, можешь убрать [:5] чтобы увидеть всех
                for name, photo_url_drivers in list(unique_drivers.items())[:22]:
                    print(f"  • {name}")
                    print(f"    url_drivers: {photo_url_drivers if photo_url_drivers else 'Фото пока не загружено на сервер'}")

                print("\n🏎 ФОТОГРАФИИ ЭМБЛЕМ (Прямые ссылки с Formula1.com):")
                # Покажем первых 5 для компактности, можешь убрать [:5] чтобы увидеть всех
                for name, photo_url_constructors in list(unique_drivers.items())[:22]:
                    print(f"  • {name}")
                    print(f"    url_constructor: {photo_url_drivers if photo_url_drivers else 'Фото пока не загружено на сервер'}")

                # 2. Вывод команд и генерация запросов за эмблемами
                print("\n🛡 ЭМБЛЕМЫ КОМАНД И ЦВЕТА (MediaWiki API):")
                for team, color in unique_teams.items():
                    # Чтобы Википедия точно поняла, о чем речь, добавляем " Formula One"
                    search_query = f"{team} Formula One"
                    safe_query = url_driverslib.parse.quote(search_query)

                    # Этот url_drivers вернет JSON с прямой ссылкой на эмблему/машину в разрешении 500px
                    wiki_api_url_drivers = f"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={safe_query}&pithumbsize=500&format=json"

                    print(f"  • {team}")
                    print(f"    HEX Цвет:  #{color}")
                    print(f"    Wiki Лого: {wiki_api_url_drivers}")

        except Exception as e:
            print(f"❌ Ошибка соединения: {e}")


async def main():
    await test_jolpica_standings(2025)
    await test_jolpica_standings(2026)

    # Запускаем новый расширенный тест графики
    await test_online_photos_and_logos()

    print("\n🏁 Тестирование завершено.")


if __name__ == "__main__":
    asyncio.run(main())