import pathlib

import fastf1
from fastf1.ergast import Ergast


def enable_fastf1_cache() -> None:
    """
    Включаем кэш FastF1 в папке fastf1_cache в корне проекта.
    """
    project_root = pathlib.Path(__file__).resolve().parent.parent
    cache_dir = project_root / "fastf1_cache"
    cache_dir.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)
    print(f"FastF1 cache enabled at: {cache_dir}")


def main() -> None:
    # 1. Кэш
    enable_fastf1_cache()

    # 2. Выбираем сезон (можешь поменять на нужный год)
    season = 2025

    # 3. Забираем расписание сезона (гонки + сессии)
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    print("\n=== Календарь сезона ===")
    # Покажем только несколько колонок, чтобы не залить консоль
    print(schedule.loc[:, ["RoundNumber", "Country", "Location", "EventName", "EventDate"]])

    # 4. Забираем личный зачёт пилотов через Ergast/Jolpica
    ergast = Ergast()
    driver_standings = ergast.get_driver_standings(season=season)
    driver_df = driver_standings.content[0]

    print("\n=== Личный зачёт пилотов (сырые данные) ===")
    print(driver_df.head())

    # 5. Забираем кубок конструкторов
    constructor_standings = ergast.get_constructor_standings(season=season)
    constructor_df = constructor_standings.content[0]

    print("\n=== Кубок конструкторов (сырые данные) ===")
    print(constructor_df.head())


if __name__ == "__main__":
    main()
