"""Buttons that launch a destination inside Telegram's private-chat Mini App."""
import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from app.utils.broadcast_draft import validate_button_destination

logger = logging.getLogger(__name__)


async def mini_app_button(bot: Bot, label: str, path: str, **params) -> InlineKeyboardMarkup | None:
    destination = validate_button_destination(path)
    if destination.scheme:
        raise ValueError("Mini App destination must be a local path")
    base = next((os.getenv(key, "").strip() for key in
                 ("MINI_APP_URL", "PUBLIC_WEB_URL", "FRONTEND_URL")
                 if os.getenv(key, "").strip()), "")
    if not base:
        try:
            menu = await bot.get_chat_menu_button()
            base = getattr(getattr(menu, "web_app", None), "url", "")
        except Exception:
            logger.warning("Could not resolve the configured Mini App menu URL")
            return None
    if not isinstance(base, str) or not base:
        logger.warning("Mini App button omitted: configure MINI_APP_URL or the bot menu")
        return None
    parts = urlsplit(base)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        logger.warning("Mini App button omitted: a public HTTPS URL is required")
        return None
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    destination_pairs = parse_qsl(destination.query, keep_blank_values=True)
    for key, _ in destination_pairs:
        query.pop(key, None)
    query.update({key: str(value) for key, value in params.items() if value is not None})
    url = urlunsplit((parts.scheme, parts.netloc, destination.path,
                     urlencode(list(query.items()) + destination_pairs), destination.fragment))
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url)),
    ]])
