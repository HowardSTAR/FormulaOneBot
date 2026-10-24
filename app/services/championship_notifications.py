"""Prepare current title artwork without blocking or suppressing reminders."""
import asyncio
import logging

from aiogram.types import BufferedInputFile

from app.services import championship
from app.utils.championship_card import build_card_models, render_championship_card

logger = logging.getLogger(__name__)


async def prepare_reminder(event, season, kind, *, schedule=None):
    if kind not in {'race', 'sprint'} or event.get('is_testing'):
        return event, ()
    try:
        event = await championship.enrich_event(
            event, season, phase='race' if kind == 'race' else 'weekend', schedule=schedule)
        models = build_card_models(event.get('championship') or {})
    except Exception:
        logger.exception('Championship reminder unavailable for %s/%s', season, event.get('round'))
        return event, ()
    photos = []
    for model in models:
        try:
            png = await asyncio.to_thread(render_championship_card, model)
            photos.append(BufferedInputFile(png, filename=f'championship-{model.kind}.png'))
        except Exception:
            logger.exception('Championship artwork unavailable for %s/%s/%s', season, event.get('round'), model.kind)
    return event, tuple(photos)
