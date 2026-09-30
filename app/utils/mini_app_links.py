"""Buttons that launch a destination inside Telegram's private-chat Mini App."""
import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from app.utils.broadcast_draft import validate_button_destination

logger = logging.getLogger(__name__)


async def _mini_app_base(bot: Bot):
    """Resolve the public Mini App origin once for a whole keyboard."""
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
    try:
        parts = urlsplit(base)
        parts.port
    except ValueError:
        logger.warning("Mini App button omitted: invalid public URL")
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        logger.warning("Mini App button omitted: a public HTTPS URL is required")
        return None
    return parts


async def destination_buttons(
    bot: Bot, buttons: list[tuple[str, str, dict]],
) -> InlineKeyboardMarkup | None:
    """One button per row; local paths open Mini App, full URLs open links.

    Validate all destinations first, and never return an incomplete keyboard
    when a Mini App origin cannot be resolved.
    """
    if not buttons:
        return None
    destinations = [validate_button_destination(path) for _, path, _ in buttons]
    base = None
    if any(not destination.scheme for destination in destinations):
        base = await _mini_app_base(bot)
        if base is None:
            return None
    rows = []
    for (label, path, params), destination in zip(buttons, destinations):
        if destination.scheme:
            button = InlineKeyboardButton(text=label, url=path)
        else:
            query = dict(parse_qsl(base.query, keep_blank_values=True))
            destination_pairs = parse_qsl(destination.query, keep_blank_values=True)
            for key, _ in destination_pairs:
                query.pop(key, None)
            query.update({key: str(value) for key, value in params.items() if value is not None})
            url = urlunsplit((base.scheme, base.netloc, destination.path,
                             urlencode(list(query.items()) + destination_pairs), destination.fragment))
            button = InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))
        rows.append([button])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def mini_app_button(bot: Bot, label: str, path: str, **params) -> InlineKeyboardMarkup | None:
    destination = validate_button_destination(path)
    if destination.scheme:
        raise ValueError("Mini App destination must be a local path")
    return await destination_buttons(bot, [(label, path, params)])
