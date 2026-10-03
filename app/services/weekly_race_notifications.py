"""Monday 11:00 Moscow recap, using the durable delivery queue."""
import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.engagement import weekly, weekly_period, time_label
from app.services.telegram_outbox import connection, enqueue, drain
from app.services.web_notifications import publish_safely as publish_web
from app.utils.mini_app_links import mini_app_button
from app.utils.notifications import get_users_with_settings

MOSCOW = ZoneInfo('Europe/Moscow')
TITLE = 'Итоги заезда недели'


def recap_text(previous, current_track):
    entries = previous['entries']
    text = f"🏁 <b>Заезд недели закончился</b>\n{html.escape(previous['name'])}\n\n"
    if entries:
        winners = [entry for entry in entries if entry['time_ms'] == entries[0]['time_ms']]
        names = ', '.join(html.escape(entry['name']) for entry in winners[:3])
        if len(winners) > 3:
            names += f" и ещё {len(winners) - 3}"
        text += ('🏆 Победитель: ' if len(winners) == 1 else '🏆 Победители: ')
        text += f"<b>{names}</b> — {time_label(entries[0]['time_ms'])}"
    else:
        text += 'На этой неделе не было сохранённых заездов — победителя нет.'
    return (text + '\n\n🟢 <b>Началась новая неделя!</b>\n'
            + f"Новая трасса: {html.escape(current_track['name'])}.\n"
            + 'Заезд уже идёт. Участвуйте и смотрите итоги в разделе «С друзьями».')


async def check_and_notify_weekly_race(bot, *, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    track, start, _ = weekly_period(now)
    due = start.astimezone(MOSCOW).replace(hour=11)
    # Recover a short outage on Monday, without broadcasting old weeks at startup.
    if not due <= now < due + timedelta(hours=1):
        return False
    key = f'weekly-race:{start.date().isoformat()}'
    week = (start-timedelta(days=7)).date().isoformat()
    destination = f'/community?weekly=previous&week={week}'
    async with connection() as conn:
        stored = await (await conn.execute(
            'SELECT text,keyboard,expires FROM telegram_delivery_batches WHERE event_key=?', (key,))).fetchone()
    expires = due.replace(hour=23, minute=59).timestamp()
    if stored is None:
        previous = await weekly(start - timedelta(microseconds=1))
        text = recap_text(previous, track)
        keyboard = await mini_app_button(bot, '🏁 С друзьями · итоги и новый заезд',
                                         '/community', weekly='previous', week=week)
        # Do not freeze a broadcast without its requested destination button.
        if keyboard is None:
            return False
        users = await get_users_with_settings(notifications_only=True)
        await enqueue(key, text, keyboard, users, expires)
        # Re-read the winning snapshot if two workers attempted the same week.
        async with connection() as conn:
            stored = await (await conn.execute(
                'SELECT text,keyboard,expires FROM telegram_delivery_batches WHERE event_key=?', (key,))).fetchone()
    await publish_web(key, TITLE, stored['text'], destination, expires=stored['expires'])
    await drain(bot, event_key=key)
    return True
