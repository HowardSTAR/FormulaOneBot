"""Discover keyboards on outgoing requests and count Telegram button updates."""
import asyncio
import logging
import os
import re
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.services import notification_clicks as clicks

logger = logging.getLogger(__name__)


async def register_button(conn, kind, label, destination=''):
    button = f'bot:{kind}:{label[:200]}'
    source = 'bot:menu' if kind == 'reply' else 'bot:messages'
    caption = 'Клавиатура меню' if kind == 'reply' else 'Кнопки сообщений'
    await conn.execute(
        'INSERT OR IGNORE INTO notification_button_links VALUES(?,?,?,?,?,?,?,?)',
        (secrets.token_urlsafe(24), source, source, 'telegram', button, destination, caption, time.time()),
    )
    row = await (await conn.execute(
        'SELECT token FROM notification_button_links WHERE source_key=? AND channel=? AND button=?',
        (source, 'telegram', button),
    )).fetchone()
    return row['token']


async def track_keyboard(conn, keyboard, chat_id=None):
    keyboard = keyboard.model_copy(deep=True)
    if isinstance(keyboard, (ReplyKeyboardMarkup, ReplyKeyboardRemove)):
        if chat_id is not None:
            await conn.execute('DELETE FROM bot_reply_buttons WHERE chat_id=?', (str(chat_id),))
        if isinstance(keyboard, ReplyKeyboardMarkup):
            for row in keyboard.keyboard:
                for button in row:
                    if button.web_app:
                        tracked = await track_keyboard(conn, InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text=button.text, web_app=button.web_app),
                        ]]))
                        button.web_app = tracked.inline_keyboard[0][0].web_app
                        continue
                    token = await register_button(conn, 'reply', button.text)
                    if chat_id is not None:
                        await conn.execute('INSERT OR IGNORE INTO bot_reply_buttons VALUES(?,?,?)',
                                           (str(chat_id), button.text, token))
        return keyboard
    from app.api.site_analytics import PUBLIC_ROUTES
    base = next((os.getenv(key, '').strip() for key in ('MINI_APP_URL', 'PUBLIC_WEB_URL', 'FRONTEND_URL')
                 if os.getenv(key, '').strip()), '')
    broadcast = False
    for row in keyboard.inline_keyboard:
        for button in row:
            url = button.web_app.url if button.web_app else button.url
            token = dict(parse_qsl(urlsplit(url).query)).get('nb') if url else None
            if token:
                link = await (await conn.execute('SELECT campaign FROM notification_button_links WHERE token=?',
                                                (token,))).fetchone()
                broadcast = broadcast or bool(link and clicks.campaign_info(link['campaign']))
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                if broadcast and re.fullmatch(r'personal:(review|leagues):\d{4}:\d{1,2}', button.callback_data):
                    continue
                await register_button(conn, 'callback', button.text)
            elif button.web_app or button.url:
                url = button.web_app.url if button.web_app else button.url
                parts = urlsplit(url)
                path = parts.path or '/'
                if (not base or parts.scheme != 'https' or parts.netloc != urlsplit(base).netloc
                        or path not in PUBLIC_ROUTES or 'nb' in dict(parse_qsl(parts.query))):
                    continue
                # Keep destination in the key so equal captions on different pages stay distinct.
                token = await register_button(conn, 'arrival', f'{button.text} → {path}', path)
                query = parse_qsl(parts.query, keep_blank_values=True) + [('nb', token)]
                tracked = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
                if button.web_app:
                    button.web_app = button.web_app.model_copy(update={'url': tracked})
                else:
                    button.url = tracked
    return keyboard


class OutgoingButtonAnalytics(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        keyboard = getattr(method, 'reply_markup', None)
        menu = getattr(method, 'menu_button', None)
        if isinstance(menu, MenuButtonWebApp):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=menu.text, web_app=menu.web_app),
            ]])
        if isinstance(keyboard, (InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove)):
            try:
                async with asyncio.timeout(2):
                    async with clicks.connection() as conn:
                        tracked = await track_keyboard(conn, keyboard, getattr(method, 'chat_id', None))
                        await conn.commit()
                    if isinstance(menu, MenuButtonWebApp):
                        method = method.model_copy(update={'menu_button': menu.model_copy(update={
                            'web_app': tracked.inline_keyboard[0][0].web_app,
                        })})
                    else:
                        method = method.model_copy(update={'reply_markup': tracked})
            except Exception:
                logger.warning('Could not register bot buttons', exc_info=True)
        return await make_request(bot, method)


async def record_button(event):
    if not event.from_user or event.from_user.is_bot:
        return
    async with clicks.connection() as conn:
        user = await (await conn.execute('SELECT id FROM users WHERE telegram_id=? AND archived_at IS NULL',
                                        (event.from_user.id,))).fetchone()
        uid = user['id'] if user else None
        if isinstance(event, CallbackQuery):
            message = event.message
            keyboard = getattr(message, 'reply_markup', None)
            if not keyboard:
                return
            button = next((b for row in keyboard.inline_keyboard for b in row
                           if b.callback_data and b.callback_data == event.data), None)
            if not button:
                return
            # Preserve per-broadcast attribution and use the same event ID as its handler.
            match = re.fullmatch(r'personal:(review|leagues):\d{4}:\d{1,2}', event.data or '')
            if match:
                batch = await (await conn.execute(
                    "SELECT event_key FROM telegram_deliveries WHERE telegram_id=? AND message_id=? AND status='sent' ORDER BY updated DESC LIMIT 1",
                    (message.chat.id, message.message_id),
                )).fetchone()
                if batch and clicks.campaign_info(batch['event_key']):
                    token = await clicks.register(conn, batch['event_key'], 'telegram', match[1], '/predictions')
                else:
                    token = await register_button(conn, 'callback', button.text)
            else:
                token = await register_button(conn, 'callback', button.text)
            event_id = 'telegram:' + event.id
        elif isinstance(event, Message) and event.text:
            row = await (await conn.execute('SELECT token FROM bot_reply_buttons WHERE chat_id=? AND label=?',
                                           (str(event.chat.id), event.text))).fetchone()
            if row:
                token = row['token']
            else:
                # Existing persistent main keyboards keep working across deployments.
                from app.utils.bot_menu import MAIN_BUTTONS
                if event.chat.type != 'private' or event.text not in MAIN_BUTTONS:
                    return
                token = await register_button(conn, 'reply', event.text)
            event_id = f'telegram-message:{event.chat.id}:{event.message_id}'
        else:
            return
        await clicks.record(conn, token, event_id, str(event.from_user.id), uid)
        await conn.commit()


class IncomingButtonAnalytics(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            async with asyncio.timeout(2):
                await record_button(event)
        except Exception:
            logger.warning('Could not record bot button', exc_info=True)
        return await handler(event, data)
