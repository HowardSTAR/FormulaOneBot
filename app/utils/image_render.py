import hashlib
import io
import json
import math
import urllib
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Callable, Optional

import matplotlib
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from matplotlib import pyplot as plt, ticker

matplotlib.use('Agg')

_DRIVER_PHOTOS_CACHE = {}
_TEAM_LOGOS_CACHE = {}
_OPENF1_DRIVERS_CACHE = {}
_OPENF1_FETCHED = False

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
    ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"

    def load_font(name: str, size: int):
        try:
            return ImageFont.truetype(str(fonts_dir / name), size)
        except Exception:
            return ImageFont.load_default()

    font_title = load_font("Jost-Bold.ttf", 60)
    font_subtitle = load_font("Jost-Regular.ttf", 34)
    font_row = load_font("Jost-Medium.ttf", 44)
    font_table = load_font("Jost-Medium.ttf", 28)
    # Emoji шрифт больше не критичен для звезды, но оставим для других целей
    try:
        font_emoji = ImageFont.truetype(str(fonts_dir / "NotoEmoji-Regular.ttf"), 40)
    except:
        font_emoji = font_row

    return font_title, font_subtitle, font_row, font_emoji, font_table


FONT_TITLE, FONT_SUBTITLE, FONT_ROW, FONT_EMOJI, FONT_TABLE = _load_fonts()


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


def _download_image(url: str) -> Image.Image | None:
    """Универсальный скачиватель картинок в оперативную память"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'FormulaOneBot/1.0 (Contact: admin@example.com)'})
        with urllib.request.urlopen(req, timeout=4) as response:
            img_data = response.read()
            return Image.open(BytesIO(img_data)).convert("RGBA")
    except Exception as e:
        print(f"Ошибка загрузки {url}: {e}")
        return None


def _get_wiki_image_url(query: str) -> str | None:
    """Обращается к Wikipedia API для поиска исторического фото"""
    try:
        safe_query = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={safe_query}&pithumbsize=400&format=json"

        req = urllib.request.Request(url, headers={'User-Agent': 'FormulaOneBot/1.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                if "thumbnail" in page_info:
                    return page_info["thumbnail"]["source"]
    except Exception:
        pass
    return None


# Маппинг названий команд на варианты для поиска файлов машин.
# Red Bull и RB (Racing Bulls) — разные команды! Не используем "bull" — матчит обе.
_CAR_TEAM_ALIASES: dict[str, list[str]] = {
    "alpine": ["alpine"],
    "haas": ["haas"],
    "ferrari": ["ferrari", "scuderia"],
    "mercedes": ["mercedes", "amg"],
    "red_bull": ["red_bull", "redbull"],  # только "red" — не "bull", иначе матчит Racing Bulls
    "rb": ["rb", "racing_bulls", "vcarb", "alphatauri"],
    "aston_martin": ["aston_martin", "astonmartin"],
    "mclaren": ["mclaren"],
    "williams": ["williams"],
    "cadillac": ["cadillac"],
    "audi": ["audi"],
}

# Общие слова и частичные совпадения, которые НЕ должны матчить (bull матчит и Red Bull и Racing Bulls)
_CAR_GENERIC_WORDS = {"f1", "team", "racing", "formula", "grand", "prix", "bull"}


def get_car_image_path(team_name: str, season: int) -> Path | None:
    """Ищет изображение машины: assets/{year}/cars/, fallback — assets/car/."""
    assets_root = Path(__file__).resolve().parents[1] / "assets"
    year_cars = assets_root / str(season) / "cars"
    fallback_car = assets_root / "car"
    raw = (team_name or "").strip().lower().replace("-", " ")
    words = [w.replace(" ", "_") for w in raw.split() if w and w not in _CAR_GENERIC_WORDS]
    search_parts = list(dict.fromkeys(words))

    matched_key = ""
    for key, aliases in _CAR_TEAM_ALIASES.items():
        key_norm = key.replace(" ", "_")
        if key_norm in raw.replace(" ", "_") or any(a.replace(" ", "_") in raw.replace(" ", "_") for a in aliases):
            matched_key = key
            for a in aliases:
                sp = a.replace(" ", "_")
                if sp and sp not in search_parts:
                    search_parts.append(sp)
            break

    _is_red_bull = matched_key == "red_bull"

    def _matches(fpath: Path) -> bool:
        stem = fpath.stem.lower().replace(" ", "_")
        if not search_parts:
            return False
        if _is_red_bull and ("racing_bulls" in stem or "vcarb" in stem) and "red" not in stem:
            return False
        for sp in search_parts:
            if sp in _CAR_GENERIC_WORDS:
                continue
            if sp in stem or stem in sp:
                return True
        return False

    def _search_in_dir(dir_path: Path) -> Path | None:
        if not dir_path.exists():
            return None
        for f in sorted(dir_path.iterdir(), key=lambda p: p.name):
            if f.is_file() and not f.name.startswith(".") and _matches(f):
                return f
        raw_core = "_".join(w for w in raw.replace(" ", "_").split("_") if w and w not in _CAR_GENERIC_WORDS)
        if raw_core:
            for f in sorted(dir_path.iterdir(), key=lambda p: p.name):
                if f.is_file() and not f.name.startswith("."):
                    stem = f.stem.lower().replace(" ", "_")
                    if raw_core in stem or stem in raw_core:
                        return f
        return None

    result = _search_in_dir(year_cars)
    if result:
        return result
    result = _search_in_dir(fallback_car)
    if result:
        return result
    # Generic fallback: первый файл в assets/car/ (для сезонов без своей папки)
    if fallback_car.exists():
        for f in sorted(fallback_car.iterdir(), key=lambda p: p.name):
            if f.is_file() and not f.name.startswith("."):
                return f
    return None


def get_asset_path(year: int, category: str, target_name: str) -> Path | None:
    """Универсальный поиск локальных картинок (.png, .avif) в папке assets/YYYY/"""
    if not target_name:
        return None

    base_dir = Path(__file__).resolve().parents[1] / "assets" / str(year) / category
    if not base_dir.exists():
        return None

    search_name = target_name.replace("⭐️", "").replace("⭐", "").strip().lower()

    for file_path in base_dir.iterdir():
        if file_path.is_file() and search_name in file_path.stem.strip().lower():
            return file_path
    return None


def _get_online_driver_url(code: str, name: str) -> str | None:
    """ВСЕГДА ищет онлайн-ссылку на фото пилота из OpenF1 API."""
    global _OPENF1_DRIVERS_CACHE, _OPENF1_FETCHED

    if not _OPENF1_FETCHED:
        _OPENF1_FETCHED = True
        try:
            req = urllib.request.Request("https://api.openf1.org/v1/drivers?session_key=latest",
                                         headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                for d in data:
                    url = d.get('headshot_url')
                    if url:
                        acronym = d.get('name_acronym', '').strip().upper()
                        full_name = d.get('full_name', '').strip().lower()
                        if acronym:
                            _OPENF1_DRIVERS_CACHE[acronym] = url
                        if full_name:
                            _OPENF1_DRIVERS_CACHE[full_name] = url
        except Exception as e:
            print(f"Ошибка получения ссылок OpenF1: {e}")

    clean_code = code.replace("⭐️", "").replace("⭐", "").strip().upper()
    clean_name = name.strip().lower()

    return _OPENF1_DRIVERS_CACHE.get(clean_code) or _OPENF1_DRIVERS_CACHE.get(clean_name)


def _get_driver_photo(code: str, name: str, season: int) -> Image.Image | None:
    """Мастер-функция: скачивает онлайн или берет из папки для любого года."""
    cache_key = f"{season}_{code}_{name}"
    if cache_key in _DRIVER_PHOTOS_CACHE:
        return _DRIVER_PHOTOS_CACHE[cache_key]

    img = None

    # 1. МАГИЯ ОНЛАЙНА: Пытаемся получить фото с официальных серверов (работает всегда)
    online_url = _get_online_driver_url(code, name)
    if online_url:
        try:
            req = urllib.request.Request(online_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                img_data = response.read()
                img = Image.open(BytesIO(img_data)).convert("RGBA")
        except Exception as e:
            print(f"Не удалось скачать {name}: {e}")

    # 2. ЖЕЛЕЗОБЕТОННЫЙ ФОЛЛБЭК: Если пилот старый (его нет в OpenF1) или нет интернета, идем в папку
    if not img:
        img_path = get_asset_path(season, "pilots", name)
        if not img_path:
            img_path = get_asset_path(season, "pilots", code)

        if img_path:
            try:
                img = Image.open(img_path).convert("RGBA")
            except Exception:
                pass

    # 3. Сохраняем результат в кэш
    if img:
        _DRIVER_PHOTOS_CACHE[cache_key] = img
        return img

    return None


def _get_team_logo(code: str, name: str, season: int) -> Image.Image | None:
    """Каскадный поиск логотипа команды для ЛЮБОГО года"""
    cache_key = f"{season}_{code}_{name}"
    if cache_key in _TEAM_LOGOS_CACHE:
        return _TEAM_LOGOS_CACHE[cache_key]

    img = None

    # ШАГ 1: Локальная папка (assets/YYYY/teams/)
    img_path = get_asset_path(season, "teams", name) or get_asset_path(season, "teams", code)
    if img_path:
        try:
            img = Image.open(img_path).convert("RGBA")
        except Exception:
            pass

    # ШАГ 2: Википедия (добавляем " Formula One", чтобы точно найти лого Ф1, а не обычные машины)
    if not img:
        wiki_url = _get_wiki_image_url(f"{name} Formula One")
        if wiki_url:
            img = _download_image(wiki_url)

    if img:
        _TEAM_LOGOS_CACHE[cache_key] = img

    return img


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


def create_comparison_image(
        driver1_data: dict,
        driver2_data: dict,
        labels: List[str]
) -> BytesIO:
    """
    Строит график сравнения накопленных очков двух пилотов.
    driverX_data: {"code": "VER", "history": [25, 18, ...], "color": "#123456"}
    labels: список названий трасс (кратко)
    """
    # Настройка стиля (Темная тема F1)
    plt.style.use('dark_background')

    # Размеры и DPI
    fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
    fig.patch.set_facecolor('#1e1e23')  # Цвет фона вокруг графика
    ax.set_facecolor('#1e1e23')  # Цвет поля графика

    # Подготовка данных (кумулятивная сумма)
    y1 = []
    current = 0
    for p in driver1_data["history"]:
        current += p if p is not None else 0
        y1.append(current)

    y2 = []
    current = 0
    for p in driver2_data["history"]:
        current += p if p is not None else 0
        y2.append(current)

    # Обрезаем данные, если гонок прошло меньше, чем в календаре
    n_races = min(len(y1), len(y2), len(labels))
    x = range(n_races)
    y1 = y1[:n_races]
    y2 = y2[:n_races]
    labels = labels[:n_races]

    # --- РИСОВАНИЕ ---

    label1 = driver1_data.get("name") or driver1_data.get("code", "?")
    label2 = driver2_data.get("name") or driver2_data.get("code", "?")

    # Пилот 1
    color1 = driver1_data.get("color", "#ff8700")
    ax.plot(x, y1, label=label1, color=color1,
            linewidth=4, marker='o', markersize=8, markeredgecolor='white', markeredgewidth=1.5)

    # Пилот 2
    color2 = driver2_data.get("color", "#00d2be")
    ax.plot(x, y2, label=label2, color=color2,
            linewidth=4, marker='o', markersize=8, markeredgecolor='white', markeredgewidth=1.5)

    # Заливка под графиком (для лидера)
    # ax.fill_between(x, y1, y2, where=(y1 > y2), interpolate=True, color=color1, alpha=0.1)
    # ax.fill_between(x, y1, y2, where=(y2 > y1), interpolate=True, color=color2, alpha=0.1)

    # --- ОФОРМЛЕНИЕ ---

    # Заголовок
    plt.title(f"Battle: {label1} vs {label2}",
              fontsize=20, fontweight='bold', color='white', pad=20)

    # Оси
    ax.grid(color='#444444', linestyle='--', linewidth=0.5, alpha=0.5)

    # Ось X (Трассы) - показываем каждую, если влезает, или через одну
    ax.set_xticks(x)
    # Если трасс много (>10), поворачиваем подписи
    rotation = 45 if n_races > 5 else 0
    ax.set_xticklabels(labels, rotation=rotation, ha='right', fontsize=10, color='#cccccc')

    # Ось Y (Очки)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.tick_params(axis='y', colors='#cccccc', labelsize=12)

    # Убираем рамки сверху и справа
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#666666')
    ax.spines['left'].set_color('#666666')

    # Легенда
    legend = ax.legend(fontsize=14, frameon=True, facecolor='#2b2b30', edgecolor='none')
    for text in legend.get_texts():
        text.set_color("white")

    # Добавляем финальный счет текстом
    final_score_text = f"{y1[-1]} - {y2[-1]}"
    plt.text(0.98, 0.05, final_score_text, transform=ax.transAxes,
             fontsize=24, fontweight='bold', color='white', ha='right', alpha=0.3)

    # Сохранение
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor='#1e1e23')
    buf.seek(0)
    plt.close(fig)  # Обязательно закрываем, чтобы очистить память

    return buf


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
            return _get_driver_photo(code, name, datetime.now().year)

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
def create_driver_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]], season: int) -> BytesIO:
    def _loader(code: str, name: str):
        return _get_driver_photo(code, name, season) # Прокидываем год

    def _color(pos: str):
        try:
            p = int(pos)
        except:
            p = 99
        if p == 1: return (255, 180, 0)
        if p == 2: return (192, 192, 192)
        if p == 3: return (205, 127, 50)
        return (80, 100, 140)

    return create_results_image(title, subtitle, rows, avatar_loader=_loader, card_color_func=_color)


def create_constructor_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]], season: int) -> BytesIO:
    def _loader(code: str, name: str):
        return _get_team_logo(code, name, season) # Прокидываем год

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


def create_f1_style_classification_image(
    event_name: str,
    session_type: str,
    rows: List[dict],
    season: int,
    favorite_driver_codes: set[str] | None = None,
) -> BytesIO:
    """
    Создаёт изображение в стиле официальной таблицы F1 (Practice/Qualifying/Race Classification).
    rows: list of dict с ключами pos, driver, team, gap_or_time, points (для гонки), driver_code (опционально).
    Столбцы: POS | DRIVER (имя + лого) | FASTEST (квалификация) или PTS (гонка).
    Квалификация: Q1 (1-10), Q2 (11-16), Q3 (17-22) — разные цвета строк.
    Гонка: топ 3 — золото/серебро/бронза, топ 4-10 — выделение, остальные — без выделения.
    Избранные пилоты — звёздочка ⭐ в колонке DRIVER.
    """
    HEADER_BG = (55, 60, 70)
    ROW_ALT = (35, 38, 45)
    ROW_BG = (28, 30, 38)
    HEADER_TEXT = (200, 200, 210)
    # Цвета квалификации: Q1 (1-10), Q2 (11-16), Q3 (17-22)
    ROW_Q1 = (30, 55, 45)  # тёмно-зелёный для топ-10
    ROW_Q1_ALT = (25, 48, 38)
    ROW_Q2 = (30, 40, 55)  # синеватый для 11-16
    ROW_Q2_ALT = (25, 35, 48)
    ROW_Q3 = (35, 35, 40)  # нейтральный для 17-22
    ROW_Q3_ALT = (30, 30, 35)
    # Цвета гонки: топ 3 и топ 4-10
    ROW_GOLD = (55, 48, 25)
    ROW_SILVER = (50, 50, 55)
    ROW_BRONZE = (55, 40, 30)
    ROW_TOP10 = (38, 42, 50)
    ROW_TOP10_ALT = (35, 38, 45)
    FAV_BORDER = (255, 215, 0)  # золотая рамка для избранных

    LOGO_SIZE = 36
    ROW_HEIGHT = 48
    PADDING = 40
    CELL_PAD = 16
    fav_codes = {str(c).upper() for c in (favorite_driver_codes or set())}

    if not rows:
        rows = [{"pos": "-", "driver": "Нет данных", "team": "", "gap_or_time": "-"}]

    temp_img = Image.new("RGB", (100, 100))
    draw_tmp = ImageDraw.Draw(temp_img)

    event_upper = (event_name or "GRAND PRIX").upper()
    session_upper = (session_type or "CLASSIFICATION").upper()

    title_w, title_h = _text_size(draw_tmp, event_upper, FONT_SUBTITLE)
    sub_w, sub_h = _text_size(draw_tmp, session_upper, FONT_TABLE)

    # Столбцы: POS | DRIVER (имя + лого) | FASTEST (квалиф) или PTS (гонка)
    pos_w = 55
    driver_w = 320
    right_col_w = 70  # PTS для гонки (0-26) или FASTEST для квалиф — компактно
    table_width = pos_w + driver_w + right_col_w + 3 * CELL_PAD
    img_width = table_width + 2 * PADDING

    header_h = 50
    table_h = len(rows) * ROW_HEIGHT
    img_height = PADDING + title_h + 20 + sub_h + 20 + header_h + table_h + PADDING

    img = Image.new("RGB", (img_width, img_height), (25, 27, 35))
    draw = ImageDraw.Draw(img)

    x_pos = PADDING
    x_driver = x_pos + pos_w + CELL_PAD
    x_right = x_driver + driver_w + CELL_PAD

    cur_y = PADDING
    draw.text(((img_width - title_w) // 2, cur_y), event_upper, font=FONT_SUBTITLE, fill=(255, 255, 255))
    cur_y += title_h + 20
    draw.text(((img_width - sub_w) // 2, cur_y), session_upper, font=FONT_TABLE, fill=HEADER_TEXT)
    cur_y += sub_h + 20

    is_qualifying = "QUALIFYING" in (session_type or "").upper()

    # Заголовки — чётко по своим колонкам
    draw.rectangle((PADDING, cur_y, img_width - PADDING, cur_y + header_h), fill=HEADER_BG)
    right_label = "PTS" if not is_qualifying else "FASTEST"
    draw.text((x_pos + (pos_w - _text_size(draw, "POS", FONT_TABLE)[0]) // 2, cur_y + (header_h - _text_size(draw, "1", FONT_TABLE)[1]) // 2 - 2), "POS", font=FONT_TABLE, fill=HEADER_TEXT)
    draw.text((x_driver, cur_y + (header_h - _text_size(draw, "A", FONT_TABLE)[1]) // 2 - 2), "DRIVER", font=FONT_TABLE, fill=HEADER_TEXT)
    draw.text((x_right + right_col_w - _text_size(draw, right_label, FONT_TABLE)[0] - CELL_PAD, cur_y + (header_h - _text_size(draw, "A", FONT_TABLE)[1]) // 2 - 2), right_label, font=FONT_TABLE, fill=HEADER_TEXT)
    cur_y += header_h

    for i, r in enumerate(rows):
        row_y = cur_y + i * ROW_HEIGHT
        pos_val = r.get("pos", 0)
        try:
            pos_int = int(pos_val) if pos_val not in ("-", "?", "", None) else 999
        except (TypeError, ValueError):
            pos_int = 999

        # Выбор цвета строки
        if is_qualifying:
            if pos_int <= 10:
                fill = ROW_Q1_ALT if i % 2 == 1 else ROW_Q1
            elif pos_int <= 16:
                fill = ROW_Q2_ALT if i % 2 == 1 else ROW_Q2
            else:
                fill = ROW_Q3_ALT if i % 2 == 1 else ROW_Q3
        else:
            if pos_int == 1:
                fill = ROW_GOLD
            elif pos_int == 2:
                fill = ROW_SILVER
            elif pos_int == 3:
                fill = ROW_BRONZE
            elif pos_int <= 10:
                fill = ROW_TOP10_ALT if i % 2 == 1 else ROW_TOP10
            else:
                fill = ROW_ALT if i % 2 == 1 else ROW_BG

        draw.rectangle((PADDING, row_y, img_width - PADDING, row_y + ROW_HEIGHT), fill=fill)

        # Рамка для избранного пилота
        code = str(r.get("driver_code", "") or "").strip().upper()
        is_fav = code and code in fav_codes
        if is_fav:
            draw.rectangle(
                (PADDING + 2, row_y + 2, img_width - PADDING - 2, row_y + ROW_HEIGHT - 2),
                outline=FAV_BORDER,
                width=2,
            )

        pos = str(r.get("pos", ""))
        driver = str(r.get("driver", ""))[:22]
        team = str(r.get("team", ""))
        if is_qualifying:
            right_val = str(r.get("gap_or_time", "-"))
        else:
            pts = r.get("points")
            try:
                right_val = str(int(float(pts))) if pts is not None and pts != "" else "0"
            except (TypeError, ValueError):
                right_val = "0"

        draw.text((x_pos + (pos_w - _text_size(draw, pos, FONT_TABLE)[0]) // 2, row_y + (ROW_HEIGHT - _text_size(draw, pos, FONT_TABLE)[1]) // 2 - 2), pos, font=FONT_TABLE, fill=TEXT_COLOR)

        # DRIVER: [⭐] имя [логотип справа]
        driver_x = x_driver
        if is_fav:
            _draw_star(draw, x_driver + 14, row_y + ROW_HEIGHT // 2, 10, FAV_BORDER)
            driver_x += 28
        draw.text((driver_x, row_y + (ROW_HEIGHT - _text_size(draw, driver[:18], FONT_TABLE)[1]) // 2 - 2), driver[:18], font=FONT_TABLE, fill=TEXT_COLOR)

        logo_img = _get_team_logo(team, team, season) if team else None
        logo_x = x_driver + driver_w - LOGO_SIZE - 4
        if logo_img:
            logo_img = logo_img.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
            paste_x = int(logo_x)
            paste_y = row_y + (ROW_HEIGHT - LOGO_SIZE) // 2
            mask = logo_img.split()[3] if logo_img.mode == "RGBA" else None
            img.paste(logo_img, (paste_x, paste_y), mask)
        elif team:
            draw.text((logo_x, row_y + (ROW_HEIGHT - _text_size(draw, team[:6], FONT_TABLE)[1]) // 2 - 2), team[:6], font=FONT_TABLE, fill=TEXT_COLOR)

        right_x = x_right + right_col_w - _text_size(draw, right_val, FONT_TABLE)[0] - CELL_PAD
        draw.text((right_x, row_y + (ROW_HEIGHT - _text_size(draw, right_val, FONT_TABLE)[1]) // 2 - 2), right_val, font=FONT_TABLE, fill=TEXT_COLOR)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


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


def create_testing_results_image(results_df, title: str):
    """
    Рисует таблицу результатов тестов.
    Колонки: Pos, Driver, Team, Time, Laps
    """
    # Настройка стилей (темная тема)
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis('off')
    fig.patch.set_facecolor('#15151e')

    # Подготовка данных
    # FastF1 возвращает: Position, Abbreviation, TeamName, Time, Laps (иногда)

    # Берем топ-20
    df = results_df.head(20).copy()

    table_data = []
    for _, row in df.iterrows():
        pos = str(int(row.get('Position', 0))) if pd.notnull(row.get('Position')) else "-"
        driver = str(row.get('Abbreviation', '???'))
        team = str(row.get('TeamName', ''))

        # Время
        time_val = str(row.get('Time', ''))
        # Форматируем timedelta (0 days 00:01:30.123 -> 1:30.123)
        if "days" in time_val:
            time_val = time_val.split("days")[-1].strip()
        if "." in time_val:
            time_val = time_val[:-3]  # Убираем лишние микросекунды

        laps = str(int(row.get('Laps', 0))) if pd.notnull(row.get('Laps')) else "0"

        table_data.append([pos, driver, team, time_val, laps])

    # Колонки
    col_labels = ["Pos", "Driver", "Team", "Best Time", "Laps"]

    # Рисуем таблицу
    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        loc='center',
        cellLoc='center',
        colColours=['#e10600'] * 5
    )

    # Стилизация таблицы
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.1, 1.8)

    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#2c2c35')
        cell.set_linewidth(1)
        if key[0] == 0:  # Заголовок
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#e10600')
        else:
            cell.set_facecolor('#1e1e26')
            cell.set_text_props(color='white')

    # Заголовок
    plt.title(f"🧪 {title}", color='white', fontsize=16, pad=20, weight='bold')

    # Сохраняем
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='#15151e')
    buf.seek(0)
    plt.close(fig)
    return buf