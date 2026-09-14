"""Transport adapters for the shared persistent delivery state machine."""
import asyncio
import base64
import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO

from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InputMediaPhoto

_capture = ContextVar('notification_capture', default=None)


def encode(value):
    if isinstance(value, BytesIO):
        value = value.getvalue()
    if isinstance(value, BufferedInputFile):
        return {'_file': base64.b64encode(value.data).decode(), 'filename': value.filename}
    if isinstance(value, (bytes, bytearray)):
        return {'_file': base64.b64encode(value).decode(), 'filename': 'results.png'}
    if hasattr(value, 'model_dump'):
        return encode(value.model_dump(exclude_none=True, exclude_defaults=True))
    if isinstance(value, dict):
        return {k: encode(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if '_file' in value:
            return BufferedInputFile(base64.b64decode(value['_file']), filename=value['filename'])
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):
        return [decode(v) for v in value]
    return value


@contextmanager
def capture():
    actions = []
    token = _capture.set(actions)
    try:
        yield actions
    finally:
        _capture.reset(token)


def captured(method, kwargs):
    actions = _capture.get()
    if actions is None:
        return False
    actions.append({'method': method, 'kwargs': encode(kwargs)})
    return True


async def queue_actions(key, actions, users, expires):
    from app.services.telegram_outbox import enqueue
    if not actions:
        raise ValueError('Empty notification')
    # Validate serializability before committing any recipients.
    json.dumps(actions)
    await enqueue(key, '', None, users, expires, payload={'actions': actions})


async def queued_message(bot, chat_id, text, *, delivery_key, expires=None, **kwargs):
    await queue_actions(f'{delivery_key}:{chat_id}', [{'method':'send_message', 'kwargs':encode({'text':text,**kwargs})}], [(chat_id,'Europe/Moscow')], expires or time.time()+86400)
    return True  # persisted, not delivered


async def queued_photo(bot, chat_id, photo, *, delivery_key, expires=None, **kwargs):
    await queue_actions(f'{delivery_key}:{chat_id}', [{'method':'send_photo', 'kwargs':encode({'photo':photo,**kwargs})}], [(chat_id,'Europe/Moscow')], expires or time.time()+86400)
    return True


async def dispatch(bot, row):
    payload = json.loads(row['payload'])
    if row['channel'] == 'webpush':
        return await dispatch_push(row, payload)
    from app.services.telegram_outbox import connection
    from app.utils.safe_send import _apply_sound_preference
    from app.utils.notifications import is_quiet_hours
    from app.session_reminders import session_enabled
    async with connection() as conn:
        progress = await (await conn.execute('SELECT step FROM delivery_progress WHERE event_key=? AND recipient=?', (row['event_key'],row['telegram_id']))).fetchone()
        owner = await (await conn.execute('SELECT timezone,reminder_sessions,role FROM users WHERE telegram_id=? AND archived_at IS NULL',(row['telegram_id'],))).fetchone()
    if row['event_key'].startswith('reminder:') and row['telegram_id'] > 0:
        if not owner or not session_enabled(owner['reminder_sessions'],row['event_key'].split(':')[3]):
            return 'cancelled','preference_changed',None,0
    step = progress[0] if progress else 0
    action = payload['actions'][step]
    kwargs = decode(action['kwargs'])
    kwargs['disable_notification'] = bool(kwargs.get('disable_notification')) or is_quiet_hours(owner['timezone'] if owner else row['timezone'])
    if isinstance(kwargs.get('reply_markup'),dict):
        kwargs['reply_markup'] = InlineKeyboardMarkup.model_validate(kwargs['reply_markup'])
    if action['method'] == 'send_media_group':
        kwargs['media'] = [InputMediaPhoto.model_validate(item) for item in kwargs['media']]
    if action['method'] not in {'send_message','send_photo','send_media_group'}:
        return 'failed','unsupported_method',None,0
    await _apply_sound_preference(row['telegram_id'],kwargs)
    result = await getattr(bot,action['method'])(chat_id=row['telegram_id'], **kwargs)
    message = result[0] if isinstance(result,list) else result
    message_id = message.message_id if isinstance(message.message_id,int) else None
    async with connection() as conn:
        await conn.execute('INSERT INTO delivery_progress VALUES(?,?,?) ON CONFLICT(event_key,recipient) DO UPDATE SET step=excluded.step', (row['event_key'],row['telegram_id'],step+1))
        await conn.commit()
    return ('sent' if step+1 == len(payload['actions']) else 'retry'),None,message_id,0


async def dispatch_push(row, payload):
    from app.services.web_notifications import connection, validate_subscription, push_config
    from app.session_reminders import session_enabled
    from pywebpush import webpush, WebPushException
    async with connection() as conn:
        sub = await (await conn.execute('SELECT s.subscription,u.role,u.reminder_sessions FROM web_push_subscriptions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND u.archived_at IS NULL', (row['telegram_id'],))).fetchone()
    if not sub:
        return 'cancelled','subscription_removed',None,0
    key = payload['event_key']
    if key.startswith('admin-error:') and sub['role'] not in {'admin','superadmin'}:
        return 'cancelled','role_changed',None,0
    if key.startswith('reminder:') and (len(key.split(':')) != 5 or not session_enabled(sub['reminder_sessions'], key.split(':')[3])):
        return 'cancelled','preference_changed',None,0
    if not push_config()['enabled']:
        return 'retry','push_not_configured',None,time.time()+300
    try:
        subscription = json.loads(sub['subscription'])
        validate_subscription(subscription)
        await asyncio.to_thread(webpush, subscription_info=subscription,
            data=json.dumps(payload['data'],ensure_ascii=False), vapid_private_key=os.environ['WEB_PUSH_PRIVATE_KEY'],
            vapid_claims={'sub':os.environ['WEB_PUSH_SUBJECT']},ttl=max(0,min(3600,int(row['expires']-time.time()))),timeout=15)
        return 'sent',None,None,0
    except WebPushException as exc:
        code = exc.response.status_code if exc.response is not None else None
        if code in {404,410}:
            async with connection() as conn:
                await conn.execute('DELETE FROM web_push_subscriptions WHERE id=?',(row['telegram_id'],))
                await conn.commit()
            return 'blocked','subscription_expired',None,0
        if code == 429:
            try:
                delay = max(60,float(exc.response.headers.get('Retry-After',60)))
            except (TypeError,ValueError):
                delay = 60
            return ('retry' if row['attempts'] < 7 else 'failed'),'push_rate_limited',None,time.time()+delay
        return ('failed' if code and 400 <= code < 500 else 'unknown'),'push_request_failed',None,0
    except ValueError:
        return 'failed','invalid_subscription',None,0
