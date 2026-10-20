"""One owner for schedules and durable jobs: python -m app.worker."""
import argparse
import asyncio
import signal
import uuid

from dotenv import load_dotenv

load_dotenv()


async def run():
    import logging
    from datetime import datetime, timezone

    import aiohttp
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.config import get_settings
    from app.db import db
    from app.f1_data import init_redis_cache, close_redis_cache, warmup_cache
    from app.services import operations
    from app.services.boosty_service import BoostyService
    from app.services.posthog_bridge import flush
    from app.services.prediction_analytics import run_job, settle_forecasts
    from app.services.prediction_notifications import check_and_notify_predictions
    from app.services.prediction_recovery import refresh_missing
    from app.services.recap_news import refresh_recent_news
    from app.services.recap_chronicle import refresh_recent_race_control
    from app.services.reminder_status import refresh_reminder_messages
    from app.services.telegram_outbox import drain, prune_payloads
    from app.services.weekly_race_notifications import check_and_notify_weekly_race
    from app.services.weekly_race_overtakes import dispatch_overtakes
    from app.services.web_notifications import poll_web_notifications
    from app.utils.backup import create_backup
    from app.utils.notifications import (check_and_send_notifications, check_and_send_session_results,
                                        check_and_notify_voting_results, initialize_result_notification_state)
    from app.utils.process_lock import ProcessLock

    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    settings = get_settings()
    instance = uuid.uuid4().hex
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))
    # OS ownership is released on a kill too; no stale distributed lease to steal.
    with ProcessLock(db.db_path.with_suffix('.worker.lock')):
        await db.initialize()
        bot = Bot(settings.bot.token, default=DefaultBotProperties(parse_mode='HTML'))
        scheduler = AsyncIOScheduler(timezone='UTC')
        running = set()
        heartbeat = None
        try:
            if settings.bot.redis_url:
                await init_redis_cache(settings.bot.redis_url)
            started = datetime.now(timezone.utc)
            ready = False

            async def results():
                nonlocal ready
                if not ready:
                    ready = await initialize_result_notification_state()
                else:
                    await check_and_send_session_results(bot)

            async def backup():
                await asyncio.to_thread(create_backup)

            async def tracked(name, function, args, kwargs):
                task = asyncio.current_task()
                running.add(task)
                try:
                    await operations.run_tracked(name, function, *args, **kwargs)
                finally:
                    running.discard(task)

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
                boosty = BoostyService(db)
                jobs = [
                    ('recap_news', 900, refresh_recent_news, (), {}, True),
                    ('recap_race_control', 900, refresh_recent_race_control, (), {}, True),
                    ('prediction_analytics_settlement', 600, settle_forecasts, (), {}, False),
                    ('backup', 86400, backup, (), {}, True),
                    ('delivery_retention', 86400, prune_payloads, (), {}, False),
                    ('notifications_job', 30, check_and_send_notifications, (bot,), {}, False),
                    ('warmup_sessions', 3600, warmup_cache, (), {}, True),
                    ('web_notifications_job', 30, poll_web_notifications, (), {'not_before': started.timestamp()}, False),
                    ('results_job', 30, results, (), {}, False),
                    ('voting_results_job', 300, check_and_notify_voting_results, (bot,), {'not_before': started}, False),
                    ('prediction_notifications_job', 30, check_and_notify_predictions, (bot,), {'not_before': started}, False),
                    ('prediction_recovery', 1800, refresh_missing, (), {}, False),
                    ('telegram_outbox', 5, drain, (bot,), {}, True),
                    ('weekly_race_overtakes', 30, dispatch_overtakes, (bot,), {}, False),
                    ('weekly_race_notifications', 30, check_and_notify_weekly_race, (bot,), {}, False),
                    ('reminder_status', 30, refresh_reminder_messages, (), {}, False),
                    ('forecast_jobs', 5, run_job, (), {}, True),
                    ('posthog', 15, flush, (db, http), {}, True),
                    ('boosty', 15, boosty.poll, (), {}, True),
                ]
                for name, interval, function, args, kwargs, immediate in jobs:
                    await operations.register_job(name, interval)
                    options = {'next_run_time': started} if immediate else {}
                    scheduler.add_job(tracked, 'interval', seconds=interval, id=name,
                        args=[name, function, args, kwargs], max_instances=1, coalesce=True,
                        misfire_grace_time=60, **options)
                await operations.component('worker', instance, starting=True)
                heartbeat = asyncio.create_task(operations.heartbeat('worker', instance))
                scheduler.start()
                try:
                    await stop.wait()
                finally:
                    scheduler.pause()
                    if running:
                        _, pending = await asyncio.wait(running, timeout=20)
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                    scheduler.shutdown(wait=False)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                await operations.component('worker', instance, stopping=True)
            await bot.session.close()
            await close_redis_cache()
            await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Probe the persisted worker heartbeat')
    args = parser.parse_args()
    if args.check:
        from app.db import DB_PATH
        from app.services.operations import worker_ready
        raise SystemExit(0 if worker_ready(DB_PATH) else 1)
    asyncio.run(run())


if __name__ == '__main__':
    main()
