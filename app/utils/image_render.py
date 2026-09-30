import hashlib
import io
import json
import math
import urllib
import unicodedata
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Callable, Optional

import matplotlib
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from matplotlib import pyplot as plt, ticker
from app.utils.default import DRIVER_CODE_TO_FILE

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
        req = urllib.request.Request(url, headers={'User-Agent': 'TurboTears/1.0 (independent motorsport service)'})
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

        req = urllib.request.Request(url, headers={'User-Agent': 'TurboTears/1.0'})
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

    season_dir = Path(__file__).resolve().parents[1] / "assets" / str(year)
    base_dir = season_dir / category
    if category != "teams" and not base_dir.exists():
        return None

    search_name = target_name.replace("⭐️", "").replace("⭐", "").strip().lower()

    if category == "pilots":
        def normalize(value):
            return "".join(c for c in unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower() if c.isalnum())
        identity = next((code for code, filename in DRIVER_CODE_TO_FILE.items()
                         if normalize(search_name) in {normalize(code), normalize(Path(filename).stem)}), None)
        candidates = {normalize(search_name)}
        if identity:
            for suffix in (".webp", ".jpg"):
                verified = base_dir / f"{identity}{suffix}"
                if verified.is_file():
                    return verified
            candidates.add(normalize(Path(DRIVER_CODE_TO_FILE[identity]).stem))
        return next((file for file in sorted(base_dir.iterdir())
                     if file.is_file() and file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}
                     and normalize(file.stem) in candidates), None)

    if category == "teams":
        aliases = {
            "redbull": {"redbullracing"}, "redbullracing": {"redbull"},
            "rb": {"racingbulls", "rbf1team"}, "rbf1team": {"racingbulls", "rb"},
            "racingbulls": {"rbf1team", "rb"}, "vcarb": {"racingbulls"},
            "alpinef1team": {"alpine"}, "haas": {"haasf1team"},
            "sauber": {"kicksauber"}, "astonmartin": {"astonmartinf1team"},
            "cadillacf1team": {"cadillac"}, "audif1team": {"audi"},
        }
        identity = _normalize_team_key(search_name)
        candidates = {identity, *aliases.get(identity, set())}
        directories = [season_dir / "team-logos", base_dir]
        return next((file for directory in directories if directory.is_dir() for file in sorted(directory.iterdir())
                     if file.is_file() and file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}
                     and _normalize_team_key(file.stem) in candidates), None)
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
    """Local season portraits take precedence over online images and their cache."""
    local = get_asset_path(season, "pilots", code) or get_asset_path(season, "pilots", name)
    if local:
        with Image.open(local) as image:
            return image.convert("RGBA")
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
    normalized = f"{code} {name}".lower().replace("_", " ")
    team_aliases: list[str] = []
    if any(token in normalized for token in ("rb f1 team", "rbf1team", "racing bulls", "visa cash app rb")):
        team_aliases.extend(["RACING BULLS", "RB F1 Team", "RB"])

    candidates = [name, code, *team_aliases]
    img_path = None
    for candidate in candidates:
        img_path = get_asset_path(season, "teams", candidate)
        if img_path:
            break

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


def create_comparison_image(driver1_data: dict, driver2_data: dict, labels: List[str]) -> BytesIO:
    """Official cumulative points and weekend deltas; None is a gap, not zero."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import FancyBboxPatch
    font_path = Path(__file__).resolve().parents[1] / "assets/fonts/Jost-Regular.ttf"
    bold_path = font_path.with_name("Jost-Bold.ttf")
    regular = FontProperties(fname=str(font_path)) if font_path.is_file() else FontProperties()
    bold = FontProperties(fname=str(bold_path)) if bold_path.is_file() else FontProperties(weight="bold")
    n = min(len(labels), len(driver1_data["history"]), len(driver2_data["history"]))
    if not n:
        raise ValueError("Нет данных для графиков.")
    figure = Figure(figsize=(10.8, 12), dpi=120, facecolor="#0b0c10")
    FigureCanvasAgg(figure)
    figure.text(.05, .966, "TURBOTEARS  /  RACE INTELLIGENCE", color="#989aa5", fontsize=14, fontproperties=bold)
    figure.text(.95, .966, str(driver1_data.get("season") or ""), color="#989aa5", fontsize=14, ha="right", fontproperties=bold)
    heading = "СРАВНЕНИЕ КОМАНД" if driver1_data.get("kind") == "teams" else "СРАВНЕНИЕ ПИЛОТОВ"
    figure.text(.05, .916, heading, color="#f5f5f7", fontsize=32, fontproperties=bold)
    figure.text(.05, .878, "Полный зачёт, включая спринты и корректировки", color="#989aa5", fontsize=15, fontproperties=regular)
    axes = figure.subplots(2, 1, gridspec_kw={"height_ratios": [1.5, 1]})
    figure.subplots_adjust(left=.085, right=.955, top=.69, bottom=.16, hspace=.35)
    colors = [driver1_data.get("color", "#ff625d"), driver2_data.get("color", "#00d2be")]
    series = [driver1_data, driver2_data]
    histories = []
    for index, data in enumerate(series):
        history, accumulated = [], 0.0
        for point in data["history"][:n]:
            if point is None:
                history.append(float("nan"))
            elif data.get("cumulative"):
                history.append(float(point))
            else:
                accumulated += float(point)
                history.append(accumulated)
        histories.append(history)
        x = .05 + index * .46
        card = FancyBboxPatch((x, .751), .435, .081, boxstyle="round,pad=0.009,rounding_size=0.012",
                              transform=figure.transFigure, facecolor="#17191f", edgecolor=colors[index], linewidth=1)
        figure.add_artist(card)
        label = str(data.get("name") or data.get("code") or "—")
        figure.text(x + .012, .802, label, color=colors[index], fontsize=max(12, 18 - max(0, len(label) - 18) // 3), fontproperties=bold)
        total = data.get("total_points", history[-1])
        score = "—" if total is None or not math.isfinite(float(total)) else f"{float(total):g}"
        figure.text(x + .012, .765, f"{score} очков в опубликованном зачёте", color="#f5f5f7", fontsize=14, fontproperties=regular)
        axes[0].plot(range(n), history, color=colors[index], marker="o", markersize=4, linewidth=2.7, label=label)
        deltas = [value - (history[i - 1] if i else 0) for i, value in enumerate(history)]
        axes[1].bar([i + (-.19 if index == 0 else .19) for i in range(n)], deltas, width=.36, color=colors[index])
    for ax, title in zip(axes, ["ОЧКИ ПОСЛЕ КАЖДОГО ЭТАПА", "ИЗМЕНЕНИЕ ОЧКОВ ЗА УИК-ЭНД"]):
        ax.set_facecolor("#0b0c10")
        ax.set_title(title, loc="left", pad=16, color="#f5f5f7", fontsize=16, fontproperties=bold)
        ax.grid(axis="y", color="#34343d", linewidth=.6, alpha=.7)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=6))
        ax.tick_params(colors="#989aa5", labelsize=10)
        for edge in ("top", "right"):
            ax.spines[edge].set_visible(False)
        for edge in ("left", "bottom"):
            ax.spines[edge].set_color("#34343d")
        ax.set_xlim(-.6, n - .4)
        ax.set_xticks(range(n))
    axes[0].set_xticklabels([str(value) for value in driver1_data.get("rounds", range(1, n + 1))][:n])
    axes[1].set_xticklabels([str(label)[:17] for label in labels[:n]], rotation=48, ha="right", fontsize=9, fontproperties=regular)
    axes[1].axhline(0, color="#989aa5", linewidth=.6)
    figure.text(.05, .069, "Пропуск данных не означает 0 очков. Изменение включает штрафы и пересчёты.",
                color="#989aa5", fontsize=11, fontproperties=regular)
    figure.text(.05, .026, "F1HUB.RU", color="#ff625d", fontsize=13, fontproperties=bold)
    figure.text(.95, .026, "ОФИЦИАЛЬНЫЙ ЗАЧЁТ", color="#989aa5", fontsize=12, ha="right", fontproperties=regular)
    output = BytesIO()
    figure.savefig(output, format="png", facecolor=figure.get_facecolor())
    output.seek(0)
    figure.clear()
    return output


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
def _standings_rows(rows):
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append({"team": "", "favorite": False, **row})
        else:
            pos, code, name, points = map(str, row[:4])
            result.append({"pos": pos, "code": code.replace("⭐️", "").replace("⭐", "").strip(),
                           "name": name.replace("⭐️", "").replace("⭐", "").strip(),
                           "points": points.replace(" очк.", ""), "team": "",
                           "favorite": "⭐" in code or "⭐" in name})
    return result


def _local_standings_art(code, name, season, category):
    path = get_asset_path(season, category, code) or get_asset_path(season, category, name)
    if path is not None:
        with Image.open(path) as source:
            return source.convert("RGBA")
    return None


def create_driver_standings_image(title: str, subtitle: str, rows, season: int) -> BytesIO:
    from app.utils.standings_card import render_standings
    return render_standings(title, subtitle, _standings_rows(rows), season, "drivers",
                            lambda code, name, year: _local_standings_art(code, name, year, "pilots"))


def create_constructor_standings_image(title: str, subtitle: str, rows, season: int) -> BytesIO:
    from app.utils.standings_card import render_standings
    return render_standings(title, subtitle, _standings_rows(rows), season, "teams",
                            lambda code, name, year: _local_standings_art(code, name, year, "teams"))


def create_quali_results_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    return create_results_image(title, subtitle, rows)


def create_f1_style_classification_image(
    event_name: str,
    session_type: str,
    rows: List[dict],
    season: int,
    favorite_driver_codes: set[str] | None = None,
) -> BytesIO:
    """Render race and qualifying results in the shared TurboTears visual style."""
    from app.utils.classification_card import render_classification

    def portrait(code, name, year):
        # Season-specific local artwork avoids network delays and wrong-year photos.
        path = get_asset_path(year, "pilots", code) or get_asset_path(year, "pilots", name)
        if path is None and name:
            path = get_asset_path(year, "pilots", name.split()[-1])
        if path:
            with Image.open(path) as source:
                portrait_image = source.convert("RGBA")
                bounds = portrait_image.getbbox()
                if bounds:
                    portrait_image = portrait_image.crop(bounds)
                # Full-body assets become close-up portraits, like the website cards.
                portrait_image = portrait_image.crop((0, 0, portrait_image.width,
                    min(portrait_image.height, int(portrait_image.width * 1.4))))
                return portrait_image
        return None

    return render_classification(
        event_name, session_type, rows, season, favorite_driver_codes, portrait,
    )


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
