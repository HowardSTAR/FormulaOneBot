"""Bot API 10.3 presentation, with an explicit, privacy-preserving text fallback."""
import os
from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    DisabledButton, InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage,
    InputRichBlockSectionHeading, InputRichBlockParagraph, InputRichBlockDetails,
    InputRichBlockTable, RichBlockTableCell,
    InputRichBlockPhoto, InputMediaPhoto, RichTextSpoiler,
)


def rich_enabled():
    return os.getenv("TELEGRAM_RICH_MESSAGES", "1").lower() not in {"0", "false", "off"}


def disabled_button(label: str):
    return InlineKeyboardButton(text=label, disabled=DisabledButton())


def personal_buttons(season: int, round_num: int, keyboard=None):
    rows = list(keyboard.inline_keyboard) if keyboard else []
    rows.append([
        InlineKeyboardButton(text="Мой разбор", callback_data=f"personal:review:{season}:{round_num}", style="primary"),
        InlineKeyboardButton(text="Мои лиги", callback_data=f"personal:leagues:{season}:{round_num}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def table(headers, rows):
    return InputRichBlockTable(is_compact=True, is_striped=True, cells=[
        [RichBlockTableCell(text=str(value), align="left", valign="top", is_header=header)
         for value in row]
        for header, row in [(True, headers), *[(False, row) for row in rows]]
    ])


def race_card(event_name, season, round_num, rows, recap, *, photo=None, favorites=""):
    """Rows are the already verified classification, not live positions."""
    ordered = sorted(rows, key=lambda row: int(row["pos"]) if str(row.get("pos", "")).isdigit() else 999)
    cells = [[row.get("pos", "—"), row.get("driver", "—"), row.get("points", "—")] for row in ordered]
    blocks = [InputRichBlockSectionHeading(text=f"{event_name} · {season}, этап {round_num}", size=3)]
    if cells and photo is not None:
        blocks.append(InputRichBlockPhoto(photo=InputMediaPhoto(
            media=photo, parse_mode=None, show_caption_above_media=False,
        )))
    elif cells:
        blocks.append(table(["Место", "Пилот", "Очки"], cells[:5]))
        blocks.append(InputRichBlockDetails(summary="Полная классификация", blocks=[table(["Место", "Пилот", "Очки"], cells)]))
    else:
        blocks.append(InputRichBlockParagraph(text=recap.get("note") or "Ждём подтверждённую классификацию."))
    if favorites:
        blocks.append(InputRichBlockParagraph(text=RichTextSpoiler(text=favorites)))
    for item in recap.get("items", [])[:3]:
        blocks.extend([InputRichBlockSectionHeading(text=item["title"], size=5), InputRichBlockParagraph(text=item["text"])])
    if recap.get("chronicle"):
        blocks.append(InputRichBlockSectionHeading(text="Интересные моменты гонки", size=4))
        for item in recap["chronicle"][:4]:
            blocks.append(InputRichBlockParagraph(text=item["title"]))
    blocks.append(InputRichBlockParagraph(text="Изменения чемпионата — за весь уик-энд." + (
        " Часть данных ещё не подтверждена." if recap.get("status") == "partial" else "")))
    return InputRichMessage(blocks=blocks)


def race_fallback(event_name, season, round_num, rows, recap, *, favorites=""):
    from app.services.race_recap import format_recap_telegram
    classification = "\n".join(escape(f"{row.get('pos', '—')}. {row.get('driver', '—')} · {row.get('points', '—')} очк.") for row in rows)
    return (f"🏁 <b>{escape(event_name)}</b> · {season}, этап {round_num}\n\n"
            + (f'<tg-spoiler>{escape(favorites)}</tg-spoiler>\n\n' if favorites else '')
            + format_recap_telegram(recap) + "\n\n" + classification
            + "\n\nИзменения чемпионата — за весь уик-энд.")


def review_card(review):
    points = "Расчёт ещё не завершён" if review["points"] is None else f"Ваш результат: {review['points']}/{review['max_points']}"
    blocks = [InputRichBlockSectionHeading(text=review["event_name"], size=3), InputRichBlockParagraph(text=points)]
    rows, explanations = [], []
    for item in review["items"]:
        def value(v):
            if v is None:
                return "Нет данных"
            if item["key"] == "safety_car":
                return "Да" if v else "Нет"
            return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        award = "Ожидаем данные" if item["status"] == "unavailable" else "Нет разбивки" if item["points"] is None else f"{item['points']}/{item['maximum']}"
        rows.append([item["label"], value(item["predicted"]), value(item["actual"]), award])
        explanations.append(InputRichBlockParagraph(text=f"{item['label']}: {item['reason']}"))
    blocks.append(table(["Пункт", "Ваш выбор", "Результат", "Баллы"], rows))
    blocks.append(InputRichBlockDetails(summary="Как начислены баллы", blocks=explanations))
    fallback = f"<b>{escape(review['event_name'])}</b>\n{escape(points)}\n\n" + "\n\n".join(
        escape(" · ".join(map(str, row))) for row in rows)
    return InputRichMessage(blocks=blocks), fallback


def leagues_card(view, user_id):
    title = f"Мои лиги · {view['total']}"
    blocks = [InputRichBlockSectionHeading(text=title, size=3)]
    fallback = [f"<b>{escape(title)}</b>"]
    for league in view['leagues']:
        name = league['name'][:100]
        scope = 'Мини-чемпионат · 3 этапа' if league['mode'] == 'cup' else 'Сезон'
        context = f"{scope} {league['season']} · Участников: {league['participants']}"
        blocks.extend([InputRichBlockSectionHeading(text=name, size=4),
                       InputRichBlockParagraph(text=context)])
        lines = [f"<b>{escape(name)}</b>", escape(context)]
        entries = list(league['top'])
        own = league['own']
        if own and all(entry['user_id'] != user_id for entry in entries):
            entries.append(own)
        if entries:
            rows = [[entry['place'], entry['display_name'] + (' (вы)' if entry['user_id'] == user_id else ''),
                     entry['total_points']] for entry in entries]
            blocks.append(table(['Место', 'Участник', 'Баллы'], rows))
            lines.extend(escape(f"#{place} · {name} — {points} баллов") for place, name, points in rows)
        else:
            blocks.append(InputRichBlockParagraph(text='Результатов пока нет.'))
            lines.append('Результатов пока нет.')
        own_text = (f"Ваше место: #{own['place']} · {own['total_points']} баллов" if own
                    else 'Вашего результата пока нет. Сделайте первый прогноз.')
        blocks.append(InputRichBlockParagraph(text=own_text))
        lines.append(escape(own_text))
        fallback.append('\n'.join(lines))
    if not view['total']:
        text = 'Вы пока не состоите в лигах.'
        blocks.append(InputRichBlockParagraph(text=text))
        fallback.append(text)
    if view['pages'] > 1:
        text = f"Страница {view['page'] + 1} из {view['pages']}"
        blocks.append(InputRichBlockParagraph(text=text))
        fallback.append(text)
    return InputRichMessage(blocks=blocks), '\n\n'.join(fallback)


def feature_rejected(exc):
    description = str(exc).lower()
    return any(part in description for part in ("method not found", "unsupported", "not supported", "rich_message", "rich message"))


async def send_card(bot, chat_id, card, fallback_text, **kwargs):
    """Never retry an ambiguous send, and never drop an ephemeral receiver."""
    if rich_enabled():
        try:
            return await bot.send_rich_message(chat_id=chat_id, rich_message=card, **kwargs)
        except TelegramBadRequest as exc:
            if not feature_rejected(exc):
                raise
    photo = next((block.photo for block in card.blocks if block.type == 'photo'), None)
    if photo is not None:
        if len(fallback_text) <= 1000:
            return await bot.send_photo(chat_id=chat_id, photo=photo.media, caption=fallback_text, parse_mode='HTML', **kwargs)
        heading = next((block.text for block in card.blocks if block.type == 'heading'), 'Итоги гонки')
        await bot.send_photo(chat_id=chat_id, photo=photo.media, caption=heading, **kwargs)
    return await bot.send_message(chat_id=chat_id, text=fallback_text, parse_mode="HTML", **kwargs)


def fallback_actions(card, text, options):
    """Ordinary transport actions; the outbox persists progress between sends."""
    photo = next((block.photo for block in card.blocks if block.type == 'photo'), None)
    if photo is None:
        return [{'method': 'send_message', 'kwargs': dict(text=text, parse_mode='HTML', **options)}]
    if len(text) <= 1000:
        return [{'method': 'send_photo', 'kwargs': dict(photo=photo.media, caption=text, parse_mode='HTML', **options)}]
    heading = next((block.text for block in card.blocks if block.type == 'heading'), 'Итоги гонки')
    return [{'method': 'send_photo', 'kwargs': dict(photo=photo.media, caption=heading, **options)},
            {'method': 'send_message', 'kwargs': dict(text=text, parse_mode='HTML', **options)}]
