"""A small allowlist of public utilities for Telegram Guest Mode; no FSM/DB writes."""
import asyncio
import os
import re
import time
from collections import OrderedDict
from datetime import datetime, timezone
from html import escape

from aiogram import Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Message

from app.f1_data import get_driver_standings_async, get_season_schedule_short_async
from app.services.driver_guides import get_driver_guide
from app.services.race_recap import get_race_recap_with_news as get_race_recap, format_recap_telegram
from app.utils.time_tools import telegram_time

router = Router(name="guest_public_tools")
_recent = OrderedDict()
HELP = ("🏁 <b>F1Hub в вашем чате</b>\n\n"
        "Упомяните бота и добавьте запрос:\n"
        "• следующая гонка\n• итоги гонки\n• пилот ALO\n• сравни ALO HAM\n• что такое VSC\n\n"
        "Только публичные данные. Личные прогнозы и настройки — в личном чате или Mini App.")
TERMS = {
    "vsc": "VSC — виртуальная машина безопасности: пилоты обязаны снизить темп по заданному временному нормативу. Физическая машина безопасности на трассу не выезжает.",
    "sc": "SC — машина безопасности: собирает пелотон и контролирует темп, пока маршалы устраняют опасность. Это не то же самое, что VSC.",
    "андеркат": "Андеркат — более ранний пит-стоп в попытке выиграть позицию за счёт темпа на свежих шинах. Он не гарантирует успех: важны прогрев шин и трафик.",
}


def allowed_rate(bot_id, caller_id, chat_id):
    now = time.monotonic()
    while _recent and next(iter(_recent.values())) <= now - 30:
        _recent.popitem(last=False)
    key = (bot_id, caller_id, chat_id)
    if now - _recent.get(key, -30) < 5:
        return False
    _recent[key] = now
    _recent.move_to_end(key)
    while len(_recent) > 2048:
        _recent.popitem(last=False)
    return True


def parse_query(text, username):
    text = re.sub(r"@" + re.escape(username) + r"\b", "", text or "", flags=re.I).strip().lower()
    if text in {"следующая гонка", "/next_race", "расписание"}:
        return "next", []
    if text in {"итоги гонки", "рекап", "/recap", "результаты гонки"}:
        return "recap", []
    match = re.fullmatch(r"(?:пилот|/driver)\s+([a-z]{3})(?:\s+(\d{4}))?", text)
    if match:
        return "driver", [match[1].upper(), match[2]]
    match = re.fullmatch(r"(?:сравни|/compare)\s+([a-z]{3})\s+([a-z]{3})(?:\s+(\d{4}))?", text)
    if match:
        return "compare", [match[1].upper(), match[2].upper(), match[3]]
    match = re.fullmatch(r"что такое\s+(vsc|sc|андеркат)\??", text)
    if match:
        return "term", [match[1]]
    return "help", []


async def public_answer(kind, args):
    now = datetime.now(timezone.utc)
    if kind == "help":
        return HELP
    if kind == "term":
        return escape(TERMS[args[0]])
    if kind in {"next", "recap"}:
        schedule = await get_season_schedule_short_async(now.year) or []
        dated = []
        for event in schedule:
            try:
                start = datetime.fromisoformat(event["race_start_utc"].replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
            except (KeyError, ValueError, AttributeError):
                continue
            if not event.get("is_cancelled"):
                dated.append((start, event))
        eligible = sorted(((at, e) for at, e in dated if (at >= now if kind == "next" else at <= now)), key=lambda x: x[0], reverse=kind == "recap")
        if not eligible:
            return "Для этого сезона пока нет подходящего этапа."
        event = eligible[0][1]
        title = f"🏁 <b>{escape(event.get('event_name') or 'Гран-при')}</b> · {now.year}, этап {event['round']}"
        if kind == "next":
            return title + "\nСтарт: " + telegram_time(event["race_start_utc"]) + "\nДо старта: " + telegram_time(event["race_start_utc"], relative=True)
        recap = await get_race_recap(now.year, int(event["round"]))
        return title + "\n\n" + (format_recap_telegram(recap) or escape(recap.get("note") or "Ждём данные.")) + "\n\nИзменения чемпионата — за весь уик-энд."
    season = int(args[-1]) if args[-1] else now.year
    if not 1950 <= season <= now.year:
        return "Укажите сезон от 1950 до текущего."
    standings = await get_driver_standings_async(season)
    if standings is None or standings.empty or "driverCode" not in standings:
        return "Зачёт пока недоступен."
    lines, chosen = [], []
    for code in args[:-1]:
        matches = standings[standings["driverCode"].str.upper() == code]
        if len(matches) != 1:
            return "Не удалось однозначно найти пилота. Укажите трёхбуквенный код и сезон."
        row = matches.iloc[0]
        name = escape(f"{row['givenName']} {row['familyName']}")
        lines.append(f"<b>{name}</b>: P{row['position']}, {float(row['points']):g} очк.")
        chosen.append(row)
    text = f"📊 Сезон {season} · опубликованный личный зачёт, включая спринты\n\n" + "\n".join(lines)
    if kind == "driver":
        guide = get_driver_guide(str(chosen[0].get("driverId", "")))
        if guide:
            text += "\n\n" + escape(guide["intro"]) + "\n\nНа что смотреть: " + escape(guide["watch"])
            text += "\nПодсказка — редакционная; биография описывает карьеру."
    return text


@router.guest_message()
async def guest_message(message: Message):
    caller = message.guest_bot_caller_user or message.from_user
    if not message.guest_query_id or not caller or caller.is_bot:
        return
    bot_user = await message.bot.me()
    if not allowed_rate(message.bot.id, caller.id, message.chat.id):
        text = "Запросы идут слишком часто. Подождите несколько секунд."
    elif os.getenv("TELEGRAM_GUEST_MODE", "1").lower() in {"0", "false", "off"}:
        text = "Гостевые ответы временно отключены. Откройте F1Hub в личном чате."
    else:
        kind, args = parse_query(message.text or message.caption, bot_user.username or "F1HubBot")
        try:
            text = await asyncio.wait_for(public_answer(kind, args), timeout=10)
        except Exception:
            text = "Источник сейчас недоступен. Попробуйте позже — данные не подменяем."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть F1Hub", url=f"https://t.me/{bot_user.username}", style="primary")
    ]]) if bot_user.username else None
    await message.bot.answer_guest_query(
        guest_query_id=message.guest_query_id,
        result=InlineQueryResultArticle(id="f1hub-public", title="F1Hub", reply_markup=keyboard,
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML")),
        request_timeout=5,
    )
