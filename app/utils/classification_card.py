"""Deterministic TurboTears result cards; artwork is optional, never a data source."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
BACKGROUND = "#0b0c10"
PANEL = "#17191f"
WHITE = "#f5f5f7"
MUTED = "#989aa5"
RED = "#e10600"


def _font(size, bold=False):
    try:
        return ImageFont.truetype(str(FONT_DIR / ("Jost-Bold.ttf" if bold else "Jost-Regular.ttf")), size)
    except OSError:
        return ImageFont.load_default()


def _fit(draw, text, size, width, bold=False):
    text = str(text)
    font = _font(size, bold)
    while draw.textlength(text, font=font) > width and size > 16:
        size -= 1
        font = _font(size, bold)
    while text and draw.textlength(text, font=font) > width:
        text = text[:-2].rstrip() + "…"
    return text, font


def _text(draw, xy, text, size, width, fill=WHITE, bold=False, anchor="lt"):
    text, font = _fit(draw, text, size, width, bold)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def render_classification(event_name, session_type, rows, season, favorites, portrait_loader):
    """All finishers in one full-width PNG, with a separate top-three portrait rail."""
    rows = list(rows) or [{"pos": "—", "driver": "Нет данных", "team": ""}]
    qualifying = "QUALIFYING" in session_type.upper()
    sprint = "SPRINT" in session_type.upper()
    title = ("СПРИНТ-КВАЛИФИКАЦИЯ" if sprint else "КВАЛИФИКАЦИЯ") if qualifying else (
        "ИТОГИ СПРИНТА" if sprint else "ИТОГИ ГОНКИ"
    )
    width, height = 1080, max(1350, 362 + len(rows) * 56)
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.polygon([(750, 0), (1080, 0), (1080, 220), (680, 220)], fill="#260e13")
    draw.rectangle((48, 43, 92, 49), fill=RED)
    _text(draw, (108, 35), "TURBOTEARS  /  RACE INTELLIGENCE", 22, 720, MUTED, True)
    _text(draw, (1032, 35), season, 22, 120, MUTED, True, "rt")
    _text(draw, (48, 90), title, 64, 984, bold=True)
    _text(draw, (48, 174), str(event_name or "GRAND PRIX").upper(), 32, 984)
    draw.line((48, 232, 1032, 232), fill="#34343d", width=2)
    _text(draw, (48, 258), "ПОЗ.", 19, 65, MUTED)
    _text(draw, (128, 258), "ПИЛОТ / КОМАНДА", 19, 380, MUTED)
    _text(draw, (720, 258), "ВРЕМЯ / ОТРЫВ" if qualifying else "ОЧКИ", 19, 175, MUTED, anchor="rt")
    _text(draw, (786, 258), "ЛИДЕРЫ СЕССИИ", 18, 246, MUTED)
    favorites = {str(code).upper() for code in favorites or []}
    for index, row in enumerate(rows):
        y = 296 + index * 56
        code = str(row.get("driver_code") or "").upper()
        favored = code in favorites
        draw.rounded_rectangle((48, y, 738, y + 52), radius=9,
                               fill="#231519" if index < 3 else PANEL,
                               outline="#dfb64a" if favored else None, width=2)
        draw.rounded_rectangle((48, y + 9, 52, y + 43), radius=2,
                               fill=RED if index < 3 else "#3c3d47")
        _text(draw, (68, y + 10), row.get("pos", "—"), 29, 52, bold=True)
        name = str(row.get("driver") or "—")
        if draw.textlength(name, font=_font(28, True)) > 393:
            parts = name.split()
            if len(parts) > 1:
                name = parts[0][0] + ". " + " ".join(parts[1:])
        _text(draw, (128, y + 3), name, 28, 390, bold=True)
        _text(draw, (128, y + 33), row.get("team") or code or "—", 17, 390, MUTED)
        value = (row.get("gap_or_time") or "—") if qualifying else row.get("points")
        if not qualifying:
            try:
                value = format(float(value), "g") if value is not None else "—"
            except (ValueError, TypeError):
                value = "—"
        _text(draw, (720, y + 12), value, 28, 180,
              "#ff625d" if index == 0 else WHITE, True, "rt")

    rail_height = height - 366
    tile_height = (rail_height - 24) // 3
    for index, row in enumerate(rows[:3]):
        x, y = 766, 296 + index * (tile_height + 12)
        tile = Image.new("RGB", (266, tile_height), PANEL)
        td = ImageDraw.Draw(tile)
        td.polygon([(0, 0), (266, 0), (266, tile_height), (180, tile_height)], fill="#381117")
        try:
            portrait = portrait_loader(str(row.get("driver_code") or ""),
                                       str(row.get("driver") or ""), season)
        except Exception:
            portrait = None
        if portrait is not None:
            portrait = ImageOps.contain(portrait.convert("RGBA"), (300, tile_height - 50))
            tile.paste(portrait, ((266 - portrait.width) // 2, tile_height - 64 - portrait.height), portrait)
        else:
            _text(td, (133, tile_height // 2), row.get("driver_code") or "F1", 60, 220,
                  WHITE, True, "mt")
        # Paint the rank last so portrait artwork cannot obscure it.
        _text(td, (12, 8), str(index + 1), 92, 70, "#ff625d", True)
        td.rectangle((0, tile_height - 66, 266, tile_height), fill="#202129")
        _text(td, (16, tile_height - 57), row.get("driver") or "—", 25, 234, bold=True)
        _text(td, (16, tile_height - 25), row.get("team") or "", 17, 234, MUTED)
        image.paste(tile, (x, y))
    draw.line((48, height - 52, 1032, height - 52), fill="#34343d", width=1)
    _text(draw, (48, height - 35), "F1HUB.RU", 18, 250, "#ff625d", True)
    _text(draw, (1032, height - 35), "РЕЗУЛЬТАТЫ СЕССИИ  /  " + str(season),
          17, 550, MUTED, anchor="rt")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
