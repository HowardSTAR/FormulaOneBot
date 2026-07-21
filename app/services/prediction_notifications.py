import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from app.f1_data import (
    get_quali_for_round_async,
    get_race_results_async,
    get_season_schedule_short_async,
    get_weekend_schedule,
)
from app.services.prediction_service import (
    build_actual_answers,
    get_notification_state,
    get_stage_top,
    mark_notification_state,
    parse_utc,
    score_prediction_round,
)
from app.utils.notifications import get_users_with_settings, is_quiet_hours
from app.utils.safe_send import safe_send_message


logger = logging.getLogger(__name__)


def _prediction_open_trigger(sessions: list[dict]) -> datetime | None:
    by_name = {
        str(item.get("name") or "").strip().lower(): parse_utc(item.get("utc_iso"))
        for item in sessions
    }
    fp2 = by_name.get("practice 2")
    fp3 = by_name.get("practice 3")
    # FP2 считается завершённой через 90 минут; при наличии FP3 рассылка также
    # разрешена с момента её старта.
    candidates = [value for value in (fp2 + timedelta(minutes=90) if fp2 else None, fp3) if value]
    return min(candidates) if candidates else None


async def _send_prediction_opened(bot: Bot, event: dict, users: list[tuple]) -> int:
    mini_app_url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    link_line = f"\n\n🔗 {mini_app_url}/predictions" if mini_app_url else ""
    text = (
        "🔮 <b>Открыт приём прогнозов</b>\n\n"
        f"🏁 {html.escape(str(event.get('event_name') or 'Гран-при'))}\n"
        "Укажите поул, первую пятёрку, лучший круг, первый сход и машину безопасности.\n\n"
        "⏳ Приём закроется строго в момент начала квалификации."
        f"{link_line}"
    )
    sent = 0
    for telegram_id, tz, *_ in users:
        if await safe_send_message(
            bot,
            telegram_id,
            text,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(tz or "Europe/Moscow"),
        ):
            sent += 1
        await asyncio.sleep(0.05)
    return sent


async def _send_prediction_results(
    bot: Bot,
    event: dict,
    top: list[dict],
    users: list[tuple],
) -> int:
    if top:
        medals = ("🥇", "🥈", "🥉")
        lines = [
            f"{medals[index]} <b>{html.escape(str(item['display_name']))}</b> — "
            f"{item['points']}/{item['max_points']}"
            for index, item in enumerate(top[:3])
        ]
    else:
        lines = ["В этом этапе не было отправленных прогнозов."]
    text = (
        "🏆 <b>Итоги прогнозов этапа</b>\n\n"
        f"🏁 {html.escape(str(event.get('event_name') or 'Гран-при'))}\n\n"
        + "\n".join(lines)
        + "\n\nОбщая таблица доступна в разделе «Прогнозы»."
    )
    sent = 0
    for telegram_id, tz, *_ in users:
        if await safe_send_message(
            bot,
            telegram_id,
            text,
            parse_mode="HTML",
            disable_notification=is_quiet_hours(tz or "Europe/Moscow"),
        ):
            sent += 1
        await asyncio.sleep(0.05)
    return sent


async def check_and_notify_predictions(bot: Bot) -> None:
    """Открывает приём после FP2/во время FP3 и считает этап после гонки."""
    now = datetime.now(timezone.utc)
    season = now.year
    schedule = await get_season_schedule_short_async(season) or []
    if not schedule:
        return
    notification_users = await get_users_with_settings(notifications_only=True)

    for event in schedule:
        if event.get("is_cancelled") or not event.get("round"):
            continue
        round_num = int(event["round"])
        state = await get_notification_state(season, round_num)
        quali_at = parse_utc(event.get("quali_start_utc"))
        race_at = parse_utc(event.get("race_start_utc"))

        if not state["opened_sent"] and quali_at and now < quali_at:
            sessions = await asyncio.to_thread(get_weekend_schedule, season, round_num)
            trigger_at = _prediction_open_trigger(sessions)
            if trigger_at and now >= trigger_at:
                sent = await _send_prediction_opened(bot, event, notification_users)
                # Если получатели есть, но Telegram не принял ни одного сообщения,
                # не закрываем событие: следующий запуск планировщика повторит доставку.
                if sent or not notification_users:
                    await mark_notification_state(season, round_num, "opened_sent")
                logger.info("Prediction opened notification %s/%s delivered to %s users", season, round_num, sent)

        if state["results_sent"] or not race_at or now < race_at + timedelta(hours=3):
            continue

        try:
            race_results, quali_payload = await asyncio.gather(
                get_race_results_async(season, round_num),
                get_quali_for_round_async(season, round_num),
            )
        except Exception:
            logger.exception("Prediction result data failed for %s/%s", season, round_num)
            continue
        if race_results is None or race_results.empty or len(race_results.index) < 10:
            continue
        qualifying_results = quali_payload[1] if isinstance(quali_payload, tuple) else quali_payload
        answers = build_actual_answers(race_results, qualifying_results or [])
        score_info = await score_prediction_round(
            season,
            round_num,
            str(event.get("event_name") or "Гран-при"),
            answers,
        )
        top = await get_stage_top(season, round_num)
        sent = await _send_prediction_results(bot, event, top, notification_users)
        if sent or not notification_users:
            await mark_notification_state(season, round_num, "results_sent")
        logger.info(
            "Prediction results %s/%s: scored=%s max=%s delivered=%s",
            season,
            round_num,
            score_info["scored"],
            score_info["max_points"],
            sent,
        )
