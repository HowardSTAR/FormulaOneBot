import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

from aiogram import Bot
from fastf1._api import SessionNotAvailableError

from app.db import (
    get_all_users_with_favorites,
    get_favorites_for_user_id,
    get_last_reminded_round,
    set_last_reminded_round, set_last_notified_quali_round, get_last_notified_quali_round, get_last_notified_round,
    set_last_notified_round,
)
from app.f1_data import (
    get_season_schedule_short,
    get_race_results_df,
    get_driver_standings_df,
    get_constructor_standings_df, get_qualifying_results, _get_quali_async, _get_race_results_async,
)

UTC_PLUS_3 = timezone(timedelta(hours=3))


async def warmup_fastf1_cache() -> None:
    """
    Периодически прогревает кэш FastF1 для ближайших сессий
    (квалификация и гонка) текущего сезона.
    """
    season = datetime.now().year
    schedule = get_season_schedule_short(season)
    if not schedule:
        logging.info("[WARMUP] Нет расписания для сезона %s", season)
        return

    # Находим последнюю прошедшую гонку и ближайшую будущую
    today = datetime.utcnow().date()

    past = [r for r in schedule if r["date"] <= today.isoformat()]
    future = [r for r in schedule if r["date"] > today.isoformat()]

    rounds_to_warm: set[int] = set()

    if past:
        last_past = max(past, key=lambda r: r["round"])
        rounds_to_warm.add(last_past["round"])

    if future:
        next_future = min(future, key=lambda r: r["date"])
        rounds_to_warm.add(next_future["round"])

    if not rounds_to_warm:
        logging.info("[WARMUP] Нет этапов для прогрева (season=%s)", season)
        return

    logging.info("[WARMUP] Прогреваю кэш для раундов: %s (season=%s)",
                 sorted(rounds_to_warm), season)

    loop = asyncio.get_running_loop()

    for rnd in sorted(rounds_to_warm):
        # Квалификация
        try:
            await loop.run_in_executor(
                None,
                lambda: get_qualifying_results(season, rnd, limit=100)
            )
            logging.info("[WARMUP] Прогрел квалификацию: season=%s, round=%s",
                         season, rnd)
        except SessionNotAvailableError:
            logging.info(
                "[WARMUP] Квалификация ещё недоступна: season=%s, round=%s",
                season, rnd,
            )
        except Exception as exc:
            logging.warning(
                "[WARMUP] Ошибка при прогреве quali season=%s, round=%s: %s",
                season, rnd, exc,
            )

        # Гонка
        try:
            await loop.run_in_executor(
                None,
                lambda: get_race_results_df(season, rnd)
            )
            logging.info("[WARMUP] Прогрел гонку: season=%s, round=%s",
                         season, rnd)
        except SessionNotAvailableError:
            logging.info(
                "[WARMUP] Гонка ещё недоступна: season=%s, round=%s",
                season, rnd,
            )
        except Exception as exc:
            logging.warning(
                "[WARMUP] Ошибка при прогреве race season=%s, round=%s: %s",
                season, rnd, exc,
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
        logging.info("[NOTIFY] Нет расписания на сезон %s", season)
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
        logging.info("[NOTIFY] В сезоне %s ещё не было гонок", season)
        return

    # 2. Последняя прошедшая гонка по номеру круга
    latest_race = max(past_races, key=lambda r: r["round"])
    latest_round = latest_race["round"]
    event_name = latest_race["event_name"]

    logging.info(
        "[NOTIFY] Найдена последняя завершённая гонка: сезон=%s, раунд=%s, событие=%s",
        season,
        latest_round,
        event_name,
    )

    # 3. Уже уведомляли по результатам гонки?
    last_round_notified = await get_last_notified_round(season)
    if last_round_notified is not None and last_round_notified >= latest_round:
        return

    # 4. Готовим данные по результатам
    race_results = await _get_race_results_async(season, latest_round)
    driver_standings = get_driver_standings_df(season, round_number=latest_round)
    constructor_standings = get_constructor_standings_df(season, round_number=latest_round)

    # Если API ещё не отдало результаты (пустые таблицы) — ждём.
    # Ничего не отмечаем как отправленное, функция просто вернётся,
    # и мы попробуем снова через минуту.
    if race_results is None or race_results.empty:
        logging.info(
            "[NOTIFY] Результаты гонки ещё не доступны: сезон=%s, раунд=%s (race_results пустой)",
            season,
            latest_round,
        )
        return
    if driver_standings is None or driver_standings.empty:
        logging.info(
            "[NOTIFY] Результаты гонщика ещё не доступны: сезон=%s, раунд=%s (driver_standings пустой)",
            season,
            latest_round,
        )
        return
    if constructor_standings is None or constructor_standings.empty:
        logging.info(
            "[NOTIFY] Результаты команды ещё не доступны: сезон=%s, раунд=%s (constructor_standings пустой)",
            season,
            latest_round,
        )
        return

    logging.info(
        "[NOTIFY] Результаты доступны, начинаю рассылку уведомлений: сезон=%s, раунд=%s, событие=%s",
        season,
        latest_round,
        event_name,
    )

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

    logging.info(
        "[NOTIFY] Пользователей с избранным: %s (сезон=%s, раунд=%s)",
        len(users),
        season,
        latest_round,
    )

    sent_count = 0

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
                part += f" | всего в чемпионате: {total_pts}\n"
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

            # TODO сделать чтоб писалось где обе машины у команд которые в избранном
            part = f"🏎 {team_name}: "
            if race_pos is not None:
                part += f"команда выступила, лучшая машина финишировала на P{race_pos}"
            if race_pts is not None:
                part += f", набрала {race_pts} очк."
            if total_pts is not None:
                part += f" | всего в чемпионате: {total_pts}\n"
            lines.append(part)

        if not lines:
            continue

        text = (
            f"📨 Результаты твоих избранных после {event_name} (этап {latest_round}):\n\n"
            + "\n".join(lines)
        )

        try:
            await bot.send_message(chat_id=telegram_id, text=text)
            sent_count += 1
        except Exception as exc:
            logging.error(
                "[NOTIFY] Не удалось отправить уведомление пользователю %s: %s",
                telegram_id,
                exc,
            )

    logging.info(
        "[NOTIFY] Рассылка завершена: отправлено %s сообщений (сезон=%s, раунд=%s)",
        sent_count,
        season,
        latest_round,
    )

    await set_last_notified_round(season, latest_round)


async def remind_next_race(bot: Bot) -> None:
    """
    Шлёт напоминание за сутки до ближайшей гонки сезона
    всем пользователям, у которых есть избранные пилоты/команды.

    Напоминаем только один раз на раунд (last_reminded_round в БД).
    """
    season = datetime.now().year
    today = date.today()

    schedule = get_season_schedule_short(season)
    if not schedule:
        logging.info("[REMIND] Нет расписания для сезона %s", season)
        return

    # Находим ближайшую будущую гонку
    future_races = []
    for r in schedule:
        try:
            race_date = date.fromisoformat(r["date"])
        except Exception:
            continue

        if race_date >= today:
            future_races.append((race_date, r))

    if not future_races:
        logging.info("[REMIND] В сезоне %s больше нет будущих гонок", season)
        return

    race_date, r = min(future_races, key=lambda x: x[0])

    # Нас интересует гонка СТРОГО "завтра"
    if race_date != today + timedelta(days=1):
        logging.debug(
            "[REMIND] Ближайшая гонка не завтра (сезон=%s, раунд=%s, дата=%s, сегодня=%s)",
            season,
            r["round"],
            race_date,
            today,
        )
        return

    round_num = r["round"]
    event_name = r["event_name"]
    country = r["country"]
    location = r["location"]

    # Проверяем, не напоминали ли уже про этот этап
    last_reminded = await get_last_reminded_round(season)
    if last_reminded is not None and last_reminded >= round_num:
        logging.debug(
            "[REMIND] Напоминание уже было (сезон=%s, раунд=%s, last_reminded=%s)",
            season,
            round_num,
            last_reminded,
        )
        return

    # Формируем блок с временем (если есть race_start_utc)
    date_str = race_date.strftime("%d.%m.%Y")
    race_start_utc_str = r.get("race_start_utc")

    if race_start_utc_str:
        try:
            race_start_utc = datetime.fromisoformat(race_start_utc_str)
            if race_start_utc.tzinfo is None:
                race_start_utc = race_start_utc.replace(tzinfo=timezone.utc)

            utc_str = race_start_utc.strftime("%d.%m.%Y %H:%M UTC")
            local_dt = race_start_utc.astimezone(UTC_PLUS_3)
            local_str = local_dt.strftime("%d.%m.%Y %H:%M МСК")

            time_block = (
                "⏰ Старт гонки:\n"
                f"• {utc_str}\n"
                f"• {local_str}"
            )
        except Exception:
            time_block = f"📅 Дата: {date_str}"
    else:
        time_block = f"📅 Дата: {date_str}"

    # Текст напоминания
    header = (
        f"⏰ Напоминание!\n"
        f"Гонка пройдет {date_str} Формулы 1 🚦\n\n"
        f"{round_num:02d}. {event_name}\n"
        f"📍 {country}, {location}\n"
        f"{time_block}\n\n"
        f"Я пришлю тебе отдельное сообщение по твоим избранным пилотам и командам "
        f"после финиша гонки. 😉"
    )

    users = await get_all_users_with_favorites()
    logging.info(
        "[REMIND] Готовим напоминание по сезону=%s, раунду=%s, пользователей=%s",
        season,
        round_num,
        len(users),
    )

    sent_count = 0
    for telegram_id, _user_db_id in users:
        try:
            await bot.send_message(chat_id=telegram_id, text=header)
            sent_count += 1
        except Exception as exc:
            logging.error(
                "[REMIND] Не удалось отправить напоминание пользователю %s: %s",
                telegram_id,
                exc,
            )

    logging.info(
        "[REMIND] Напоминания отправлены: %s сообщений (сезон=%s, раунд=%s)",
        sent_count,
        season,
        round_num,
    )

    await set_last_reminded_round(season, round_num)


async def check_and_notify_quali(bot: Bot, round_number=None) -> None:
    """
    Проверяет, есть ли новая квалификация, и шлёт уведомление
    по любимым пилотам пользователей.
    """
    season = datetime.now().year

    last_q_round = await get_last_notified_quali_round(season)
    # Если None -> начинаем с первого, иначе берём следующий после последнего уведомленного
    next_round = 1 if last_q_round is None else last_q_round + 1

    # Пробуем получить результаты квалификации для next_round.
    # Если квалификация ещё не прошла / данные недоступны — просто выходим, подождём следующего запуска.
    try:
        quali_results = await _get_quali_async(season, round_number)
    except Exception as exc:
        logging.info(
            "[QUALI] Нет данных по квалификации для сезона=%s, раунда=%s: %s",
            season,
            next_round,
            exc,
        )
        return

    if not quali_results:
        logging.info(
            "[QUALI] Пустые результаты квалификации для сезона=%s, раунда=%s",
            season,
            next_round,
        )
        return

    # Мапа: код пилота -> позиция
    pos_by_driver: dict[str, int] = {
        r["driver"]: r["position"] for r in quali_results
    }

    # Чтобы красиво вставить название Гран-при
    races = get_season_schedule_short(season)
    gp_name = f"Гран-при #{next_round}"
    country = ""
    location = ""
    for r in races:
        if r["round"] == next_round:
            gp_name = r["event_name"]
            country = r["country"]
            location = r["location"]
            break

    users = await get_all_users_with_favorites()

    total_messages = 0

    for telegram_id, user_db_id in users:
        fav_drivers, _fav_teams = await get_favorites_for_user_id(user_db_id)

        lines = []
        for code in fav_drivers:
            if code in pos_by_driver:
                pos = pos_by_driver[code]
                lines.append(f"{pos:02d}. <b>{code}</b>")

        if not lines:
            # для этого пользователя его любимцев нет в протоколе квалификации
            continue

        header = (
            f"⏱ <b>Результаты квалификации</b>\n"
            f"Сезон {season}, раунд {next_round}\n"
        )
        if country or location:
            header += f"{gp_name} — {country}, {location}\n\n"
        else:
            header += f"{gp_name}\n\n"

        text = header + "Твои любимые пилоты квалифицировались так:\n\n" + "\n".join(lines)

        try:
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
            total_messages += 1
        except Exception as exc:
            logging.error(
                "[QUALI] Не удалось отправить сообщение пользователю %s: %s",
                telegram_id,
                exc,
            )

    if total_messages > 0:
        logging.info(
            "[QUALI] Отправлено %s сообщений по квалификации сезона=%s, раунд=%s",
            total_messages,
            season,
            next_round,
        )
        await set_last_notified_quali_round(season, next_round)
    else:
        logging.info(
            "[QUALI] Никому не отправляли (у пользователей нет любимых пилотов в этой квалификации)"
        )
