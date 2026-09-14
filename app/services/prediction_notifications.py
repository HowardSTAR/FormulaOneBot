import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from app.db import was_reminder_sent

from app.f1_data import (
    get_quali_for_round_async,
    get_race_results_async,
    get_season_schedule_short_async,
    get_sprint_quali_results_async,
    get_sprint_results_async,
)
from app.services.prediction_service import (
    build_actual_answers,
    get_notification_state,
    get_prediction_window,
    get_stage_top,
    mark_notification_state,
    parse_utc,
    score_prediction_round,
)
from app.services.prediction_race_facts import get_prediction_race_facts
from app.services.telegram_outbox import enqueue, drain
from app.utils.notifications import get_users_with_settings
from app.utils.mini_app_links import mini_app_button
from app.services.web_notifications import publish_safely as publish_web


logger = logging.getLogger(__name__)


async def _queue_prediction(bot, event, kind, text, keyboard, users):
    now = datetime.now(timezone.utc)
    _, deadline = get_prediction_window(event)
    expires = deadline or now + timedelta(hours=2 if kind == 'closing' else 24)
    if kind == 'results':
        expires = now + timedelta(days=7)
    key = f"prediction:{kind}:{event.get('season', now.year)}:{event['round']}"
    await enqueue(key, text, keyboard, users, expires.timestamp())
    # The separate worker will finish queued recipients after a restart/failure.
    await drain(bot, event_key=key)
    return len(users)


def _prediction_open_trigger(sessions: list[dict]) -> datetime | None:
    by_name = {
        str(item.get("name") or "").strip().lower(): parse_utc(item.get("utc_iso"))
        for item in sessions
    }
    preferred_names = (
        "practice 1",
        "free practice 1",
        "sprint practice",
        "sprint fp1",
        "sprint shootout",
        "sprint qualifying",
    )
    candidates = [by_name.get(name) for name in preferred_names if by_name.get(name)]
    return min(candidates) if candidates else None


async def _send_prediction_opened(bot: Bot, event: dict, users: list[tuple]) -> int:
    keyboard = await mini_app_button(bot, "🔮 Сделать прогноз", "/predictions", tab="form")
    sprint_line = (
        "\nНа спринт-уикенде также доступны прогнозы на спринт-поул и победителя спринта."
        if event.get("sprint_start_utc") or event.get("sprint_quali_start_utc")
        else ""
    )
    text = (
        "🔮 <b>Открыт приём прогнозов</b>\n\n"
        f"🏁 {html.escape(str(event.get('event_name') or 'Гран-при'))}\n"
        "Укажите поул, первую пятёрку, лучший круг, первый сход и машину безопасности."
        f"{sprint_line}\n\n"
        "⏳ Приём закроется строго в момент начала первой квалификации уикенда."
    )
    await publish_web(f"prediction-open:{event.get('season')}:{event.get('round')}", "Открыт приём прогнозов", text, "/predictions?tab=form")
    return await _queue_prediction(bot, event, 'open', text, keyboard, users)


async def _send_prediction_results(
    bot: Bot,
    event: dict,
    top: list[dict],
    users: list[tuple],
) -> int:
    keyboard = await mini_app_button(
        bot, "🏆 Таблица прогнозов", "/predictions", tab="leaderboard",
    )
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
        + "\n\nОткройте общую таблицу прогнозов по кнопке ниже."
    )
    await publish_web(f"prediction-results:{event.get('season')}:{event.get('round')}", "Итоги прогнозов", text, "/predictions?tab=leaderboard")
    return await _queue_prediction(bot, event, 'results', text, keyboard, users)


async def _send_prediction_closing(bot: Bot, event: dict, users: list[tuple]) -> bool:
    keyboard = await mini_app_button(bot, "🔮 Сделать прогноз", "/predictions", tab="form")
    text = (
        "⏳ <b>До закрытия прогнозов осталось 2 часа!</b>\n\n"
        f"🏁 {html.escape(str(event.get('event_name') or 'Гран-при'))}\n\n"
        "Времени осталось мало! Укажите поул, первую пятёрку, лучший круг, первый сход "
        "и машину безопасности. Если прогноз уже сделан — ещё можно его проверить и изменить.\n\n"
        "🔒 Приём закроется строго в момент начала первой квалификации уикенда."
    )
    season, round_num = event['season'], int(event['round'])
    await publish_web(f"prediction-closing:{season}:{round_num}", "До закрытия прогнозов осталось 2 часа", text, "/predictions?tab=form")
    remaining = []
    for telegram_id, tz, *_ in users:
        if await was_reminder_sent(telegram_id, season, round_num, False, 21000):
            continue
        remaining.append((telegram_id, tz))
    await _queue_prediction(bot, event, 'closing', text, keyboard, remaining)
    return True  # Safely enqueued, not a claim that every recipient received it.


async def check_and_notify_predictions(bot: Bot, *, not_before: datetime | None = None) -> None:
    """Invites at FP1 and scores the stage after race results become ready."""
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
        opens_at, deadline = get_prediction_window(event)
        race_at = parse_utc(event.get("race_start_utc"))

        closing_at = deadline - timedelta(hours=2) if deadline else None
        if closing_at and now >= closing_at and not state.get("closing_sent", False):
            # A short scheduler window prevents late reminders and restart spam.
            stale = now >= min(deadline, closing_at + timedelta(minutes=5)) or (
                not_before is not None and closing_at < not_before
            )
            if not stale:
                # The closing invitation replaces an unsent opening invitation.
                if not state["opened_sent"]:
                    await mark_notification_state(season, round_num, "opened_sent")
                    state["opened_sent"] = True
            if stale or await _send_prediction_closing(bot, {**event, "season": season}, notification_users):
                await mark_notification_state(season, round_num, "closing_sent")

        if not state["opened_sent"] and opens_at and deadline and opens_at <= now < deadline:
            logger.info(
                "[Notification Trigger] event=prediction_window_open season=%s round=%s opens_at=%s",
                season,
                round_num,
                opens_at.isoformat(),
            )
            if now >= opens_at:
                skipped_open = not_before is not None and opens_at < not_before
                sent = 0 if skipped_open else await _send_prediction_opened(
                    bot, {**event, "season": season}, notification_users,
                )
                # The flag prevents re-enqueueing. Individual delivery is in the outbox.
                if skipped_open or sent or not notification_users:
                    await mark_notification_state(season, round_num, "opened_sent")
                logger.info(
                    "[Delivery Queued] event=prediction_window_open season=%s round=%s queued=%s",
                    season,
                    round_num,
                    sent,
                )

        if state["results_sent"] or not race_at or now < race_at + timedelta(hours=3):
            continue

        try:
            race_results, quali_payload, sprint_quali_results, sprint_results = await asyncio.gather(
                get_race_results_async(season, round_num),
                get_quali_for_round_async(season, round_num),
                get_sprint_quali_results_async(season, round_num)
                if event.get("sprint_quali_start_utc")
                else asyncio.sleep(0, result=[]),
                get_sprint_results_async(season, round_num)
                if event.get("sprint_start_utc")
                else asyncio.sleep(0, result=None),
            )
        except Exception:
            logger.exception("Prediction result data failed for %s/%s", season, round_num)
            continue
        if race_results is None or race_results.empty or len(race_results.index) < 10:
            continue
        qualifying_results = quali_payload[1] if isinstance(quali_payload, tuple) else quali_payload
        race_facts = await get_prediction_race_facts(season, round_num)
        answers = build_actual_answers(
            race_results,
            qualifying_results or [],
            sprint_qualifying_results=sprint_quali_results or [],
            sprint_results=sprint_results,
            extra_facts=race_facts,
        )
        score_info = await score_prediction_round(
            season,
            round_num,
            str(event.get("event_name") or "Гран-при"),
            answers,
        )
        top = await get_stage_top(season, round_num)
        # Keep historical scoring intact, but never replay old broadcasts on boot.
        skipped_result = not_before is not None and race_at + timedelta(hours=3) < not_before
        sent = 0 if skipped_result else await _send_prediction_results(
            bot, {**event, "season": season}, top, notification_users,
        )
        if skipped_result or sent or not notification_users:
            await mark_notification_state(season, round_num, "results_sent")
        logger.info(
            "Prediction results %s/%s: scored=%s max=%s queued=%s",
            season,
            round_num,
            score_info["scored"],
            score_info["max_points"],
            sent,
        )
