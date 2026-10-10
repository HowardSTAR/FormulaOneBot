"""Versioned modular fictional-driver portraits shared by the UI and social cards."""
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT = {'helmet': 'scarlet', 'suit': 'scarlet', 'background': 'garage'}
OPTIONS = {
    'helmet': {'scarlet': 'Алый / полоса', 'cobalt': 'Кобальт / двойная полоса', 'mint': 'Жемчуг / мята'},
    'suit': {'scarlet': 'Алый / графит', 'cobalt': 'Индиго / лайм', 'mint': 'Графит / мята'},
    'background': {'garage': 'Ночной бокс', 'scarlet': 'Красный сектор', 'cobalt': 'Синий час',
                   'mint': 'Полярное сияние', 'gold': 'Золотой подиум'},
}
ASSETS = Path(__file__).resolve().parents[1] / 'profile_avatar_assets'


def validate(values):
    if set(values) != set(DEFAULT) or any(value not in OPTIONS[key] for key, value in values.items()):
        raise ValueError('Неизвестный вариант аватара')
    return dict(values)


@lru_cache(maxsize=6)
def _layer(name, helmet):
    with Image.open(ASSETS / f'{name}-v1.png') as source:
        source = source.convert('RGBA')
        # Each generated bust is registered at its black neck seal, keeping the
        # helmet and shoulder silhouettes intact when mixed across collections.
        split = round(source.height * ({'scarlet': .595, 'cobalt': .623, 'mint': .634} if helmet
                                       else {'scarlet': .62, 'cobalt': .64, 'mint': .65})[name])
        box = (0, 0, source.width, split) if helmet else (0, split, source.width, source.height)
        return source.crop(box).resize((384, 238 if helmet else 146), Image.Resampling.LANCZOS)


@lru_cache(maxsize=45)
def render(helmet='scarlet', suit='scarlet', background='garage'):
    validate(dict(helmet=helmet, suit=suit, background=background))
    palettes = {'garage': ('#384456', '#10141d'), 'scarlet': ('#a53b46', '#211725'),
                'cobalt': ('#375cb3', '#111c39'), 'mint': ('#3c9688', '#142638'),
                'gold': ('#a58248', '#26212a')}
    from PIL import ImageColor
    start, end = (ImageColor.getrgb(c) for c in palettes[background])
    image = Image.new('RGBA', (384, 384))
    draw = ImageDraw.Draw(image)
    for y in range(384):
        t = y / 383
        draw.line((0, y, 384, y), fill=tuple(round(a*(1-t)+b*t) for a, b in zip(start, end)))
    draw.ellipse((38, 25, 346, 333), outline=(*start, 180), width=2)
    draw.polygon(((305, 0), (335, 0), (135, 384), (105, 384)), fill=(*start, 90))
    image.alpha_composite(_layer(suit, False), (0, 238))
    image.alpha_composite(_layer(helmet, True), (0, 0))
    output = io.BytesIO()
    image.convert('RGB').save(output, 'PNG', optimize=True)
    return output.getvalue()
