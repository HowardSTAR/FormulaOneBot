"""Season standings in the same visual system as the race classification."""
from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

from app.utils.classification_card import BACKGROUND, MUTED, PANEL, RED, WHITE, _text


def _artwork(loader, row, season):
    try:
        source = loader(row["code"], row["name"], season)
        if source is not None:
            source = source.convert("RGBA")
            bounds = source.getchannel("A").getbbox()
            return source.crop(bounds) if bounds else None
    except Exception:
        pass
    return None


def _paste_art(image, source, box, *, portrait=False):
    x, y, width, height = box
    if portrait:
        # Show the face, not a full-body sprite squeezed into a tiny circle.
        source = source.crop((0, 0, source.width, min(source.height, int(source.width * 1.2))))
        source = ImageOps.fit(source, (width, height), centering=(0.5, 0.15))
    else:
        # Logos keep their aspect ratio and alpha, including wide wordmarks.
        source = ImageOps.contain(source, (width, height))
    image.paste(source, (x + (width - source.width) // 2, y + (height - source.height) // 2), source)


def render_standings(title, subtitle, rows, season, category, artwork_loader):
    drivers = category == "drivers"
    rows = list(rows) or [{"pos": "—", "code": "", "name": "Нет данных", "points": "—", "team": ""}]
    height = max(1080, 368 + len(rows) * 68)
    image = Image.new("RGB", (1080, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.polygon([(750, 0), (1080, 0), (1080, 220), (680, 220)], fill="#260e13")
    draw.rectangle((48, 43, 92, 49), fill=RED)
    _text(draw, (108, 35), "TURBOTEARS  /  RACE INTELLIGENCE", 22, 720, MUTED, True)
    _text(draw, (1032, 35), season, 22, 120, MUTED, True, "rt")
    _text(draw, (48, 90), "ЛИЧНЫЙ ЗАЧЁТ" if drivers else "КУБОК КОНСТРУКТОРОВ", 58, 984, bold=True)
    scope = "ВКЛЮЧАЯ СПРИНТЫ" if season >= 2021 else "ОФИЦИАЛЬНЫЙ ЗАЧЁТ"
    _text(draw, (48, 172), f"СЕЗОН {season}  /  {scope}", 29, 984)
    draw.line((48, 232, 1032, 232), fill="#34343d", width=2)
    _text(draw, (48, 258), "ПОЗ.", 19, 65, MUTED)
    _text(draw, (128, 258), "ПИЛОТ / КОМАНДА" if drivers else "КОМАНДА", 19, 390, MUTED)
    _text(draw, (720, 258), "ОЧКИ", 19, 140, MUTED, anchor="rt")
    _text(draw, (786, 258), "ЛИДЕРЫ ЧЕМПИОНАТА", 18, 246, MUTED)
    art = [_artwork(artwork_loader, row, season) for row in rows]
    for index, row in enumerate(rows):
        y = 296 + index * 68
        favored = bool(row.get("favorite"))
        draw.rounded_rectangle((48, y, 738, y + 64), radius=9,
                               fill="#231519" if index < 3 else PANEL,
                               outline="#dfb64a" if favored else None, width=2)
        draw.rounded_rectangle((48, y + 11, 52, y + 53), radius=2, fill=RED if index < 3 else "#3c3d47")
        _text(draw, (68, y + 16), row["pos"], 29, 52, bold=True)
        if art[index] is not None:
            _paste_art(image, art[index], (126, y + 4, 62, 56), portrait=drivers)
        else:
            _text(draw, (156, y + 21), row["code"][:3] or "—", 17, 60, MUTED, True, "mt")
        name = row["name"]
        if drivers and " " in name:
            given, family = name.rsplit(" ", 1)
            name = f"{given} {family.upper()}"
        _text(draw, (202, y + 5), name, 27, 332, bold=True)
        _text(draw, (202, y + 37), row.get("team") or (row["code"] if drivers else "КУБОК КОМАНД"), 16, 332, MUTED)
        _text(draw, (720, y + 15), row["points"], 29, 165, "#ff625d" if index == 0 else WHITE, True, "rt")
    tile_height = (height - 390) // 3
    for index, row in enumerate(rows[:3]):
        x, y = 766, 296 + index * (tile_height + 12)
        tile = Image.new("RGB", (266, tile_height), PANEL)
        td = ImageDraw.Draw(tile)
        td.polygon([(0, 0), (266, 0), (266, tile_height), (180, tile_height)], fill="#381117")
        source = art[index]
        if source is not None:
            if drivers:
                source = source.crop((0, 0, source.width, min(source.height, int(source.width * 1.6))))
            _paste_art(tile, source, (14, 48, 238, tile_height - 116))
        else:
            _text(td, (133, tile_height // 2), "НЕТ ФОТО" if drivers else "НЕТ ЛОГО", 24, 228, MUTED, True, "mt")
        _text(td, (12, 8), row["pos"], 84, 94, "#ff625d", True)
        td.rectangle((0, tile_height - 66, 266, tile_height), fill="#202129")
        _text(td, (16, tile_height - 57), row["name"], 25, 234, bold=True)
        _text(td, (16, tile_height - 25), f"{row['points']} очк.", 18, 234, MUTED)
        image.paste(tile, (x, y))
    draw.line((48, height - 52, 1032, height - 52), fill="#34343d", width=1)
    _text(draw, (48, height - 35), "F1HUB.RU", 18, 250, "#ff625d", True)
    _text(draw, (1032, height - 35), f"ЗАЧЁТ ЧЕМПИОНАТА  /  {season}", 17, 650, MUTED, anchor="rt")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
