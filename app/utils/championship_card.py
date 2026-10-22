"""Reusable, local championship posters. Data and artwork stay separate.

This renderer does not fetch standings or send notifications. It consumes the
same verified title scenarios as the forecast form, so scores and opponents
can be replaced without regenerating or retouching any design asset.
"""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.utils.classification_card import _font

GOLD = '#eed088'
WHITE = '#f4f4ee'
GREEN = '#65efb1'
RED = '#ff6477'
MUTED = '#9b9fa8'
WIDTH, HEIGHT = 1080, 1420
CROWDED_TOP, RIVAL_TILE_HEIGHT, RIVAL_TILE_GAP = 950, 310, 18
ASSETS = Path(__file__).resolve().parents[1] / 'assets'


@dataclass(frozen=True)
class Entrant:
    code: str
    name: str
    points: float


@dataclass(frozen=True)
class Rival:
    entrant: Entrant
    maximum: float | None
    blocks_from: float | None
    tie_points: float | None = None


@dataclass(frozen=True)
class ChampionshipCard:
    kind: str
    season: int
    round: int
    leader: Entrant
    gain: float
    race: tuple[int, ...]
    sprint: tuple[int, ...]
    rivals: tuple[Rival, ...]


def number(value):
    return f'{float(value):g}'


def build_card_models(context):
    """No mathematical chance means no attachment; an outage is not 'No'.

    A card illustrates one sufficient scenario, not the entire decision table.
    Equal-point exceptions are amber, never advertised as guaranteed green.
    """
    if context.get('status') != 'ok':
        return []
    from app.services.championship import COMPETITIONS, attainable_scores
    cards = []
    for kind, cars in COMPETITIONS:
        candidates = context.get(kind) or []
        if not candidates:
            continue
        candidate = max(candidates, key=lambda c: (c['points'], c['wins']))
        scenario = candidate['scenarios'][0]
        finish = scenario['finishes'][0]
        scores = attainable_scores(cars, 22, bool(candidate['has_sprint']))
        # Include opponents from the entire scenario set, including a rival who
        # can delay the title but cannot yet clinch it on this particular round.
        opponents = {}
        for option in candidate['scenarios']:
            for rival in option['rivals']:
                opponents[rival['id']] = rival
        limits = {r['id']: r for r in scenario['rivals']}
        rivals = []
        for identifier, opponent in sorted(opponents.items(), key=lambda item: (-item[1]['points'], item[0])):
            cap = limits.get(identifier)
            if cap is None:
                maximum, blocking, tie = None, None, None
            else:
                maximum, tie = cap['max_points'], cap['tie_points']
                safe = max(maximum, tie) if tie is not None else maximum
                blocking = next((p for p in scores if p > safe), None)
            rivals.append(Rival(Entrant(identifier, opponent['name'], opponent['points']), maximum, blocking, tie))
        cards.append(ChampionshipCard(kind, int(context['season']), int(context['round']),
                                      Entrant(candidate['id'], candidate['name'], candidate['points']),
                                      scenario['points'], tuple(finish['race']), tuple(finish['sprint']), tuple(rivals)))
    return cards


def _text(image, xy, value, size, fill=WHITE, *, anchor='mt', width=1000, bold=True, glow=False):
    value = str(value)
    draw = ImageDraw.Draw(image)
    font = _font(size, bold)
    while draw.textlength(value, font=font) > width and size > 14:
        size -= 1
        font = _font(size, bold)
    if glow:
        mask = Image.new('L', image.size)
        ImageDraw.Draw(mask).text(xy, value, font=font, fill=255, anchor=anchor)
        bloom = Image.new('RGBA', image.size, '#e5a944')
        bloom.putalpha(mask.filter(ImageFilter.GaussianBlur(13)).point(lambda x: int(x * .55)))
        image.alpha_composite(bloom)
        gradient = Image.new('RGBA', image.size)
        gd = ImageDraw.Draw(gradient)
        top = int(draw.textbbox(xy, value, font=font, anchor=anchor)[1])
        bottom = int(draw.textbbox(xy, value, font=font, anchor=anchor)[3])
        for y in range(top, bottom + 1):
            t = (y - top) / max(1, bottom - top)
            color = tuple(int(a + (b-a)*t) for a, b in zip((255, 244, 184), (181, 132, 55)))
            gd.line((0, y, image.width, y), fill=color)
        gradient.putalpha(mask)
        image.alpha_composite(gradient)
    else:
        draw.text(xy, value, font=font, fill=fill, anchor=anchor)


def _background(style, height):
    yy, xx = np.mgrid[0:height:2, 0:WIDTH:2]
    halo = np.exp(-(((xx - 540)/370)**2 + ((yy - 530)/470)**2))
    floor = np.exp(-(((xx - 540)/620)**2 + ((yy - 1060)/150)**2))
    color = np.array([7, 10, 14]) + halo[..., None]*np.array([35, 27, 11]) + floor[..., None]*np.array([12, 11, 7])
    image = Image.fromarray(np.uint8(np.clip(color, 0, 255))).resize((WIDTH, height), Image.Resampling.BICUBIC).convert('RGBA')
    ornament = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(ornament)
    if style == 'podium':
        draw.polygon([(0, 210), (330, 145), (385, 1000), (0, 1050)], fill=(28, 77, 73, 65))
        draw.polygon([(330, 145), (750, 145), (716, 1000), (385, 1000)], fill=(118, 88, 32, 64))
        draw.polygon([(750, 145), (1080, 210), (1080, 1050), (716, 1000)], fill=(125, 64, 21, 70))
        draw.line((330, 145, 385, 1000), fill=(226, 191, 107, 120), width=2)
        draw.line((750, 145, 716, 1000), fill=(226, 191, 107, 120), width=2)
    else:
        draw.ellipse((200, 180, 880, 860), outline=(220, 183, 98, 64), width=2)
        draw.arc((225, 205, 855, 835), 190, 345, fill=(227, 197, 120, 130), width=3)
    for y in range(250, 1030, 36):
        for x in range(34, 1050, 36):
            if abs(x-540) > 390:
                draw.ellipse((x, y, x+2, y+2), fill=(206, 184, 132, 23))
    rng = np.random.default_rng(7)
    for _ in range(85):
        x, y = int(rng.integers(30, 1050)), int(rng.integers(150, 1000))
        draw.ellipse((x, y, x+2, y+2), fill=(241, 204, 125, int(rng.integers(20, 100))))
    image.alpha_composite(ornament)
    return image


def _load(model, entrant, category):
    # Existing, season-aware identity resolver; never download at render time.
    from app.utils.image_render import get_asset_path, get_car_image_path
    path = get_car_image_path(entrant.code, model.season) if category == 'cars' else get_asset_path(model.season, category, entrant.code)
    if category == 'cars' and path is not None and path.parent != ASSETS / str(model.season) / 'cars':
        return None
    if path is None:
        return None
    with Image.open(path) as source:
        art = source.convert('RGBA')
    bounds = art.getchannel('A').getbbox()
    return art.crop(bounds) if bounds else None


def _portrait(image, source, box, *, leader=False):
    if source is None:
        return
    x, y, w, h = box
    source = source.crop((0, 0, source.width, min(source.height, int(source.width * 1.55))))
    art = ImageOps.fit(source, (w, h), centering=(.5, .02), method=Image.Resampling.LANCZOS)
    # A soft fade keeps the photographic silhouettes above the condition strip.
    alpha = np.asarray(art.getchannel('A'), dtype=np.float32)
    fade = np.minimum(1, np.maximum(0, (h - np.arange(h))/max(1, h*.19)))
    alpha *= fade[:, None]
    if not leader:
        pixels = np.array(art)
        pixels[..., :3] = (pixels[..., :3] * .76).astype('uint8')
        art = Image.fromarray(pixels)
    art.putalpha(Image.fromarray(np.uint8(alpha)))
    if leader:
        halo = Image.new('RGBA', (w+80, h+80), '#dbb76a')
        mask = Image.new('L', halo.size)
        mask.paste(art.getchannel('A'), (40, 40))
        halo.putalpha(mask.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v*.22)))
        image.alpha_composite(halo, (x-40, y-40))
    image.alpha_composite(art, (x, y))


def _contain(image, source, box, *, fade=False):
    if source is None:
        return
    x, y, w, h = box
    art = ImageOps.contain(source, (w, h), Image.Resampling.LANCZOS)
    if fade:
        art.putalpha(art.getchannel('A').point(lambda v: int(v*.7)))
    image.alpha_composite(art, (x+(w-art.width)//2, y+(h-art.height)//2))


def _arrow(draw, x, y, color, *, size=24):
    draw.line((x, y+size, x, y-size), fill=color, width=5)
    draw.line((x-size//2, y-size//2, x, y-size, x+size//2, y-size//2), fill=color, width=5)


def _places(positions):
    return '+'.join(f'P{p}' if p else '0' for p in positions)


def _header(image, model, *, compact=False):
    ImageDraw.Draw(image).line((48, 35, 1032, 35), fill='#584627', width=1)
    _text(image, (48, 52), model.season, 23, MUTED, anchor='lt', bold=False)
    _text(image, (1032, 52), f'{model.round:02d}', 23, MUTED, anchor='rt', bold=False)
    _text(image, (540, 82), 'CHAMPION?', 80 if compact else 85, GOLD, width=800, glow=True)
    _text(image, (540, 178 if compact else 175), number(model.leader.points),
          120 if compact else 156, GOLD, width=400, glow=True)


def _footer(image, y):
    _text(image, (540, y), 'ВСЕ ЗЕЛЁНЫЕ УСЛОВИЯ ВМЕСТЕ · КРАСНОГО ДОСТАТОЧНО ОДНОГО',
          16, MUTED, width=980)


def _name(image, entrant, center, y, width, *, leader=False):
    name = entrant.name.upper()
    if ' ' in name and width < 450:
        given, family = name.rsplit(' ', 1)
        _text(image, (center, y), given, 24 if leader else 21, GOLD if leader else MUTED, width=width)
        _text(image, (center, y+34), family, 49 if leader else 35, GOLD if leader else WHITE, width=width, glow=leader)
    else:
        _text(image, (center, y+15), name, 52 if leader else 36, GOLD if leader else WHITE, width=width, glow=leader)


def rival_labels(model, rival):
    """Plain-language bounds; weekend totals must never become race places."""
    green = ('ЛЮБОЙ РЕЗУЛЬТАТ', '')
    if rival.maximum is not None:
        green = ('НЕТ ВАРИАНТА', '') if rival.maximum < 0 else (
            'НЕ БОЛЬШЕ', number(rival.maximum) + ' очков')
    red = ('НЕ ПОМЕШАЕТ', '') if rival.blocks_from is None else (
        'ОТ ' + number(rival.blocks_from) + ' ОЧКОВ', '')
    if model.kind == 'drivers' and not model.sprint:
        from app.services.championship import RACE
        if rival.maximum is not None and 0 <= rival.maximum < RACE[0]:
            place = next((p for p, score in enumerate(RACE, 1) if score <= rival.maximum), len(RACE) + 1)
            green = (f'{place}-е ИЛИ НИЖЕ', 'не больше ' + number(rival.maximum) + ' очков')
        if rival.blocks_from is not None and 0 < rival.blocks_from <= RACE[0]:
            place = max(p for p, score in enumerate(RACE, 1) if score >= rival.blocks_from)
            red = (f'{place}-е ИЛИ ВЫШЕ', 'от ' + number(rival.blocks_from) + ' очков')
    return green, red


def _condition(image, center, y, heading, lines, color, width, compact):
    _text(image, (center, y), heading, 15 if compact else 18, color, width=width)
    _text(image, (center, y+(27 if compact else 31)), lines[0],
          30 if compact else 38, color, width=width)
    _text(image, (center, y+(67 if compact else 82)), lines[1],
          21 if compact else 24, color, width=width, bold=False)


def _rival_metrics(image, model, rival, center, y, width=290, *, compact=False):
    green, red = rival_labels(model, rival)
    _condition(image, center, y, 'ДЛЯ ТИТУЛА', green, GREEN, width, compact)
    if rival.blocks_from is not None:
        _condition(image, center, y+(117 if compact else 150), 'ОТЛОЖИТ ТИТУЛ', red, RED, width, compact)
    else:
        _text(image, (center, y+(144 if compact else 181)), red[0],
              24 if compact else 27, MUTED, width=width)
    if rival.tie_points is not None:
        _text(image, (center, y+(217 if compact else 277)), number(rival.tie_points) + ' очков: доп. условия',
              17 if compact else 20, GOLD, width=width)


def _png(image):
    output = BytesIO()
    image.convert('RGB').save(output, format='PNG', optimize=True)
    return output.getvalue()


def _rival_tile(image, model, rival, x, y, loader):
    """Keep a rival's identity and both bounds together at a readable scale."""
    width = 486
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x, y, x+width, y+RIVAL_TILE_HEIGHT), radius=20,
                           fill='#0f1419', outline='#393323', width=1)
    if model.kind == 'drivers':
        _portrait(image, loader(model, rival.entrant, 'pilots'), (x+8, y+115, 137, 180))
    else:
        _contain(image, loader(model, rival.entrant, 'teams'), (x+22, y+124, 108, 95))
        _contain(image, loader(model, rival.entrant, 'cars'), (x+7, y+235, 142, 60))
    _text(image, (x+22, y+18), rival.entrant.name.upper(), 26, width=width-44, anchor='lt')
    _text(image, (x+75, y+52), number(rival.entrant.points), 39, GOLD, width=125)
    _text(image, (x+75, y+99), 'ОЧКОВ', 13, MUTED, width=125)
    _rival_metrics(image, model, rival, x+315, y+65, width=300, compact=True)


def _render_crowded(model, style, loader):
    rows = math.ceil(len(model.rivals)/2)
    height = CROWDED_TOP + rows*RIVAL_TILE_HEIGHT + (rows-1)*RIVAL_TILE_GAP + 72
    image = _background(style, height)
    _header(image, model, compact=True)
    if model.kind == 'drivers':
        _portrait(image, loader(model, model.leader, 'pilots'), (330, 295, 420, 480), leader=True)
    else:
        _contain(image, loader(model, model.leader, 'teams'), (430, 318, 220, 215))
        _contain(image, loader(model, model.leader, 'cars'), (210, 525, 660, 185))
    _name(image, model.leader, 540, 725, 400, leader=True)
    draw = ImageDraw.Draw(image)
    draw.line((54, 815, 1026, 815), fill='#64502c', width=2)
    draw.line((54, 916, 1026, 916), fill='#64502c', width=1)
    places = _places(model.race)
    if model.sprint:
        places += ' / СПРИНТ ' + _places(model.sprint)
    _text(image, (225, 830), 'РЕЗУЛЬТАТ ЛИДЕРА', 16, MUTED, width=300)
    _text(image, (225, 858), places, 36, width=300)
    _arrow(draw, 455, 867, GREEN, size=15)
    _text(image, (555, 839), '+'+number(model.gain), 57, GREEN, width=200)
    _text(image, (855, 830), 'СТАНЕТ ОЧКОВ', 16, MUTED, width=260)
    _text(image, (855, 858), number(model.leader.points+model.gain), 36, GOLD, width=260)
    for index, rival in enumerate(model.rivals):
        row, column = divmod(index, 2)
        # Center the last tile when the number of opponents is odd.
        x = 297 if index == len(model.rivals)-1 and column == 0 else 44 + column*506
        _rival_tile(image, model, rival, x, CROWDED_TOP+row*(RIVAL_TILE_HEIGHT+RIVAL_TILE_GAP), loader)
    _footer(image, height-40)
    return _png(image)


def render_championship_card(model, *, style='aura', artwork_loader=None):
    """Render a fresh poster. A caller may cache by complete data + artwork version.

    No rivals are silently discarded: four or more total participants switch
    to a leader portrait and a two-column rival grid. Missing images leave identities
    and scores intact. Returned PNG bytes are independent of file destinations.
    """
    if style not in {'aura', 'podium'} or model.kind not in {'drivers', 'constructors'}:
        raise ValueError('Unsupported championship card style or competition')
    if not math.isfinite(model.leader.points) or not math.isfinite(model.gain):
        raise ValueError('Invalid championship score')
    loader = artwork_loader or _load
    if len(model.rivals) > 2:
        return _render_crowded(model, style, loader)
    height = HEIGHT
    image = _background(style, height)
    _header(image, model)
    main_rivals = model.rivals
    centers = (185, 895)
    if model.kind == 'drivers':
        for rival, center in zip(main_rivals, centers):
            _portrait(image, loader(model, rival.entrant, 'pilots'), (center-185, 430, 370, 545))
        _portrait(image, loader(model, model.leader, 'pilots'), (280, 330, 520, 665), leader=True)
    else:
        for rival, center in zip(main_rivals, centers):
            _contain(image, loader(model, rival.entrant, 'teams'), (center-90, 435, 180, 160), fade=True)
            _contain(image, loader(model, rival.entrant, 'cars'), (center-190, 550, 380, 150), fade=True)
        _contain(image, loader(model, model.leader, 'teams'), (390, 345, 300, 250))
        glow = Image.new('RGBA', image.size)
        ImageDraw.Draw(glow).ellipse((150, 710, 930, 825), fill=(229, 187, 88, 85))
        image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(30)))
        _contain(image, loader(model, model.leader, 'cars'), (150, 595, 780, 330))
    for rival, center in zip(main_rivals, centers):
        _text(image, (center, 325), number(rival.entrant.points), 68, '#c5c9c9', width=300)
    # The photo fade and a dark plate prevent text sitting over faces or logos.
    plate = Image.new('RGBA', image.size)
    ImageDraw.Draw(plate).rectangle((0, 928, WIDTH, height), fill=(7, 10, 14, 226))
    image.alpha_composite(plate)
    draw = ImageDraw.Draw(image)
    draw.line((54, 1036, 1026, 1036), fill='#64502c', width=2)
    draw.line((360, 1062, 360, 1360), fill='#30332f', width=1)
    draw.line((720, 1062, 720, 1360), fill='#30332f', width=1)
    _name(image, model.leader, 540, 937, 350, leader=True)
    for rival, center in zip(main_rivals, centers):
        _name(image, rival.entrant, center, 943, 300)
        _rival_metrics(image, model, rival, center, 1065)
    _text(image, (540, 1065), 'РЕЗУЛЬТАТ ЛИДЕРА', 18, MUTED, width=310)
    _text(image, (540, 1096), _places(model.race), 48, WHITE, width=310)
    draw = ImageDraw.Draw(image)
    _arrow(draw, 435, 1197, GREEN, size=20)
    _text(image, (560, 1157), '+'+number(model.gain), 80, GREEN, width=225)
    _text(image, (540, 1260), 'СТАНЕТ ОЧКОВ', 18, MUTED, width=310)
    _text(image, (540, 1290), number(model.leader.points+model.gain), 43, GOLD, width=310)
    if model.sprint:
        _text(image, (540, 1348), 'СПРИНТ: ' + _places(model.sprint), 21, GOLD, width=300)
    _footer(image, 1386)
    return _png(image)
