from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Callable
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from app.utils.default import DRIVER_CODE_TO_FILE, _TEAM_KEY_TO_FILE

# Кеш загруженных фотографий пилотов
_DRIVER_PHOTOS_CACHE: dict[str, Image.Image] = {}

# Кеш логотипов команд
_TEAM_LOGOS_CACHE: dict[str, Image.Image] = {}

# Визуальные константы (Modern Dark Theme)
BG_GRADIENT_TOP = (25, 30, 45)  # Темно-синий верх
BG_GRADIENT_BOT = (10, 10, 15)  # Почти черный низ
CARD_BG_COLOR = (35, 40, 55)  # Основной цвет карточек
SHADOW_COLOR = (0, 0, 0)  # Цвет тени
TEXT_COLOR = (240, 240, 250)
ACCENT_RED = (225, 6, 0)  # F1 Red

# Сдвиг текста
TEXT_V_SHIFT = -15


# --- Загрузка шрифтов (без изменений) ---

def _load_fonts() -> tuple[
    ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"

    try:
        font_title = ImageFont.truetype(str(fonts_dir / "Jost-Bold.ttf"), 60)
        font_subtitle = ImageFont.truetype(str(fonts_dir / "Jost-Regular.ttf"), 34)
        font_row = ImageFont.truetype(str(fonts_dir / "Jost-Medium.ttf"), 44)
        try:
            font_emoji = ImageFont.truetype(str(fonts_dir / "NotoEmoji-Regular.ttf"), 40)
        except Exception:
            font_emoji = font_row
    except Exception:
        try:
            font_title = ImageFont.truetype("Jost-Bold.ttf", 60)
            font_subtitle = ImageFont.truetype("Jost-Regular.ttf", 34)
            font_row = ImageFont.truetype("Jost-Medium.ttf", 44)
            font_emoji = font_row
        except Exception:
            # запасной вариант
            font_title = font_subtitle = font_row = font_emoji = ImageFont.load_default()

    return font_title, font_subtitle, font_row, font_emoji


def _normalize_team_key(text: str) -> str:
    import re
    s = (text or "").lower()
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


FONT_TITLE, FONT_SUBTITLE, FONT_ROW, FONT_EMOJI = _load_fonts()


def _get_driver_photo(code: str) -> Image.Image | None:
    code = code.upper()
    if code not in DRIVER_CODE_TO_FILE:
        return None

    if code in _DRIVER_PHOTOS_CACHE:
        return _DRIVER_PHOTOS_CACHE[code]

    pilots_dir = Path(__file__).resolve().parents[1] / "assets" / "pilots"
    img_path = pilots_dir / DRIVER_CODE_TO_FILE[code]
    if not img_path.exists():
        return None

    try:
        img = Image.open(img_path).convert("RGB")
    except Exception:
        return None

    _DRIVER_PHOTOS_CACHE[code] = img
    return img


def _get_team_logo(name_or_code: str) -> Image.Image | None:
    key = _normalize_team_key(name_or_code)
    if not key:
        return None

    if key in _TEAM_LOGOS_CACHE:
        return _TEAM_LOGOS_CACHE[key]

    filename = _TEAM_KEY_TO_FILE.get(key)
    if not filename:
        return None

    teams_dir = Path(__file__).resolve().parents[1] / "assets" / "teams"
    img_path = teams_dir / filename
    if not img_path.exists():
        return None

    try:
        img = Image.open(img_path).convert("RGBA")
    except Exception:
        return None

    _TEAM_LOGOS_CACHE[key] = img
    return img


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    else:
        w, h = draw.textsize(text, font=font)
    return w, h


def _create_vertical_gradient(width: int, height: int, top_color: tuple, bottom_color: tuple) -> Image.Image:
    """Генерирует фон с вертикальным градиентом."""
    base = Image.new('RGB', (width, height), top_color)

    # Чтобы не считать каждый пиксель долго, делаем градиент высотой H и шириной 1, затем растягиваем
    gradient_strip = Image.new('RGB', (1, height), top_color)
    draw = ImageDraw.Draw(gradient_strip)

    r1, g1, b1 = top_color
    r2, g2, b2 = bottom_color

    # Рисуем полоску 1xHeight
    for y in range(height):
        ratio = y / height
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        draw.point((0, y), fill=(r, g, b))

    # Растягиваем на всю ширину
    return gradient_strip.resize((width, height), resample=Image.Resampling.NEAREST)


def create_results_image(
        title: str,
        subtitle: str,
        rows: List[Tuple[str, str, str, str]],
        avatar_loader: Callable[[str, str], Image.Image | None] | None = None,
        card_color_func: Callable[[str], tuple[int, int, int]] | None = None,
) -> BytesIO:
    """
    Основная функция рисования результатов (гонка, квала, зачеты).
    С обновленным дизайном (градиенты, тени).
    """
    # --- Настройки макета ---
    padding = 30
    header_gap = 50
    line_spacing = 30
    row_height = 120
    avatar_size = 90

    # Шрифты
    font_title = FONT_TITLE
    font_subtitle = FONT_SUBTITLE
    font_row = FONT_ROW
    font_emoji = FONT_EMOJI

    if avatar_loader is None:
        def avatar_loader(code: str, name: str) -> Image.Image | None:  # type: ignore[no-redef]
            return _get_driver_photo(code)

    safe_rows = rows if rows else [("—", "", "Нет данных", "")]

    # 1. Расчет размеров
    temp_img = Image.new("RGB", (100, 100))
    draw_tmp = ImageDraw.Draw(temp_img)

    title_w, title_h = _text_size(draw_tmp, title, font_title)
    subtitle_w, subtitle_h = _text_size(draw_tmp, subtitle, font_subtitle)

    num_rows = len(safe_rows)
    rows_per_col = (num_rows + 1) // 2

    # Ищем самую длинную строку для ширины колонки
    max_row_text = ""
    for pos, code, name, pts in safe_rows:
        candidate = f"{pos}. {name} {pts}000"  # запас
        if len(candidate) > len(max_row_text):
            max_row_text = candidate
    row_text_w, _ = _text_size(draw_tmp, max_row_text, font_row)

    min_width = 1800
    img_width = max(
        min_width,
        title_w + 2 * padding,
        subtitle_w + 2 * padding,
        row_text_w + 2 * padding,
    )

    img_height = (
            padding
            + title_h
            + header_gap
            + subtitle_h
            + header_gap
            + rows_per_col * (row_height + line_spacing)
            + padding
    )

    # 2. Создаем фон
    img = _create_vertical_gradient(img_width, img_height, BG_GRADIENT_TOP, BG_GRADIENT_BOT)
    draw = ImageDraw.Draw(img, "RGBA")  # RGBA для прозрачности, если понадобится

    # 3. Рисуем заголовок
    cur_y = padding
    x_title = (img_width - title_w) // 2
    # Небольшая тень заголовка
    draw.text((x_title + 2, cur_y + 2), title, font=font_title, fill=(0, 0, 0))
    draw.text((x_title, cur_y), title, font=font_title, fill=(255, 255, 255))

    cur_y += title_h + 15
    x_sub = (img_width - subtitle_w) // 2
    draw.text((x_sub, cur_y), subtitle, font=font_subtitle, fill=(180, 180, 200))

    cur_y += subtitle_h + 20

    # Декоративная линия (F1 Red)
    line_w = 400
    line_x_start = (img_width - line_w) // 2
    draw.line(
        (line_x_start, cur_y, line_x_start + line_w, cur_y),
        fill=ACCENT_RED,
        width=4,
    )
    cur_y += 40  # отступ до карточек

    start_y = cur_y

    # 4. Колонки
    gap_between_cols = 50
    col_width = (img_width - 2 * padding - gap_between_cols) // 2
    left_x = padding
    right_x = padding + col_width + gap_between_cols

    rows_left = safe_rows[:rows_per_col]
    rows_right = safe_rows[rows_per_col:]

    # Палитра по умолчанию
    def _default_card_color_for_pos(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p <= 3:
            return (255, 140, 60)  # ярче
        if p <= 10:
            return (60, 200, 160)  # бирюза
        return (80, 90, 120)  # серый

    color_for_pos = card_color_func or _default_card_color_for_pos

    def _draw_row(col_x: int, row_y: int,
                  pos: str, code: str, name: str, pts: str) -> None:

        card_x0 = col_x
        card_y0 = row_y
        card_x1 = col_x + col_width
        card_y1 = row_y + row_height

        accent = color_for_pos(pos)

        # --- ТЕНЬ КАРТОЧКИ ---
        shadow_offset = 6
        draw.rounded_rectangle(
            (card_x0 + shadow_offset, card_y0 + shadow_offset,
             card_x1 + shadow_offset, card_y1 + shadow_offset),
            radius=24,
            fill=SHADOW_COLOR
        )

        # --- ФОН КАРТОЧКИ ---
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x1, card_y1),
            radius=24,
            fill=CARD_BG_COLOR,
            outline=(60, 65, 80),  # тонкая обводка
            width=1
        )

        # --- ЦВЕТНАЯ ПОЛОСКА (Акцент) ---
        # Делаем её чуть шире и интереснее
        strip_width = 12
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x0 + strip_width, card_y1),
            corners=(True, False, False, True),  # Только левые углы (PIL >= 10.0), но у нас старый PIL скорее всего
            radius=24,
            fill=accent,
        )
        # Хак для старого PIL: рисуем прямоугольник поверх, чтобы "обрезать" скругление справа
        draw.rectangle(
            (card_x0 + strip_width - 5, card_y0, card_x0 + strip_width, card_y1),
            fill=accent
        )

        # Внутренние координаты
        inner_y0 = card_y0 + 10
        inner_y1 = card_y1 - 10
        inner_y_center = (inner_y0 + inner_y1) // 2

        block_gap = 12
        block_pad_x = 16

        # --- Расчет ширин блоков ---
        pts_w, pts_h = _text_size(draw, pts, font_row)
        pts_block_w = pts_w + block_pad_x * 2

        pos_w, pos_h = _text_size(draw, pos, font_row)
        pos_block_w = max(80, pos_w + block_pad_x * 2)

        avatar_block_w = avatar_size  # Квадрат (круг)

        # Координаты X (справа налево для очков, слева направо для остального)
        pts_x1 = card_x1 - 24
        pts_x0 = pts_x1 - pts_block_w

        pos_x0 = card_x0 + 24 + strip_width  # отступ от цветной полоски
        pos_x1 = pos_x0 + pos_block_w

        avatar_x0 = pos_x1 + block_gap
        avatar_x1 = avatar_x0 + avatar_block_w

        name_x0 = avatar_x1 + block_gap * 2
        name_x1 = pts_x0 - block_gap

        # --- АВАТАР ---
        # Фоновый круг под аватар
        avatar_center_x = (avatar_x0 + avatar_x1) // 2
        avatar_center_y = inner_y_center

        # Рисуем подложку под аватар
        draw.ellipse(
            (avatar_x0, avatar_center_y - avatar_size // 2,
             avatar_x1, avatar_center_y + avatar_size // 2),
            fill=(25, 30, 45)
        )

        raw_code = code.replace("⭐️", "").replace("⭐", "").strip().upper()
        if len(raw_code) > 3: raw_code = raw_code[-3:]

        base_img = avatar_loader(raw_code, name)  # type: ignore

        if base_img is not None:
            avatar = base_img.resize((avatar_size, avatar_size), Image.LANCZOS)
            # Маска для круглой обрезки
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

            paste_x = avatar_center_x - avatar_size // 2
            paste_y = avatar_center_y - avatar_size // 2

            img.paste(avatar, (paste_x, paste_y), mask)

        # --- ПОЗИЦИЯ ---
        # Рисуем просто текст, без плашки, так чище в новом дизайне
        pos_tx = pos_x0 + (pos_block_w - pos_w) // 2
        pos_ty = inner_y_center + TEXT_V_SHIFT - pos_h // 2
        draw.text((pos_tx, pos_ty), pos, font=font_row, fill=(180, 190, 200))

        # --- ОЧКИ ---
        # Плашка под очки (чуть светлее фона)
        draw.rounded_rectangle(
            (pts_x0, inner_y0 + 10, pts_x1, inner_y1 - 10),
            radius=12,
            fill=(45, 50, 65)
        )
        pts_tx = pts_x0 + (pts_block_w - pts_w) // 2
        pts_ty = inner_y_center + TEXT_V_SHIFT - pts_h // 2
        draw.text((pts_tx, pts_ty), pts, font=font_row, fill=TEXT_COLOR)

        # --- ИМЯ ---
        # Обработка имени и звездочки
        raw_code_for_star = code.strip()
        raw_name_for_star = name.strip()
        has_star = ("⭐" in raw_code_for_star) or ("⭐" in raw_name_for_star)

        clean_name = raw_name_for_star.replace("⭐️", "").replace("⭐", "").strip()
        base_name_text = clean_name or name

        max_name_width = name_x1 - name_x0

        star_text = "⭐️" if has_star else ""
        star_w = 0
        star_gap = 10
        if star_text:
            star_w, _ = _text_size(draw, star_text, font_emoji)

        name_to_draw = base_name_text
        name_w, name_h = _text_size(draw, name_to_draw, font_row)

        # Обрезаем имя если не влезает
        while name_to_draw and (star_w + star_gap + name_w) > max_name_width:
            name_to_draw = name_to_draw[:-1]
            name_w, name_h = _text_size(draw, name_to_draw + "…", font_row)
        if name_to_draw != base_name_text:
            name_to_draw = name_to_draw + "…"
            name_w, name_h = _text_size(draw, name_to_draw, font_row)

        text_block_h = max(name_h, 40)
        base_ty = inner_y_center + TEXT_V_SHIFT - text_block_h // 2

        # Выравнивание имени по левому краю (после аватара)
        cur_x = name_x0

        if star_text:
            draw.text((cur_x, base_ty), star_text, font=font_emoji, fill=TEXT_COLOR)
            cur_x += star_w + star_gap

        draw.text((cur_x, base_ty), name_to_draw, font=font_row, fill=TEXT_COLOR)

    # Рисуем строки
    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)

        if i < len(rows_left):
            _draw_row(left_x, row_y, *rows_left[i])

        if i < len(rows_right):
            _draw_row(right_x, row_y, *rows_right[i])

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def create_driver_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    """Обертка для личного зачета."""

    def _driver_avatar_loader(code: str, name: str) -> Image.Image | None:
        return _get_driver_photo(code)

    def _driver_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p == 1: return (255, 180, 0)  # Золото
        if p == 2: return (192, 192, 192)  # Серебро
        if p == 3: return (205, 127, 50)  # Бронза
        return (80, 100, 140)  # Остальные (нейтральный синий)

    return create_results_image(
        title, subtitle, rows,
        avatar_loader=_driver_avatar_loader,
        card_color_func=_driver_card_color,
    )


def create_constructor_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    """Обертка для Кубка конструкторов."""

    def _team_avatar_loader(code: str, name: str) -> Image.Image | None:
        src = name or code
        return _get_team_logo(src)

    def _team_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p == 1: return (255, 180, 0)
        if p == 2: return (192, 192, 192)
        if p == 3: return (205, 127, 50)
        return (220, 40, 40) if p == 99 else (80, 100, 140)

    return create_results_image(
        title, subtitle, rows,
        avatar_loader=_team_avatar_loader,
        card_color_func=_team_card_color,
    )


def create_quali_results_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    """Обертка для квалификации."""
    has_time_by_pos = {}
    for pos, _, _, time_text in rows:
        t = (time_text or "").strip().upper()
        has_time = bool(t and t not in {"—", "NO TIME", "DNS", "DNF", "DSQ"})
        has_time_by_pos[pos] = has_time

    def _quali_avatar_loader(code: str, name: str) -> Image.Image | None:
        return _get_driver_photo(code)

    def _quali_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99

        has_time = has_time_by_pos.get(pos, False)
        if p == 1: return (255, 180, 0)
        if p == 2: return (192, 192, 192)
        if p == 3: return (205, 127, 50)

        if has_time: return (60, 200, 160)  # Бирюзовый
        return (100, 100, 120)

    return create_results_image(
        title, subtitle, rows,
        avatar_loader=_quali_avatar_loader,
        card_color_func=_quali_card_color,
    )


def create_season_image(season: int, races: list[dict]) -> BytesIO:
    """
    Рисует календарь сезона.
    Также обновлен под новый стиль (градиенты, тени).
    """
    padding = 30
    header_gap = 40
    line_spacing = 25
    row_height = 110

    # Шрифты
    title_font = FONT_TITLE
    subtitle_font = FONT_SUBTITLE
    row_font = FONT_ROW

    gap_between_cols = 50
    side_margin_inside = 20
    block_gap = 10
    block_pad_x = 16

    safe_races = races if races else []
    if not safe_races:
        safe_races = [{"round": 0, "event_name": "Нет данных", "country": "", "date": date.today().isoformat()}]

    today = date.today()
    races_with_dates = []
    for r in safe_races:
        try:
            rd = date.fromisoformat(r.get("date", today.isoformat()))
        except:
            rd = today
        races_with_dates.append((r, rd))

    # Расчет размеров
    temp_img = Image.new("RGB", (100, 100))
    draw_tmp = ImageDraw.Draw(temp_img)

    title = f"Календарь сезона {season}"
    title_w, title_h = _text_size(draw_tmp, title, title_font)

    # Считаем ширину контента
    max_round_w, max_gp_w, max_date_w = 0, 0, 0
    for r, rd in races_with_dates:
        ev = r.get("event_name", "")
        cntry = r.get("country", "")
        gp_text = f"{ev} ({cntry})" if cntry else ev

        w_rnd, _ = _text_size(draw_tmp, "00", row_font)
        max_round_w = max(max_round_w, w_rnd)

        w_gp, _ = _text_size(draw_tmp, gp_text, row_font)
        max_gp_w = max(max_gp_w, w_gp)

        w_dt, _ = _text_size(draw_tmp, "88.88.8888", row_font)
        max_date_w = max(max_date_w, w_dt)

    round_block_w = max_round_w + block_pad_x * 2
    date_block_w = max_date_w + block_pad_x * 2
    gp_block_w = max_gp_w + block_pad_x * 2

    col_width_min = side_margin_inside * 2 + round_block_w + block_gap + gp_block_w + block_gap + date_block_w

    num_rows = len(races_with_dates)
    rows_per_col = (num_rows + 1) // 2

    img_width = max(
        1800,
        2 * padding + 2 * col_width_min + gap_between_cols,
        title_w + 2 * padding
    )
    img_height = (
            padding + title_h + header_gap +
            rows_per_col * (row_height + line_spacing) + padding
    )

    # Фон и Drawer
    img = _create_vertical_gradient(img_width, img_height, BG_GRADIENT_TOP, BG_GRADIENT_BOT)
    draw = ImageDraw.Draw(img)

    # Хедер
    cur_y = padding
    x_title = (img_width - title_w) // 2
    draw.text((x_title + 2, cur_y + 2), title, font=title_font, fill=(0, 0, 0))  # тень
    draw.text((x_title, cur_y), title, font=title_font, fill=(255, 255, 255))

    cur_y += title_h + 20
    # Красная линия
    draw.line((padding, cur_y, img_width - padding, cur_y), fill=(70, 70, 90), width=2)  # подложка линии
    center_line = img_width // 2
    draw.line((center_line - 150, cur_y, center_line + 150, cur_y), fill=ACCENT_RED, width=4)  # акцент

    cur_y += header_gap // 2
    start_y = cur_y

    col_width = (img_width - 2 * padding - gap_between_cols) // 2
    left_x = padding
    right_x = padding + col_width + gap_between_cols

    races_left = races_with_dates[:rows_per_col]
    races_right = races_with_dates[rows_per_col:]

    def _draw_season_row(col_x: int, row_y: int, r: dict, rd: date) -> None:
        finished = rd < today

        # Цвета
        if finished:
            accent_color = (180, 50, 50)  # тусклый красный
            fill_color = (35, 30, 30)  # темный
            text_fill = (150, 150, 160)
        else:
            accent_color = (50, 180, 100)  # зеленый
            fill_color = (35, 45, 40)
            text_fill = (255, 255, 255)

        card_x0, card_y0 = col_x, row_y
        card_x1, card_y1 = col_x + col_width, row_y + row_height

        # Тень
        draw.rounded_rectangle(
            (card_x0 + 5, card_y0 + 5, card_x1 + 5, card_y1 + 5),
            radius=20, fill=SHADOW_COLOR
        )
        # Фон
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x1, card_y1),
            radius=20, fill=CARD_BG_COLOR, outline=(60, 60, 75), width=1
        )
        # Акцент слева
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x0 + 10, card_y1),
            radius=20, fill=accent_color
        )
        draw.rectangle((card_x0 + 6, card_y0, card_x0 + 10, card_y1), fill=accent_color)

        # Контент
        inner_y_center = (card_y0 + card_y1) // 2

        round_num = int(r.get("round", 0))
        ev = r.get("event_name", "")
        cntry = r.get("country", "")
        date_str = rd.strftime("%d.%m")

        # Номер этапа
        round_x0 = card_x0 + 25
        round_text = f"{round_num:02d}"
        draw.text((round_x0, inner_y_center + TEXT_V_SHIFT - 20), round_text, font=row_font, fill=(100, 100, 120))

        # Дата справа
        date_w, date_h = _text_size(draw, date_str, row_font)
        date_x = card_x1 - 25 - date_w

        # Плашка даты
        draw.rounded_rectangle(
            (date_x - 10, inner_y_center - 25, card_x1 - 15, inner_y_center + 25),
            radius=8, fill=fill_color
        )
        draw.text((date_x, inner_y_center + TEXT_V_SHIFT - date_h // 2), date_str, font=row_font, fill=text_fill)

        # Название Гран-при (между номером и датой)
        gp_x0 = round_x0 + 60
        gp_x1 = date_x - 20
        gp_text = f"{ev} ({cntry})" if cntry else ev

        # Обрезка текста
        max_gp_w = gp_x1 - gp_x0
        gp_draw = gp_text
        gw, gh = _text_size(draw, gp_draw, row_font)
        while gp_draw and gw > max_gp_w:
            gp_draw = gp_draw[:-1]
            gw, gh = _text_size(draw, gp_draw + "…", row_font)
        if gp_draw != gp_text: gp_draw += "…"

        draw.text((gp_x0, inner_y_center + TEXT_V_SHIFT - gh // 2), gp_draw, font=row_font, fill=text_fill)

    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)
        if i < len(races_left): _draw_season_row(left_x, row_y, *races_left[i])
        if i < len(races_right): _draw_season_row(right_x, row_y, *races_right[i])

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf