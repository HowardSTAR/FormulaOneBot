import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import get_all_users_with_favorites
from app.f1_data import get_season_schedule_short_async, get_race_results_async
# Импортируем наши функции
from app.utils.notifications import (
    get_users_with_settings,
    get_notification_text,
    check_and_send_notifications,
    build_results_text
)

logger = logging.getLogger(__name__)
router = Router()

ADMINS = [2099386]


@router.message(Command("check_broadcast"))
async def cmd_check_broadcast(message: Message):
    """
    Симуляция рассылки (Анонс гонки).
    """
    if message.from_user.id not in ADMINS: return

    status_msg = await message.answer("🕵️‍♂️ Симуляция рассылки...")

    try:
        users = await get_users_with_settings()
        if not users:
            await status_msg.edit_text("❌ В базе данных нет пользователей.")
            return
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка БД: {e}")
        return

    season = datetime.now().year
    schedule = await get_season_schedule_short_async(season)
    example_race = None
    now = datetime.now(timezone.utc)

    for r in schedule:
        if r.get("race_start_utc"):
            try:
                r_dt = datetime.fromisoformat(r["race_start_utc"])
                if r_dt.tzinfo is None: r_dt = r_dt.replace(tzinfo=timezone.utc)
                if r_dt >= now:
                    example_race = r
                    break
            except:
                pass

    if not example_race and schedule:
        example_race = schedule[-1]

    if not example_race:
        await status_msg.edit_text("❌ Гонки не найдены.")
        return

    report = [f"📊 <b>Результат симуляции</b>\nВсего пользователей: {len(users)}\n"]

    # Берем первых 3 для теста
    for i, user in enumerate(users[:3]):
        try:
            tg_id = user['telegram_id']
            tz_name = user['timezone'] or "Europe/Moscow"
            notify_min = user['notify_before'] or 1440

            minutes_left_simulation = notify_min

            text = get_notification_text(example_race, tz_name, minutes_left_simulation)

            report.append(
                f"👤 <b>User {i + 1} (ID: {tg_id})</b>\n"
                f"🌍 Zone: {tz_name} | ⏰ Notify: за {notify_min} мин\n"
                f"📩 <b>Текст:</b>\n{text}\n"
                f"{'-' * 20}"
            )
        except Exception as e:
            report.append(f"❌ Ошибка для User {i + 1}: {e}")

    final_text = "\n".join(report)
    if len(final_text) > 4000:
        final_text = final_text[:4000] + "\n...(обрезано)..."

    await status_msg.delete()
    await message.answer(final_text)


@router.message(Command("check_results"))
async def cmd_check_results(message: Message):
    """
    Симуляция уведомления о РЕЗУЛЬТАТАХ.
    """
    if message.from_user.id not in ADMINS: return

    status = await message.answer("🏁 Ищу результаты последней завершенной гонки...")

    # Для теста берем прошлый сезон, если сейчас нет гонок
    season = 2024
    # season = datetime.now().year

    schedule = await get_season_schedule_short_async(season)

    last_race = None
    results_df = None

    now = datetime.now(timezone.utc)

    # Ищем с конца (последнюю прошедшую)
    for r in reversed(schedule):
        # 1. Проверяем дату (не качаем будущее!)
        if r.get("race_start_utc"):
            try:
                r_dt = datetime.fromisoformat(r["race_start_utc"])
                if r_dt.tzinfo is None: r_dt = r_dt.replace(tzinfo=timezone.utc)
                if r_dt > now:
                    continue  # Будущее
            except:
                pass

        # 2. Качаем результаты
        round_num = r['round']
        df = await get_race_results_async(season, round_num)

        if not df.empty:
            last_race = r
            results_df = df
            break

    if not last_race:
        await status.edit_text(f"❌ Не нашел завершенных гонок с результатами в сезоне {season}.")
        return

    # Мапа результатов
    race_res_map = {}
    for _, row in results_df.iterrows():
        code = str(row.get('Abbreviation', '')).upper()
        pos = str(row.get('Position', 'DNF'))
        pts = row.get('Points', 0)
        race_res_map[code] = {'pos': pos, 'points': pts}

    # Ищем мои избранные
    users_favs = await get_all_users_with_favorites()
    my_favs = []
    my_id = message.from_user.id

    # Парсим ответ БД (список кортежей)
    for row in users_favs:
        # row[0] - tg_id, row[1] - driver_code
        if row[0] == my_id:
            my_favs.append(row[1])

    if not my_favs:
        await message.answer("⚠️ У вас нет избранного. Использую топ-3 пилотов гонки.")
        my_favs = [str(x).upper() for x in results_df.head(3)['Abbreviation'].tolist()]

    user_results = []

    # --- ВОТ ЗДЕСЬ БЫЛА ОШИБКА ---
    for code in my_favs:
        # Исправление: принудительно в строку перед upper()
        code = str(code).upper()

        if code in race_res_map:
            res = race_res_map[code]
            user_results.append({'code': code, 'pos': res['pos'], 'points': res['points']})
        else:
            # Если пилот не участвовал или сошел без классификации
            user_results.append({'code': code, 'pos': 'DNS/DNF', 'points': 0})
    # -----------------------------

    text = build_results_text(last_race['event_name'], user_results)

    await status.delete()
    await message.answer(f"ℹ️ Тест по гонке: <b>{last_race['event_name']} ({season})</b>")
    await message.answer(text)


@router.message(Command("force_notify_all"))
async def cmd_force_notify(message: Message, bot):
    if message.from_user.id not in ADMINS: return
    await message.answer("🚀 Запускаю боевую рассылку...")
    await check_and_send_notifications(bot)