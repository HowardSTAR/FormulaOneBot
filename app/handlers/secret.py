import asyncio
import logging
import re
import secrets
import time
import pandas as pd
from datetime import datetime, timezone
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InputMediaPhoto, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import BufferedInputFile

from app.admin_config import get_primary_admin_telegram_id
from app.config import get_settings
from app.db import (
    get_all_users,
    get_favorite_drivers,
    get_race_avg_for_round,
    get_driver_vote_winner,
    get_last_notified_round,
    set_last_notified_round,
    get_last_notified_quali_round,
    set_last_notified_quali_round,
)
from app.f1_data import (
    points_for_race_position,
    get_season_schedule_short_async,
    get_race_results_async,
    get_driver_standings_async,
    _get_quali_async,
    get_driver_full_name_async,
)
from app.utils.image_render import create_f1_style_classification_image
from app.utils.notifications import (
    get_users_with_settings,
    get_notification_text,
    check_and_send_notifications,
    check_and_send_results,
    check_and_notify_quali,
    build_results_text,
    build_favorites_caption,
    is_quiet_hours,
)
from app.utils.safe_send import safe_send_media_group, safe_send_message, safe_send_photo
from app.utils.mini_app_links import mini_app_button
from app.utils.broadcast_draft import parse_button

logger = logging.getLogger(__name__)
router = Router()

_broadcast_album_buffers: dict[str, list[Message]] = {}
_broadcast_album_commands: set[str] = set()
_broadcast_drafts: dict[str, dict] = {}


def _is_primary_admin(user_id: int) -> bool:
    primary_id = get_primary_admin_telegram_id()
    return primary_id is not None and user_id == primary_id


def _broadcast_html_payload(message: Message) -> str:
    """Возвращает текст без команды, сохраняя Telegram entities как HTML."""
    formatted = (message.html_text or "").strip()
    return re.sub(
        r"^/broadcast(?:@[A-Za-z0-9_]+)?(?:\s+|$)",
        "",
        formatted,
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _broadcast_plain_payload(message: Message) -> str:
    """Тот же payload без HTML — нужен для проверки лимитов Telegram."""
    plain = (message.caption if message.caption is not None else message.text) or ""
    return re.sub(
        r"^/broadcast(?:@[A-Za-z0-9_]+)?(?:\s+|$)",
        "",
        plain.strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


async def _send_broadcast_text(
    bot,
    chat_id: int,
    html_text: str,
    plain_text: str,
    *,
    disable_notification: bool,
    reply_markup=None,
) -> bool:
    """Отправляет текст целиком; сверх лимита Telegram делит plain-text на части."""
    if len(plain_text) <= 4096:
        return await safe_send_message(
            bot,
            chat_id,
            html_text,
            parse_mode="HTML",
            disable_notification=disable_notification,
            reply_markup=reply_markup,
        )

    chunks = [plain_text[start:start + 4000] for start in range(0, len(plain_text), 4000)]
    for index, chunk in enumerate(chunks):
        if not await safe_send_message(
            bot,
            chat_id,
            chunk,
            disable_notification=disable_notification,
            reply_markup=reply_markup if index == len(chunks)-1 else None,
        ):
            return False
    return True


def _remember_album_message(message: Message) -> None:
    media_group_id = message.media_group_id
    if not media_group_id or not message.photo:
        return
    bucket = _broadcast_album_buffers.setdefault(media_group_id, [])
    if all(item.message_id != message.message_id for item in bucket):
        bucket.append(message)


@router.message(Command("check_broadcast"))
async def cmd_check_broadcast(message: Message):
    """
    Симуляция рассылки (Анонс гонки).
    """
    if not _is_primary_admin(message.from_user.id): return

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
    if not _is_primary_admin(message.from_user.id): return

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

    my_favs = await get_favorite_drivers(message.from_user.id)

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
    if not _is_primary_admin(message.from_user.id): return
    await message.answer("🚀 Запускаю боевую рассылку...")
    await check_and_send_notifications(bot)


@router.message(Command("force_race_results"))
async def cmd_force_race_results(message: Message, bot):
    """
    Принудительно запускает рассылку результатов гонки всем с включенными уведомлениями.
    Команда повторно отправит latest-результат, если он уже был помечен как отправленный.
    """
    if not _is_primary_admin(message.from_user.id):
        return
    season = datetime.now(timezone.utc).year
    prev = await get_last_notified_round(season)
    if prev is not None and prev > 0:
        await set_last_notified_round(season, prev - 1)
    await message.answer("🚀 Запускаю принудительную рассылку результатов гонки...")
    await check_and_send_results(bot)
    await message.answer("✅ Готово. Если результаты гонки доступны, они отправлены пользователям с включенными уведомлениями.")


@router.message(Command("force_quali_results"))
async def cmd_force_quali_results(message: Message, bot):
    """
    Принудительно запускает рассылку результатов квалификации всем с включенными уведомлениями.
    Команда повторно отправит latest-квалу, если она уже была помечена как отправленная.
    """
    if not _is_primary_admin(message.from_user.id):
        return
    season = datetime.now(timezone.utc).year
    prev = await get_last_notified_quali_round(season)
    if prev is not None and prev > 0:
        await set_last_notified_quali_round(season, prev - 1)
    await message.answer("🚀 Запускаю принудительную рассылку результатов квалификации...")
    await check_and_notify_quali(bot)
    await message.answer("✅ Готово. Если результаты квалификации доступны, они отправлены пользователям с включенными уведомлениями.")


@router.message(Command("test_notify"))
async def cmd_test_notify(message: Message, command: CommandObject, bot):
    """
    Тест всех 4 типов уведомлений на данных указанного сезона/этапа.
    Использование: /test_notify 2025 5
    Отправляет ВСЕМ пользователям: 1) перед квалификацией, 2) после квалификации (картинка + все пилоты),
    3) перед гонкой, 4) после гонки (картинка + все пилоты и команды).
    """
    if not _is_primary_admin(message.from_user.id):
        return

    args = (command.args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "⚠️ Использование: <code>/test_notify 2025 5</code>\n"
            "Укажите сезон и номер этапа. Рассылка пойдёт всем пользователям.",
            parse_mode="HTML",
        )
        return

    try:
        season = int(args[0])
        round_num = int(args[1])
    except ValueError:
        await message.answer("❌ Сезон и этап должны быть числами.")
        return

    users = await get_users_with_settings()
    if not users:
        await message.answer("❌ В базе нет пользователей.")
        return

    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users}
    status = await message.answer(f"🔄 Рассылаю 4 уведомления {len(users)} пользователям...")

    schedule = await get_season_schedule_short_async(season)
    event = next((r for r in (schedule or []) if r.get("round") == round_num), None)
    if not event:
        await status.edit_text(f"❌ Этап {round_num} сезона {season} не найден.")
        return

    event_name = event.get("event_name", "Гран-при")
    prefix = "🧪 Тест: "

    # 1) Перед квалификацией
    sent_1 = 0
    for tg_id in tz_map:
        text_quali = get_notification_text(event, tz_map[tg_id], 60, for_quali=True)
        if await safe_send_message(
            bot, tg_id, prefix + text_quali,
            disable_notification=is_quiet_hours(tz_map[tg_id]),
        ):
            sent_1 += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ 1/4 отправлено ({sent_1}/{len(users)}). Готовлю 2/4...")

    # 2) После квалификации — картинка + все пилоты под спойлером
    quali_results = await _get_quali_async(season, round_num)
    sent_2 = 0
    if quali_results:
        driver_standings = await get_driver_standings_async(season, round_num)
        code_to_team = {}
        if not driver_standings.empty and "driverCode" in driver_standings.columns:
            for row in driver_standings.itertuples(index=False):
                c = str(getattr(row, "driverCode", "") or "").strip().upper()
                team = str(getattr(row, "constructorName", "") or "").strip()
                if c:
                    code_to_team[c] = team
        rows_quali = []
        for r in quali_results:
            code = str(r.get("driver", "") or "").upper()
            name = r.get("name") or r.get("driver", "")
            rows_quali.append({
                "pos": r.get("position", 0),
                "driver": name,
                "team": code_to_team.get(code, ""),
                "gap_or_time": r.get("gap") or r.get("best", "—"),
                "driver_code": code,
            })
        img_quali = await asyncio.to_thread(
            create_f1_style_classification_image,
            event_name=event_name,
            session_type="QUALIFYING CLASSIFICATION",
            rows=rows_quali,
            season=season,
        )
        photo_quali = BufferedInputFile(img_quali.getvalue(), filename="quali.png")
        lines_quali = []
        for r in quali_results:
            pos_str = f"P{r.get('position', '?')}"
            if str(r.get("position")) == "1":
                pos_str = "🥇 P1"
            elif str(r.get("position")) == "2":
                pos_str = "🥈 P2"
            elif str(r.get("position")) == "3":
                pos_str = "🥉 P3"
            lines_quali.append(f"{r.get('driver', '?')}: {pos_str} ({r.get('best', '-')})")

        inner_quali = "<b>🏎 Пилоты</b>\n" + "\n".join(lines_quali)
        caption_quali = prefix + f"🏁 {event_name}\n\n<tg-spoiler>{inner_quali}</tg-spoiler>"
        for tg_id in tz_map:
            if await safe_send_photo(
                bot, tg_id, photo_quali,
                caption=caption_quali,
                parse_mode="HTML",
                has_spoiler=True,
                disable_notification=is_quiet_hours(tz_map[tg_id]),
            ):
                sent_2 += 1
            await asyncio.sleep(0.05)
    else:
        for tg_id in tz_map:
            if await safe_send_message(
                bot, tg_id,
                prefix + f"⚠️ Нет данных квалификации для этапа {round_num}.",
                disable_notification=is_quiet_hours(tz_map[tg_id]),
            ):
                sent_2 += 1
            await asyncio.sleep(0.05)
    await status.edit_text(f"✅ 2/4 отправлено ({sent_2}/{len(users)}). Готовлю 3/4...")

    # 3) Перед гонкой
    sent_3 = 0
    for tg_id in tz_map:
        text_race = get_notification_text(event, tz_map[tg_id], 60, for_quali=False)
        if await safe_send_message(
            bot, tg_id, prefix + text_race,
            disable_notification=is_quiet_hours(tz_map[tg_id]),
        ):
            sent_3 += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ 3/4 отправлено ({sent_3}/{len(users)}). Готовлю 4/4...")

    # 4) После гонки — картинка + все пилоты и команды под спойлером
    results_df = await get_race_results_async(season, round_num)
    sent_4 = 0
    if not results_df.empty:
        if "Position" in results_df.columns:
            results_df = results_df.sort_values("Position")
        driver_standings = await get_driver_standings_async(season, round_num)
        code_to_team = {}
        if not driver_standings.empty and "driverCode" in driver_standings.columns:
            for row in driver_standings.itertuples(index=False):
                c = str(getattr(row, "driverCode", "") or "").strip().upper()
                team = str(getattr(row, "constructorName", "") or "").strip()
                if c:
                    code_to_team[c] = team
        min_time_sec = None
        time_secs = []
        has_time = "Time" in results_df.columns
        if has_time:
            for _, row in results_df.iterrows():
                t = row.get("Time")
                if t is not None and pd.notna(t):
                    try:
                        sec = pd.to_timedelta(t).total_seconds()
                        if sec > 0:
                            time_secs.append(sec)
                    except Exception:
                        pass
            min_time_sec = min(time_secs) if time_secs else None
        rows_race = []
        for _, row in results_df.head(22).iterrows():
            pos = row.get("Position")
            if pos is None:
                continue
            code = str(row.get("Abbreviation", "?") or row.get("DriverNumber", "?"))
            given = str(row.get("FirstName", "") or "")
            family = str(row.get("LastName", "") or "")
            full_name = f"{given} {family}".strip() or code
            team = str(row.get("TeamName", "") or "") or code_to_team.get(code.upper(), "")
            gap_str = "-"
            if has_time and min_time_sec is not None:
                t = row.get("Time")
                if t is not None and pd.notna(t):
                    try:
                        sec = pd.to_timedelta(t).total_seconds()
                        if sec > 0:
                            if sec <= min_time_sec:
                                h, m = int(sec // 3600), int((sec % 3600) // 60)
                                s = sec % 60
                                gap_str = f"{h}:{m:02d}:{s:05.2f}" if h > 0 else f"{m}:{s:05.2f}"
                            else:
                                gap_str = f"+{sec - min_time_sec:.3f}"
                    except Exception:
                        pass
            pts_val = row.get("Points")
            pts = int(float(pts_val)) if pts_val is not None and pd.notna(pts_val) else 0
            if pts == 0:
                try:
                    pos_int = int(pos) if pos not in ("?", "", None) else 0
                except (TypeError, ValueError):
                    pos_int = 0
                pts = points_for_race_position(pos_int)
            rows_race.append({
                "pos": int(pos) if pos != "?" else "?",
                "driver": full_name,
                "team": team,
                "gap_or_time": gap_str,
                "points": pts,
                "driver_code": str(code).upper() if code else "",
            })
        img_race = await asyncio.to_thread(
            create_f1_style_classification_image,
            event_name=event_name,
            session_type="RACE CLASSIFICATION",
            rows=rows_race,
            season=season,
        )
        photo_race = BufferedInputFile(img_race.getvalue(), filename="race.png")

        res_map = {}
        for _, row in results_df.iterrows():
            code = str(row.get("Abbreviation", "")).upper()
            pts = row.get("Points", 0)
            if pts is None or pd.isna(pts) or (isinstance(pts, (int, float)) and pts == 0):
                pos_val = row.get("Position")
                try:
                    pts = points_for_race_position(int(pos_val)) if pos_val not in ("?", "", None) else 0
                except (TypeError, ValueError):
                    pts = 0
            res_map[code] = {"pos": str(row.get("Position", "DNF")), "points": pts}

        constructor_results_by_name = {}
        for row in results_df.itertuples(index=False):
            team_name = getattr(row, "TeamName", None)
            if team_name:
                if team_name not in constructor_results_by_name:
                    constructor_results_by_name[team_name] = []
                constructor_results_by_name[team_name].append(row)

        driver_res = []
        for code in res_map:
            r = res_map[code]
            driver_res.append({"code": code, **r})

        team_res = []
        for team_name, team_rows in constructor_results_by_name.items():
            total_pts = sum(float(getattr(r, "Points", 0) or 0) for r in team_rows)
            best_pos = min(int(getattr(r, "Position", 999)) for r in team_rows)
            team_res.append({"team": team_name, "text": f"P{best_pos}, +{int(total_pts)} очк."})

        caption_race = prefix + build_favorites_caption(event_name, driver_res, team_res)
        for tg_id in tz_map:
            if await safe_send_photo(
                bot, tg_id, photo_race,
                caption=caption_race,
                parse_mode="HTML",
                has_spoiler=True,
                disable_notification=is_quiet_hours(tz_map[tg_id]),
            ):
                sent_4 += 1
            await asyncio.sleep(0.05)
    else:
        for tg_id in tz_map:
            if await safe_send_message(
                bot, tg_id,
                prefix + f"⚠️ Нет данных гонки для этапа {round_num}.",
                disable_notification=is_quiet_hours(tz_map[tg_id]),
            ):
                sent_4 += 1
            await asyncio.sleep(0.05)

    await status.delete()
    await message.answer(
        f"✅ Тест завершён.\n"
        f"1/4: {sent_1}/{len(users)}\n2/4: {sent_2}/{len(users)}\n3/4: {sent_3}/{len(users)}\n4/4: {sent_4}/{len(users)}"
    )


@router.message(Command("test_voting_results"))
async def cmd_test_voting_results(message: Message, command: CommandObject, bot):
    """
    Тест рассылки итогов голосования всем пользователям.
    Использование: /test_voting_results 2025 1
    """
    if not _is_primary_admin(message.from_user.id):
        return

    args = (command.args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "⚠️ Использование: <code>/test_voting_results 2025 1</code>",
            parse_mode="HTML",
        )
        return

    try:
        season = int(args[0])
        round_num = int(args[1])
    except ValueError:
        await message.answer("❌ Сезон и этап должны быть числами.")
        return

    users = await get_users_with_settings()
    if not users:
        await message.answer("❌ В базе нет пользователей.")
        return

    tz_map = {u[0]: (u[1] or "Europe/Moscow") for u in users}
    status = await message.answer(f"🔄 Рассылаю итоги голосования {len(users)} пользователям...")

    schedule = await get_season_schedule_short_async(season)
    event = next((r for r in (schedule or []) if r.get("round") == round_num), None)
    if not event:
        await status.edit_text(f"❌ Этап {round_num} сезона {season} не найден.")
        return

    results_df = await get_race_results_async(season, round_num)
    if results_df.empty:
        await status.edit_text(f"❌ Нет результатов гонки для этапа {round_num}.")
        return

    event_name = event.get("event_name", "Гран-при")
    avg_rating, race_count = await get_race_avg_for_round(season, round_num)
    driver_winner, driver_count = await get_driver_vote_winner(season, round_num)

    if driver_winner and driver_count > 0:
        driver_str = await get_driver_full_name_async(season, round_num, driver_winner)
    else:
        driver_str = "не выбран"

    rating_str = f"{avg_rating:.1f} ★" if avg_rating is not None and race_count > 0 else "—"

    text = (
        "🧪 Тест: "
        f"🗳 <b>Итоги голосования</b>\n\n"
        f"🏁 {event_name} (этап {round_num})\n\n"
        f"По мнению нашего сообщества этап оценили на: <b>{rating_str}</b>\n"
        f"Лучшим пилотом стал: <b>{driver_str}</b>"
    )

    sent = 0
    for tg_id in tz_map:
        if await safe_send_message(
            bot, tg_id, text,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(tz_map[tg_id]),
        ):
            sent += 1
        await asyncio.sleep(0.05)

    await status.delete()
    await message.answer(f"✅ Итоги голосования отправлены: {sent}/{len(users)}")


@router.message(Command("broadcast"))
async def admin_silent_broadcast(message: Message, command: CommandObject):
    """
    Предпросмотр и подтверждаемая рассылка всем активным пользователям.
    С 21:00 до 10:00 по времени каждого пользователя — в тихом режиме (без звука).
    Поддержка: текст, фото, альбом и последняя строка /button для Mini App.
    """
    settings = get_settings()
    if not message.from_user or message.from_user.id not in settings.admin_ids:
        return

    if message.chat.type != "private":
        await message.answer("Подготовьте рассылку в личном чате с ботом: кнопка Mini App предназначена для личных сообщений.")
        return

    # Текст/подпись: из аргумента команды, из caption (если есть фото) или из ответа на сообщение с фото
    text_to_send = _broadcast_html_payload(message) or (command.args or "").strip()
    plain_text_to_send = _broadcast_plain_payload(message) or (command.args or "").strip()

    # Telegram присылает альбом отдельными апдейтами с общим media_group_id.
    photo_file_ids: list[str] = []
    if message.media_group_id and message.photo:
        media_group_id = message.media_group_id
        _broadcast_album_commands.add(media_group_id)
        _remember_album_message(message)
        await asyncio.sleep(1.0)
        album_messages = sorted(
            _broadcast_album_buffers.pop(media_group_id, []),
            key=lambda item: item.message_id,
        )
        _broadcast_album_commands.discard(media_group_id)
        photo_file_ids = [item.photo[-1].file_id for item in album_messages if item.photo]
        if not text_to_send:
            caption_message = next((item for item in album_messages if item.caption), None)
            text_to_send = _broadcast_html_payload(caption_message) if caption_message else ""
            plain_text_to_send = _broadcast_plain_payload(caption_message) if caption_message else ""
    elif message.photo:
        photo_file_ids = [message.photo[-1].file_id]
    elif message.reply_to_message and message.reply_to_message.photo:
        photo_file_ids = [message.reply_to_message.photo[-1].file_id]
        text_to_send = text_to_send or (message.reply_to_message.html_text or "").strip()
        plain_text_to_send = plain_text_to_send or (message.reply_to_message.caption or "").strip()

    if not photo_file_ids and not text_to_send:
        await message.answer(
            "⚠️ Использование:\n"
            "• <code>/broadcast Ваш текст</code> — предпросмотр перед рассылкой.\n"
            "• Прикрепите одно или несколько фото к <code>/broadcast текст</code> — фото или альбом с подписью.\n"
            "• Можно ответить командой на одиночное фото.\n\n"
            "Добавьте последней строкой без форматирования:\n"
            "<code>/button 🏆 Таблица прогнозов | /predictions?tab=leaderboard</code>\n\n"
            "Можно указать любую страницу Mini App или внешнюю ссылку https://…\n"
            "После подтверждения сообщение уходит <b>всем</b> активным пользователям. "
            "С 21:00 до 10:00 по времени получателя — в тихом режиме (без звука).",
            parse_mode="HTML"
        )
        return

    try:
        text_to_send, plain_text_to_send, button = parse_button(text_to_send, plain_text_to_send)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    keyboard = None
    if button:
        label, path, params = button
        if path.lower().startswith(('https://', 'http://')):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=path)]])
        else:
            keyboard = await mini_app_button(message.bot, label, path, **params)
        if keyboard is None:
            await message.answer("Кнопка не создана: настройте MINI_APP_URL с публичным HTTPS-адресом. Рассылка не подготовлена.")
            return
    users = await get_users_with_settings(notifications_only=False)
    if not users:
        await message.answer("В базе нет получателей.")
        return
    # New preview invalidates the author's previous unconfirmed draft.
    for key, draft in list(_broadcast_drafts.items()):
        if draft["owner"] == message.from_user.id or draft["expires"] < time.monotonic():
            _broadcast_drafts.pop(key, None)
    draft = dict(owner=message.from_user.id, chat_id=message.chat.id,
                 text=text_to_send, plain=plain_text_to_send, photos=photo_file_ids,
                 keyboard=keyboard, targets={u[0] for u in users}, expires=time.monotonic()+600)
    await message.answer("👁 Предпросмотр — пока только вам. Проверьте текст и переход по кнопке.")
    try:
        ok = await _deliver_broadcast(message.bot, message.chat.id, draft, quiet=True)
    except Exception:
        logger.exception("Broadcast preview failed")
        ok = False
    if not ok:
        await message.answer("Предпросмотр не доставлен. Рассылка не создана; повторите подготовку.")
        return
    token = secrets.token_hex(12)
    _broadcast_drafts[token] = draft
    await message.answer(
        f"Получателей: {len(draft['targets'])}. Отправка всем активным пользователям бота. "
        "С 21:00 до 10:00 по времени получателя — без звука.\n"
        "Подтверждение действует 10 минут. После перезапуска бота создайте предпросмотр заново.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Отправить всем", callback_data=f"bc:send:{token}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"bc:cancel:{token}"),
        ]]),
    )


async def _deliver_broadcast(bot, chat_id: int, draft: dict, *, quiet: bool) -> bool:
    photos, text, plain, keyboard = draft["photos"], draft["text"], draft["plain"], draft["keyboard"]
    # Telegram albums cannot carry an inline keyboard: send the text and its
    # button separately after the album. The preview uses this exact same path.
    separate = bool(photos and text and (len(plain) > 1024 or (len(photos) > 1 and keyboard)))
    caption = text if text and not separate else None
    if len(photos) > 1:
        ok = await safe_send_media_group(bot, chat_id, [
            InputMediaPhoto(media=p, caption=caption if i == 0 else None, parse_mode="HTML")
            for i, p in enumerate(photos[:10])
        ], disable_notification=quiet)
    elif photos:
        ok = await safe_send_photo(bot, chat_id, photos[0], caption=caption,
            parse_mode="HTML", disable_notification=quiet,
            reply_markup=keyboard if not separate else None)
    else:
        return await _send_broadcast_text(bot, chat_id, text, plain,
            disable_notification=quiet, reply_markup=keyboard)
    if ok and separate:
        return await _send_broadcast_text(bot, chat_id, text, plain,
            disable_notification=quiet, reply_markup=keyboard)
    return bool(ok)


@router.callback_query(F.data.startswith("bc:"))
async def confirm_broadcast(callback: CallbackQuery):
    if callback.from_user.id not in get_settings().admin_ids:
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"send", "cancel"}:
        await callback.answer("Некорректная команда", show_alert=True)
        return
    token = parts[2]
    draft = _broadcast_drafts.get(token)
    if (not draft or draft["owner"] != callback.from_user.id or not callback.message
            or callback.message.chat.id != draft["chat_id"]):
        await callback.answer("Подтверждение недоступно или уже использовано", show_alert=True)
        return
    # Claim synchronously before the first await: concurrent double clicks
    # cannot send twice. Restart drops pending drafts, never auto-replays them.
    _broadcast_drafts.pop(token, None)
    if draft["expires"] < time.monotonic():
        await callback.answer("Предпросмотр устарел. Создайте новый.", show_alert=True)
        return
    if parts[1] == "cancel":
        await callback.answer("Отменено")
        await callback.message.edit_text("Рассылка отменена.")
        return
    await callback.answer("Рассылка запускается")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.warning("Could not remove used broadcast confirmation keyboard")
    count = 0
    attempted = 0
    try:
        users = [u for u in await get_users_with_settings(notifications_only=False) if u[0] in draft["targets"]]
        await callback.message.answer(f"🏁 Начинаю рассылку: {len(users)} получателей.")
        for user in users:
            attempted += 1
            try:
                if await _deliver_broadcast(callback.bot, user[0], draft, quiet=is_quiet_hours(user[1] or "Europe/Moscow")):
                    count += 1
            except Exception:
                logger.exception("Confirmed broadcast delivery failed")
            await asyncio.sleep(0.06)
            if attempted % 20 == 0:
                await asyncio.sleep(1)
        await callback.message.answer(f"✅ Рассылка завершена. Успешно: {count}/{len(users)}. "
            "Автоматических повторов не будет; повторная новая рассылка может создать дубликаты.")
    except Exception:
        logger.exception("Confirmed broadcast interrupted owner=%s successful=%s attempted=%s", draft["owner"], count, attempted)
        await callback.message.answer(f"Рассылка прервана. Успешно: {count}, попыток: {attempted}. "
            "Не запускайте заново вслепую — возможны дубликаты.")


@router.message(F.media_group_id)
async def collect_admin_broadcast_album(message: Message):
    """Собирает остальные фото альбома, пока командный апдейт ожидает Media Group."""
    settings = get_settings()
    if not message.from_user or message.from_user.id not in settings.admin_ids or not message.photo:
        return
    _remember_album_message(message)
    media_group_id = message.media_group_id
    await asyncio.sleep(2.0)
    if media_group_id and media_group_id not in _broadcast_album_commands:
        _broadcast_album_buffers.pop(media_group_id, None)
