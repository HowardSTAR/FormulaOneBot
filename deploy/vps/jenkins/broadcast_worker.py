"""VPS delivery policy: only confirmed broadcasts, independent of app CLI flags."""
import asyncio
import logging
import signal
import uuid
import aiohttp


async def deliver_pending(bot):
    from app.services.telegram_outbox import connection, drain
    async with connection() as conn:
        keys = await (await conn.execute(
            "SELECT DISTINCT event_key FROM telegram_deliveries "
            "WHERE event_key GLOB 'broadcast:*' AND status IN ('pending','retry') "
            "ORDER BY event_key LIMIT 50")).fetchall()
    for row in keys:
        await drain(bot, event_key=row[0])


async def main():
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from app.config import get_settings
    from app.db import db
    from app.services import operations
    from app.services.posthog_bridge import config as analytics_config, flush
    from app.utils.process_lock import ProcessLock

    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    instance = uuid.uuid4().hex
    with ProcessLock(db.db_path.with_suffix('.worker.lock')):
        await db.initialize()
        async with Bot(get_settings().bot.token,
                       default=DefaultBotProperties(parse_mode='HTML')) as bot, \
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            await operations.register_job('telegram_outbox', 5)
            if all(analytics_config()):
                await operations.register_job('posthog', 15)
            last_flush = 0.0
            await operations.component('worker', instance, starting=True)
            heartbeat = asyncio.create_task(operations.heartbeat('worker', instance))
            try:
                while not stop.is_set():
                    try:
                        await operations.run_tracked('telegram_outbox', deliver_pending, bot)
                    except Exception:
                        logging.exception('Broadcast queue iteration failed')
                    if all(analytics_config()) and loop.time()-last_flush >= 15:
                        last_flush = loop.time()
                        try:
                            await operations.run_tracked('posthog', flush, db, http)
                        except Exception:
                            logging.exception('Analytics queue iteration failed')
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                await operations.component('worker', instance, stopping=True)
                await db.close()


if __name__ == '__main__':
    asyncio.run(main())
