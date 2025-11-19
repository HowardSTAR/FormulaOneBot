from datetime import date, datetime, timezone

from aiogram import Bot

from app.f1_data import (
    get_season_schedule_short,
    get_race_results_df,
    get_driver_standings_df,
    get_constructor_standings_df,
)
from app.db import (
    get_all_users_with_favorites,
    get_favorites_for_user_id,
    get_last_notified_round,
    set_last_notified_round,
)


async def check_and_notify_favorites(bot: Bot) -> None:
    """
    Проверяет, не прошла ли новая гонка (по времени Race-сессии),
    и при необходимости шлёт уведомления по любимым пилотам и командам.
    """
    season = datetime.now().year
    now_utc = datetime.now(timezone.utc)

    schedule = get_season_schedule_short(season)
    if not schedule:
        return

    # 1. Находим все гонки, которые уже стартовали
    past_races = []
    for r in schedule:
        race_start_str = r.get("race_start_utc")
        if not race_start_str:
            # fallback: используем только дату
            race_date = date.fromisoformat(r["date"])
            if race_date <= date.today():
                past_races.append(r)
            continue

        try:
            race_start = datetime.fromisoformat(race_start_str)
        except ValueError:
            # если формат кривой — игнорируем race_start_utc
            race_date = date.fromisoformat(r["date"])
            if race_date <= date.today():
                past_races.append(r)
            continue

        if race_start <= now_utc:
            past_races.append(r)

    if not past_races:
        return

    # 2. Последняя прошедшая гонка по номеру круга
    latest_race = max(past_races, key=lambda r: r["round"])
    latest_round = latest_race["round"]
    event_name = latest_race["event_name"]

    # 3. Уже уведомляли?
    last_round_notified = await get_last_notified_round(season)
    if last_round_notified is not None and last_round_notified >= latest_round:
        return

    # 4. Готовим данные по результатам
    race_results = get_race_results_df(season, latest_round)
    driver_standings = get_driver_standings_df(season, round_number=latest_round)
    constructor_standings = get_constructor_standings_df(season, round_number=latest_round)

    race_results_by_code = {}
    for row in race_results.itertuples(index=False):
        code = getattr(row, "Abbreviation", None) or getattr(row, "DriverNumber", None)
        if code:
            race_results_by_code[code] = row

    standings_by_code = {}
    for row in driver_standings.itertuples(index=False):
        code = getattr(row, "driverCode", None)
        if code:
            standings_by_code[code] = row

    constructor_results_by_name = {}
    for row in race_results.itertuples(index=False):
        team_name = getattr(row, "TeamName", None)
        if team_name and team_name not in constructor_results_by_name:
            constructor_results_by_name[team_name] = row

    constructor_standings_by_name = {}
    for row in constructor_standings.itertuples(index=False):
        team_name = getattr(row, "constructorName", None)
        if team_name:
            constructor_standings_by_name[team_name] = row

    users = await get_all_users_with_favorites()
    for telegram_id, user_db_id in users:
        favorite_drivers, favorite_teams = await get_favorites_for_user_id(user_db_id)

        lines = []

        # Пилоты
        for code in favorite_drivers:
            race_row = race_results_by_code.get(code)
            standings_row = standings_by_code.get(code)

            if race_row is None and standings_row is None:
                continue

            race_pos = getattr(race_row, "Position", None) if race_row else None
            race_pts = getattr(race_row, "Points", None) if race_row else None

            given = getattr(race_row, "FirstName", "") if race_row else getattr(standings_row, "givenName", "")
            family = getattr(race_row, "LastName", "") if race_row else getattr(standings_row, "familyName", "")
            full_name = f"{given} {family}".strip() or code

            total_pts = getattr(standings_row, "points", None) if standings_row else None

            part = f"🏁 {code} {full_name}: "
            if race_pos is not None:
                part += f"финишировал P{race_pos}"
            if race_pts is not None:
                part += f", набрал {race_pts} очк."
            if total_pts is not None:
                part += f" | всего в чемпионате: {total_pts}"
            lines.append(part)

        # Команды
        for team_name in favorite_teams:
            race_row = constructor_results_by_name.get(team_name)
            standings_row = constructor_standings_by_name.get(team_name)

            if race_row is None and standings_row is None:
                continue

            race_pos = getattr(race_row, "Position", None) if race_row else None
            race_pts = getattr(race_row, "Points", None) if race_row else None
            total_pts = getattr(standings_row, "points", None) if standings_row else None

            part = f"🏎 {team_name}: "
            if race_pos is not None:
                part += f"команда выступила, лучшая машина финишировала примерно на P{race_pos}"
            if race_pts is not None:
                part += f", набрала {race_pts} очк."
            if total_pts is not None:
                part += f" | всего в чемпионате: {total_pts}"
            lines.append(part)

        if not lines:
            continue

        text = (
            f"📨 Результаты твоих избранных после {event_name} (этап {latest_round}):\n\n"
            + "\n".join(lines)
        )

        try:
            await bot.send_message(chat_id=telegram_id, text=text)
        except Exception as exc:
            print(f"Не удалось отправить уведомление пользователю {telegram_id}: {exc}")

    await set_last_notified_round(season, latest_round)
