"""Refresh delivered reminders in place; never send a second notification."""
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.types import InlineKeyboardMarkup

from app.session_reminders import SESSION_BITS

logger = logging.getLogger(__name__)
STATUS_KEYS = {
    'race': 'race_status', 'quali': 'qualifying_status',
    'sprint': 'sprint_status', 'sprint_quali': 'sprint_qualifying_status',
}
# The schedule contains starts, not live finish times. Conservative fallback
# windows are explicitly labelled as schedule-based in the message.
SESSION_MINUTES = {
    'practice1': 60, 'practice2': 60, 'practice3': 60,
    'quali': 90, 'sprint_quali': 60, 'sprint': 60, 'race': 180,
}


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def session_phase(event, kind, now):
    """Return (phase, estimated); explicit cancellation/live/finish wins."""
    status = str(event.get(STATUS_KEYS.get(kind, f'{kind}_status')) or '').lower().strip()
    if event.get('is_cancelled') or status in {'cancelled', 'canceled', 'abandoned'}:
        return 'cancelled', False
    start = parse_utc(event.get(f'{kind}_start_utc'))
    if not start or kind not in SESSION_MINUTES:
        return 'unknown', False
    if status in {'completed', 'results_ready', 'finished'}:
        return 'finished', False
    if status in {'live', 'running', 'in_progress', 'suspended', 'red_flag'}:
        return 'live', False
    if now < start:
        return 'before', False
    end = parse_utc(event.get(f'{kind}_end_utc'))
    if end and end > start:
        return ('finished' if now >= end else 'live'), False
    end = start + timedelta(minutes=SESSION_MINUTES[kind])
    return ('finished' if now >= end else 'live'), True


def first_qualifying_kind(event):
    starts = [(parse_utc(event.get(f'{kind}_start_utc')), kind)
              for kind in ('quali', 'sprint_quali')]
    return min((item for item in starts if item[0]), default=(None, None))[1]


def prediction_closing_status_text(event, kind, phase, estimated):
    import html
    name = 'Спринт-квалификация' if kind == 'sprint_quali' else 'Квалификация'
    title = f'{name} ' + {'live': 'идёт', 'finished': 'закончилась', 'cancelled': 'отменена'}[phase]
    text = (f"🏁 <b>{title}</b>\n\n"
            f"{html.escape(str(event.get('event_name') or 'Гран-при'))}\n\n"
            '🔒 Приём прогнозов закрыт. Сохранённый прогноз можно посмотреть по кнопке ниже.')
    if estimated:
        text += '\n\nСтатус квалификации — по расписанию.'
    return text


async def _queue_status_edits(event, season, kind, now, batch_size, *, prediction=False):
    from app.services.telegram_outbox import connection
    from app.services.delivery_adapters import queue_actions, encode
    phase, _ = session_phase(event, kind, now)
    if phase not in {'live', 'finished', 'cancelled'}:
        return
    if prediction:
        source = f"prediction:closing:{season}:{event['round']}"
        predicate, params = 'd.event_key=?', [source]
        key_sql = "'prediction-state:' || d.event_key || ':' || d.telegram_id"
    else:
        prefix = f"reminder:{season}:{event['round']}:{kind}:"
        predicate, params = 'd.event_key>=? AND d.event_key<?', [prefix, prefix[:-1]+';']
        key_sql = "'reminder-state:' || d.event_key"
    async with connection() as conn:
        rows = await (await conn.execute(
            'SELECT d.event_key,d.telegram_id,d.message_id,d.timezone,u.timezone AS user_timezone '
            'FROM telegram_deliveries d JOIN telegram_delivery_batches b USING(event_key) '
            'LEFT JOIN users u ON u.telegram_id=d.telegram_id '
            f"WHERE {predicate} AND d.status='sent' AND d.message_id IS NOT NULL "
            'AND b.created>=? AND (d.telegram_id<0 OR (u.id IS NOT NULL AND u.archived_at IS NULL)) '
            'AND NOT EXISTS (SELECT 1 FROM telegram_delivery_batches e '
            f"WHERE e.event_key={key_sql} || ':' || ?) "
            'ORDER BY d.updated,d.telegram_id LIMIT ?',
            (*params, (now-timedelta(days=4)).timestamp(), phase, batch_size))).fetchall()
    for row in rows:
        tz_name = 'UTC' if row['telegram_id'] < 0 else row['user_timezone'] or row['timezone']
        metadata = {'source_key': row['event_key'], 'event': event, 'kind': kind,
                    'timezone': tz_name, 'for_group': row['telegram_id'] < 0,
                    'prediction_closing': prediction}
        action = {'method': 'edit_message_text', 'kwargs': encode({
            'message_id': row['message_id'], '_reminder': metadata})}
        key_base = (f"prediction-state:{row['event_key']}:{row['telegram_id']}" if prediction
                    else f"reminder-state:{row['event_key']}")
        await queue_actions(f'{key_base}:{phase}', [action], [(row['telegram_id'], tz_name)],
                            (now+timedelta(days=1)).timestamp())


async def refresh_reminder_messages(*, now=None, batch_size=200):
    """Queue bounded, deduplicated edits for reminders with confirmed message IDs.

    Receipts are durable, so a restart still updates previously sent reminders.
    Delivery IDs also support reminders sent before this feature was installed.
    Failed/deleted messages never cause a replacement send.
    """
    from app.f1_data import get_season_schedule_short_async
    now = now or utc_now()
    seasons = {now.year, (now - timedelta(days=4)).year}
    for season in sorted(seasons):
        try:
            schedule = await get_season_schedule_short_async(season)
        except Exception:
            logger.exception('Reminder status schedule unavailable for season=%s', season)
            continue
        for event in schedule or []:
            if event.get('is_testing') or not event.get('round'):
                continue
            for kind in SESSION_BITS:
                start = parse_utc(event.get(f'{kind}_start_utc'))
                if not start or not now - timedelta(days=3) <= start <= now:
                    continue
                await _queue_status_edits(event, season, kind, now, batch_size)
                if kind == first_qualifying_kind(event):
                    await _queue_status_edits(event, season, kind, now, batch_size, prediction=True)


async def dispatch_reminder_edit(bot, row, kwargs):
    """Only edit the original delivered message; render again after queue delays."""
    from app.services.telegram_outbox import connection
    from app.utils.notifications import get_notification_text
    metadata = kwargs.get('_reminder') or {}
    source = metadata.get('source_key', '')
    prediction = metadata.get('prediction_closing', False)
    key_base = (f"prediction-state:{source}:{row['telegram_id']}" if prediction
                else f'reminder-state:{source}')
    source_prefix = 'prediction:closing:' if prediction else 'reminder:'
    if not source.startswith(source_prefix) or row['event_key'] not in {
            f'{key_base}:live', f'{key_base}:finished', f'{key_base}:cancelled'}:
        return 'failed', 'invalid_reminder_edit', None, 0
    async with connection() as conn:
        receipt = await (await conn.execute(
            "SELECT d.message_id,b.keyboard FROM telegram_deliveries d JOIN telegram_delivery_batches b USING(event_key) "
            "WHERE d.event_key=? AND d.telegram_id=? AND d.status='sent'",
            (source, row['telegram_id']))).fetchone()
        terminal = await (await conn.execute(
            "SELECT 1 FROM telegram_delivery_batches WHERE event_key IN (?,?) LIMIT 1",
            (f'{key_base}:finished', f'{key_base}:cancelled'))).fetchone()
    if row['event_key'].endswith(':live') and terminal:
        return 'cancelled', 'reminder_edit_superseded', None, 0
    message_id = kwargs.get('message_id')
    if not receipt or not isinstance(message_id, int) or receipt['message_id'] != message_id:
        return 'cancelled', 'reminder_receipt_missing', None, 0
    now = utc_now()
    event, kind = metadata['event'], metadata['kind']
    start = parse_utc(event.get(f'{kind}_start_utc'))
    phase, estimated = session_phase(event, kind, now)
    if not start or phase in {'unknown', 'before'}:
        return 'cancelled', 'reminder_not_started', None, 0
    edit_kwargs = {}
    if prediction:
        text = prediction_closing_status_text(event, kind, phase, estimated)
        if receipt['keyboard']:
            keyboard = InlineKeyboardMarkup.model_validate(json.loads(receipt['keyboard']))
            for buttons in keyboard.inline_keyboard:
                for button in buttons:
                    if button.text == '🔮 Сделать прогноз':
                        button.text = '🔮 Мой прогноз'
            edit_kwargs['reply_markup'] = keyboard
    else:
        text = get_notification_text(event, metadata['timezone'], (start-now).total_seconds()/60,
                                     event_kind=kind, for_group=metadata['for_group'],
                                     phase=phase, estimated=estimated)
    try:
        await bot.edit_message_text(chat_id=row['telegram_id'], message_id=message_id,
                                    text=text, parse_mode='HTML', **edit_kwargs)
    except TelegramBadRequest as exc:
        detail = str(exc.message).lower()
        if 'message is not modified' not in detail:
            if 'message to edit not found' in detail or "message can't be edited" in detail:
                return 'cancelled', 'reminder_not_editable', message_id, 0
            raise
    except (TelegramNetworkError, TelegramServerError, TimeoutError):
        # Repeating the same edit is safe, unlike repeating an ambiguous send.
        if row['attempts'] >= 7:
            return 'failed', 'reminder_edit_unavailable', message_id, 0
        return 'retry', 'reminder_edit_retry', message_id, now.timestamp()+min(30*2**row['attempts'], 1800)
    return 'sent', None, message_id, 0
