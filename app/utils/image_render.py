from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Callable
from datetime import date
import hashlib
import math  # <--- Добавлен для рисования звезды

from PIL import Image, ImageDraw, ImageFont

from app.utils.default import DRIVER_CODE_TO_FILE, _TEAM_KEY_TO_FILE

# Кеш загруженных фотографий пилотов
_DRIVER_PHOTOS_CACHE: dict[str, Image.Image] = {}
# Кеш логотипов команд
_TEAM_LOGOS_CACHE: dict[str, Image.Image] = {}

# Визуальные константы (Modern Dark Theme)
BG_GRADIENT_TOP = (25, 30, 45)
BG_GRADIENT_BOT = (10, 10, 15)
CARD_BG_COLOR = (35, 40, 55)
SHADOW_COLOR = (0, 0, 0)
TEXT_COLOR = (240, 240, 250)
ACCENT_RED = (225, 6, 0)

# Сдвиг текста по вертикали
TEXT_V_SHIFT = -15


# --- Загрузка шрифтов ---
def _load_fonts() -> tuple[
    ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"

    def load_font(name: str, size: int):
        try:
            return ImageFont.truetype(str(fonts_dir / name), size)
        except Exception:
            return ImageFont.load_default()

    font_title = load_font("Jost-Bold.ttf", 60)
    font_subtitle = load_font("Jost-Regular.ttf", 34)
    font_row = load_font("Jost-Medium.ttf", 44)
    # Emoji шрифт больше не критичен для звезды, но оставим для других целей
    try:
        font_emoji = ImageFont.truetype(str(fonts_dir / "NotoEmoji-Regular.ttf"), 40)
    except:
        font_emoji = font_row

    return font_title, font_subtitle, font_row, font_emoji


FONT_TITLE, FONT_SUBTITLE, FONT_ROW, FONT_EMOJI = _load_fonts()


def _normalize_team_key(text: str) -> str:
    import re
    s = (str(text) or "").lower()
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


# --- Рисование геометрических примитивов ---

def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple):
    """
    Рисует 5-конечную звезду векторно.
    cx, cy - центр звезды
    r - внешний радиус (размер)
    """
    points = []
    # 5 лучей, внешний радиус R, внутренний r*0.4
    inner_r = r * 0.45

    # Начинаем с -90 градусов (верхняя точка)
    angle_start = -math.pi / 2

    for i in range(10):
        angle = angle_start + i * (math.pi / 5)  # шаг 36 градусов
        radius = r if i % 2 == 0 else inner_r
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))

    draw.polygon(points, fill=color)


def _generate_placeholder_avatar(text: str, size: int = 90) -> Image.Image:
    """Генерирует аватарку с инициалами."""
    text = str(text or "?").strip()
    h = hashlib.md5(text.encode('utf-8')).hexdigest()
    r = int(h[0:2], 16) % 100 + 50
    g = int(h[2:4], 16) % 100 + 50
    b = int(h[4:6], 16) % 100 + 50
    color = (r, g, b)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size, size), fill=color)

    initials = text[:2].upper() if len(text) <= 3 else text[:1].upper()
    if " " in text:
        parts = text.split()
        if len(parts) > 1:
            initials = f"{parts[0][0]}{parts[1][0]}".upper()

    try:
        font = FONT_ROW
        w, h_text = _text_size(draw, initials, font)
        draw.text(((size - w) / 2, (size - h_text) / 2 + TEXT_V_SHIFT / 2), initials, font=font, fill=(255, 255, 255))
    except:
        pass

    return img


def _get_driver_photo(code: str) -> Image.Image | None:
    if not code: return None
    code = str(code).upper()
    if code in _DRIVER_PHOTOS_CACHE: return _DRIVER_PHOTOS_CACHE[code]
    filename = DRIVER_CODE_TO_FILE.get(code)
    if not filename: return None
    pilots_dir = Path(__file__).resolve().parents[1] / "assets" / "pilots"
    img_path = pilots_dir / filename
    if not img_path.exists(): return None
    try:
        img = Image.open(img_path).convert("RGB")
        _DRIVER_PHOTOS_CACHE[code] = img
        return img
    except Exception:
        return None


def _get_team_logo(name_or_code: str) -> Image.Image | None:
    key = _normalize_team_key(name_or_code)
    if not key: return None
    if key in _TEAM_LOGOS_CACHE: return _TEAM_LOGOS_CACHE[key]
    filename = _TEAM_KEY_TO_FILE.get(key)
    if not filename: return None
    teams_dir = Path(__file__).resolve().parents[1] / "assets" / "teams"
    img_path = teams_dir / filename
    if not img_path.exists(): return None
    try:
        img = Image.open(img_path).convert("RGBA")
        _TEAM_LOGOS_CACHE[key] = img
        return img
    except Exception:
        return None


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return draw.textsize(text, font=font)


def _create_vertical_gradient(width: int, height: int, top_color: tuple, bottom_color: tuple) -> Image.Image:
    base = Image.new('RGB', (width, height), top_color)
    gradient_strip = Image.new('RGB', (1, height), top_color)
    draw = ImageDraw.Draw(gradient_strip)
    r1, g1, b1 = top_color
    r2, g2, b2 = bottom_color
    for y in range(height):
        ratio = y / height
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        draw.point((0, y), fill=(r, g, b))
    return gradient_strip.resize((width, height), resample=Image.Resampling.NEAREST)


# --- ОСНОВНАЯ ФУНКЦИЯ ---

def create_results_image(
        title: str,
        subtitle: str,
        rows: List[Tuple[str, str, str, str]],
        avatar_loader: Callable[[str, str], Image.Image | None] | None = None,
        card_color_func: Callable[[str], tuple[int, int, int]] | None = None,
) -> BytesIO:
    safe_rows = []
    if rows:
        for r in rows:
            safe_rows.append((str(r[0]), str(r[1] or ""), str(r[2] or "Unknown"), str(r[3])))
    else:
        safe_rows = [("—", "", "Нет данных", "")]

    padding = 30
    header_gap = 50
    line_spacing = 30
    row_height = 120
    avatar_size = 90

    if avatar_loader is None:
        def avatar_loader(code: str, name: str) -> Image.Image | None:
            return _get_driver_photo(code)

    temp_img = Image.new("RGB", (100, 100))
    draw_tmp = ImageDraw.Draw(temp_img)

    title_w, title_h = _text_size(draw_tmp, title, FONT_TITLE)
    subtitle_w, subtitle_h = _text_size(draw_tmp, subtitle, FONT_SUBTITLE)

    num_rows = len(safe_rows)
    rows_per_col = (num_rows + 1) // 2

    max_row_text = ""
    for pos, code, name, pts in safe_rows:
        candidate = f"{pos}. {name} {pts}000"
        if len(candidate) > len(max_row_text): max_row_text = candidate
    row_text_w, _ = _text_size(draw_tmp, max_row_text, FONT_ROW)

    min_width = 1800
    img_width = max(min_width, title_w + 2 * padding, row_text_w + 2 * padding)
    img_height = padding + title_h + header_gap + subtitle_h + header_gap + rows_per_col * (
                row_height + line_spacing) + padding

    img = _create_vertical_gradient(img_width, img_height, BG_GRADIENT_TOP, BG_GRADIENT_BOT)
    draw = ImageDraw.Draw(img, "RGBA")

    cur_y = padding
    x_title = (img_width - title_w) // 2
    draw.text((x_title + 2, cur_y + 2), title, font=FONT_TITLE, fill=(0, 0, 0))
    draw.text((x_title, cur_y), title, font=FONT_TITLE, fill=(255, 255, 255))
    cur_y += title_h + 15

    x_sub = (img_width - subtitle_w) // 2
    draw.text((x_sub, cur_y), subtitle, font=FONT_SUBTITLE, fill=(180, 180, 200))
    cur_y += subtitle_h + 20

    line_w = 400
    draw.line(((img_width - line_w) // 2, cur_y, (img_width + line_w) // 2, cur_y), fill=ACCENT_RED, width=4)
    cur_y += 40
    start_y = cur_y

    gap_between_cols = 50
    col_width = (img_width - 2 * padding - gap_between_cols) // 2
    left_x = padding
    right_x = padding + col_width + gap_between_cols

    rows_left = safe_rows[:rows_per_col]
    rows_right = safe_rows[rows_per_col:]

    def _default_card_color_for_pos(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except:
            p = 99
        if p <= 3: return (255, 140, 60)
        if p <= 10: return (60, 200, 160)
        return (80, 90, 120)

    color_for_pos = card_color_func or _default_card_color_for_pos

    def _draw_row(col_x: int, row_y: int, pos: str, code: str, name: str, pts: str) -> None:
        card_x0, card_y0 = col_x, row_y
        card_x1, card_y1 = col_x + col_width, row_y + row_height
        accent = color_for_pos(pos)

        draw.rounded_rectangle((card_x0 + 6, card_y0 + 6, card_x1 + 6, card_y1 + 6), radius=24, fill=SHADOW_COLOR)
        draw.rounded_rectangle((card_x0, card_y0, card_x1, card_y1), radius=24, fill=CARD_BG_COLOR,
                               outline=(60, 65, 80), width=1)

        strip_width = 12
        draw.rounded_rectangle((card_x0, card_y0, card_x0 + strip_width, card_y1), radius=24, fill=accent)
        draw.rectangle((card_x0 + strip_width - 5, card_y0, card_x0 + strip_width, card_y1), fill=accent)

        inner_y_center = (card_y0 + card_y1) // 2
        pts_w, pts_h = _text_size(draw, pts, FONT_ROW)
        pos_w, pos_h = _text_size(draw, pos, FONT_ROW)

        pts_x = card_x1 - 24 - pts_w - 16
        pos_x = card_x0 + 24 + strip_width

        avatar_x = pos_x + max(80, pos_w + 32)
        name_x = avatar_x + avatar_size + 24

        raw_code = code.replace("⭐️", "").replace("⭐", "").strip().upper()
        lookup_key = raw_code if raw_code else name

        base_img = avatar_loader(lookup_key, name)
        if base_img is None:
            base_img = _generate_placeholder_avatar(name or code or "?")

        if base_img:
            avatar = base_img.resize((avatar_size, avatar_size), Image.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
            paste_y = inner_y_center - avatar_size // 2
            img.paste(avatar, (int(avatar_x), int(paste_y)), mask)

        draw.text((pos_x, inner_y_center + TEXT_V_SHIFT - pos_h // 2), pos, font=FONT_ROW, fill=(180, 190, 200))

        draw.rounded_rectangle((pts_x - 10, inner_y_center - 20, pts_x + pts_w + 10, inner_y_center + 20), radius=12,
                               fill=(45, 50, 65))
        draw.text((pts_x, inner_y_center + TEXT_V_SHIFT - pts_h // 2), pts, font=FONT_ROW, fill=TEXT_COLOR)

        clean_name = name.replace("⭐️", "").replace("⭐", "").strip()
        has_star = "⭐" in name or "⭐" in code

        name_draw = clean_name
        name_w, name_h = _text_size(draw, name_draw, FONT_ROW)
        max_name_w = pts_x - name_x - 20
        while name_draw and name_w > max_name_w:
            name_draw = name_draw[:-1]
            name_w, name_h = _text_size(draw, name_draw + "…", FONT_ROW)
        if name_draw != clean_name: name_draw += "…"

        cur_name_x = name_x

        if has_star:
            # --- РИСУЕМ ЗВЕЗДУ ГЕОМЕТРИЧЕСКИ ---
            # Центрируем звезду по вертикали относительно текста
            star_radius = 16
            star_cx = cur_name_x + star_radius
            # Сдвигаем чуть вниз (TEXT_V_SHIFT обычно поднимает текст, звезду тоже надо поднять)
            star_cy = inner_y_center + TEXT_V_SHIFT

            _draw_star(draw, star_cx, star_cy, star_radius, (255, 215, 0))  # Золотая звезда
            cur_name_x += 45  # отступ

        draw.text((cur_name_x, inner_y_center + TEXT_V_SHIFT - name_h // 2), name_draw, font=FONT_ROW, fill=TEXT_COLOR)

    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)
        if i < len(rows_left): _draw_row(left_x, row_y, *rows_left[i])
        if i < len(rows_right): _draw_row(right_x, row_y, *rows_right[i])

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# Обертки
def create_driver_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    def _color(pos: str):
        try:
            p = int(pos)
        except:
            p = 99
        if p == 1: return (255, 180, 0)
        if p == 2: return (192, 192, 192)
        if p == 3: return (205, 127, 50)
        return (80, 100, 140)

    return create_results_image(title, subtitle, rows, card_color_func=_color)


def create_constructor_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    def _loader(code: str, name: str):
        return _get_team_logo(name or code)

    def _color(pos: str):
        try:
            p = int(pos)
        except:
            p = 99
        if p == 1: return (255, 180, 0)
        if p == 2: return (192, 192, 192)
        if p == 3: return (205, 127, 50)
        return (220, 40, 40)

    return create_results_image(title, subtitle, rows, avatar_loader=_loader, card_color_func=_color)


def create_quali_results_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    return create_results_image(title, subtitle, rows)


def create_season_image(season: int, races: list[dict]) -> BytesIO:
    safe_races = races if races else []
    if not safe_races: safe_races = [
        {"round": 0, "event_name": "Нет данных", "country": "", "date": date.today().isoformat()}]

    races_with_dates = []
    today = date.today()
    for r in safe_races:
        try:
            rd = date.fromisoformat(r.get("date", ""))
        except:
            rd = today
        races_with_dates.append((r, rd))

    temp_img = Image.new("RGB", (100, 100))
    draw_tmp = ImageDraw.Draw(temp_img)
    title = f"Календарь сезона {season}"
    title_w, title_h = _text_size(draw_tmp, title, FONT_TITLE)

    img_width = 1800
    num_rows = len(races_with_dates)
    rows_per_col = (num_rows + 1) // 2
    row_height = 110
    line_spacing = 25
    header_gap = 40
    padding = 30

    img_height = padding + title_h + header_gap + rows_per_col * (row_height + line_spacing) + padding

    img = _create_vertical_gradient(img_width, img_height, BG_GRADIENT_TOP, BG_GRADIENT_BOT)
    draw = ImageDraw.Draw(img)

    x_title = (img_width - title_w) // 2
    draw.text((x_title, padding), title, font=FONT_TITLE, fill=(255, 255, 255))
    start_y = padding + title_h + header_gap

    col_width = (img_width - 2 * padding - 50) // 2
    left_x = padding
    right_x = padding + col_width + 50

    for i, (r, rd) in enumerate(races_with_dates):
        col_x = left_x if i < rows_per_col else right_x
        row_idx = i if i < rows_per_col else i - rows_per_col
        row_y = start_y + row_idx * (row_height + line_spacing)

        finished = rd < today
        fill = (35, 30, 30) if finished else (35, 45, 40)
        accent = (180, 50, 50) if finished else (50, 180, 100)

        draw.rounded_rectangle((col_x, row_y, col_x + col_width, row_y + row_height), radius=20, fill=fill)
        draw.rounded_rectangle((col_x, row_y, col_x + 10, row_y + row_height), radius=20, fill=accent)

        round_text = f"{int(r.get('round', 0)):02d}"
        ev = r.get("event_name", "")
        dt = rd.strftime("%d.%m")

        draw.text((col_x + 25, row_y + 35), round_text, font=FONT_ROW, fill=(100, 100, 120))
        draw.text((col_x + 100, row_y + 35), ev, font=FONT_ROW, fill=(255, 255, 255))
        draw.text((col_x + col_width - 120, row_y + 35), dt, font=FONT_ROW, fill=(200, 200, 200))

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf