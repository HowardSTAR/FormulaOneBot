from io import BytesIO
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

# Соответствие кода пилота имени файла с его фотографией
# Файлы лежат в app/assets/pilots
DRIVER_CODE_TO_FILE = {
    "ALB": "Alexander Albon.png",
    "ANT": "Andrea Kimi Antonelli.png",
    "SAI": "Carlos Sainz.png",
    "LEC": "Charles Leclerc.png",
    "OCO": "Esteban Ocon.png",
    "ALO": "Fernando Alonso.png",
    "COL": "Franco Colapinto.png",
    "BOR": "Gabriel Bortoleto.png",
    "RUS": "George Russell.png",
    "HAD": "Isack Hadjar.png",
    "DOO": "Jack Doohan.png",
    "STR": "Lance Stroll.png",
    "NOR": "Lando Norris.png",
    "HAM": "Lewis Hamilton.png",
    "LAW": "Liam Lawson.png",
    "VER": "Max Verstappen.png",
    "HUL": "Nico Hülkenberg.png",
    "BEA": "Oliver Bearman.png",
    "PIA": "Oscar Piastri.png",
    "GAS": "Pierre Gasly.png",
    "TSU": "Yuki Tsunoda.png",
}

# Кеш загруженных фотографий пилотов
_DRIVER_PHOTOS_CACHE: dict[str, Image.Image] = {}


def _get_driver_photo(code: str) -> Image.Image | None:
    """
    Возвращает PIL‑картинку по коду пилота (VER, LEC и т.д.) или None,
    если фото не найдено. Картинки кешируются в _DRIVER_PHOTOS_CACHE.
    """
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


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    """
    Аккуратно считаем размеры текста, учитывая разные версии Pillow.
    """
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    else:
        w, h = draw.textsize(text, font=font)
    return w, h


def create_results_image(
    title: str,
    subtitle: str,
    rows: List[Tuple[str, str, str, str]],
) -> BytesIO:
    """
    Рисует картинку с результатами в стиле табло:
    1) позиция  2) фото пилота  3) имя  4) очки за гонку.

    rows: список кортежей
      (position, driver_code, driver_name, points_text)
      пример: ("01", "⭐️NOR", "Ландо Норрис", "25 очк.")
    """
    # --- Общие настройки ---
    padding = 15          # отступы по краям (сделал побольше)
    header_gap = 40
    line_spacing = 24
    row_height = 120      # высота одной карточки
    avatar_size = 90      # размер аватара пилота (круглый)
    avatar_gap = 20
    TEXT_V_SHIFT = -15  # небольшой сдвиг текста вверх для визуального выравнивания по центру

    bg_color = (10, 10, 25)
    text_color = (235, 235, 245)
    accent_color = (255, 215, 0)
    separator_color = (70, 70, 120)

    # --- Загрузка шрифтов ---
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"

    try:
        font_title = ImageFont.truetype(str(fonts_dir / "Jost-Bold.ttf"), 60)
        font_subtitle = ImageFont.truetype(str(fonts_dir / "Jost-Regular.ttf"), 34)
        font_row = ImageFont.truetype(str(fonts_dir / "Jost-Medium.ttf"), 44)
        try:
            font_emoji = ImageFont.truetype(
                str(fonts_dir / "NotoEmoji-Regular.ttf"), 40
            )
        except Exception:
            font_emoji = font_row
    except Exception:
        try:
            font_title = ImageFont.truetype("Jost-Bold.ttf", 60)
            font_subtitle = ImageFont.truetype("Jost-Regular.ttf", 34)
            font_row = ImageFont.truetype("Jost-Medium.ttf", 44)
            font_emoji = font_row
        except Exception:
            font_title = font_subtitle = font_row = ImageFont.load_default()

    # хотя бы одна строка, чтобы не упасть
    safe_rows: List[Tuple[str, str, str, str]]
    if rows:
        safe_rows = rows
    else:
        safe_rows = [("—", "", "Нет данных", "")]

    # временное изображение для расчётов
    temp_img = Image.new("RGB", (2400, 2400))
    draw_tmp = ImageDraw.Draw(temp_img)

    title_w, title_h = _text_size(draw_tmp, title, font_title)
    subtitle_w, subtitle_h = _text_size(draw_tmp, subtitle, font_subtitle)

    # две колонки
    num_rows = len(safe_rows)
    rows_per_col = (num_rows + 1) // 2

    # самая широкая строка по имени + очкам
    max_row_text = ""
    for pos, code, name, pts in safe_rows:
        candidate = f"{pos}. {name} {pts}"
        if len(candidate) > len(max_row_text):
            max_row_text = candidate
    row_text_w, _ = _text_size(draw_tmp, max_row_text, font_row)

    # ширина / высота
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

    img = Image.new("RGB", (img_width, img_height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # --- Заголовок ---
    cur_y = padding
    x_title = (img_width - title_w) // 2
    draw.text((x_title, cur_y), title, font=font_title, fill=accent_color)

    cur_y += title_h + header_gap
    x_sub = (img_width - subtitle_w) // 2
    draw.text((x_sub, cur_y), subtitle, font=font_subtitle, fill=text_color)

    # линия под заголовком
    cur_y += subtitle_h + header_gap
    draw.line(
        (padding, cur_y, img_width - padding, cur_y),
        fill=separator_color,
        width=2,
    )
    cur_y += header_gap // 2

    start_y = cur_y

    # параметры колонок
    gap_between_cols = 40
    col_width = (img_width - 2 * padding - gap_between_cols) // 2
    left_x = padding
    right_x = padding + col_width + gap_between_cols

    rows_left = safe_rows[:rows_per_col]
    rows_right = safe_rows[rows_per_col:]

    def _card_color_for_pos(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p <= 3:
            return (255, 132, 80)   # подиум
        if p <= 10:
            return (60, 190, 170)   # очковая зона
        return (55, 70, 110)        # остальные

    def _draw_row(col_x: int, row_y: int,
                  pos: str, code: str, name: str, pts: str) -> None:
        # фон карточки
        card_x0 = col_x
        card_y0 = row_y
        card_x1 = col_x + col_width
        card_y1 = row_y + row_height - 6

        card_color = _card_color_for_pos(pos)
        inner_color = (
            int(card_color[0] * 0.8),
            int(card_color[1] * 0.8),
            int(card_color[2] * 0.9),
        )

        # основной фон карточки
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x1, card_y1),
            radius=24,
            fill=inner_color,
        )
        # цветная полоска слева
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x0 + 16, card_y1),
            radius=24,
            fill=card_color,
        )

        # внутренняя область для "подкарточек"
        inner_y0 = card_y0 + 10
        inner_y1 = card_y1 - 10
        inner_y_center = (inner_y0 + inner_y1) // 2

        # разобьём карточку на 4 зоны: позиция, аватар, имя, очки
        block_gap = 8
        block_pad_x = 16

        # текст очков
        pts_text = pts
        pts_w, pts_h = _text_size(draw, pts_text, font_row)
        pts_block_w = pts_w + block_pad_x * 2

        # текст позиции
        pos_text = pos
        pos_w, pos_h = _text_size(draw, pos_text, font_row)
        pos_block_w = max(80, pos_w + block_pad_x * 2)

        # для аватара блок фиксированной ширины
        avatar_block_w = avatar_size + block_pad_x * 2

        # правая граница блока с очками
        pts_x1 = card_x1 - 24
        pts_x0 = pts_x1 - pts_block_w

        # слева направо: позиция -> аватар -> имя -> очки
        pos_x0 = card_x0 + 24
        pos_x1 = pos_x0 + pos_block_w

        avatar_x0 = pos_x1 + block_gap
        avatar_x1 = avatar_x0 + avatar_block_w

        name_x0 = avatar_x1 + block_gap
        name_x1 = pts_x0 - block_gap

        # если вдруг не хватает места (на всякий случай)
        if name_x1 <= name_x0:
            name_x0 = avatar_x1 + block_gap
            name_x1 = avatar_x1 + max(120, row_height)

        # --- аватар пилота ---
        draw.rounded_rectangle(
            (avatar_x0, inner_y0, avatar_x1, inner_y1),
            radius=18,
            fill=(25, 35, 70),
        )

        raw_code = code.replace("⭐️", "").replace("⭐", "").strip().upper()
        if len(raw_code) > 3:
            raw_code = raw_code[-3:]

        base_img = _get_driver_photo(raw_code)
        if base_img is not None:
            avatar = base_img.resize((avatar_size, avatar_size), Image.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

            avatar_x_center = (avatar_x0 + avatar_x1) // 2
            avatar_y_center = inner_y_center

            avatar_x = avatar_x_center - avatar_size // 2
            avatar_y = avatar_y_center - avatar_size // 2

            img.paste(avatar, (avatar_x, avatar_y), mask)

        # --- позиция ---
        draw.rounded_rectangle(
            (pos_x0, inner_y0, pos_x1, inner_y1),
            radius=18,
            fill=(30, 40, 80),
        )
        pos_tx = pos_x0 + (pos_block_w - pos_w) // 2
        pos_ty = inner_y_center + TEXT_V_SHIFT - pos_h // 2
        draw.text((pos_tx, pos_ty), pos_text, font=font_row, fill=text_color)

        # --- очки ---
        draw.rounded_rectangle(
            (pts_x0, inner_y0, pts_x1, inner_y1),
            radius=18,
            fill=(25, 45, 90),
        )
        pts_tx = pts_x0 + (pts_block_w - pts_w) // 2
        pts_ty = inner_y_center + TEXT_V_SHIFT - pts_h // 2
        draw.text((pts_tx, pts_ty), pts_text, font=font_row, fill=text_color)

        # --- имя пилота ---
        draw.rounded_rectangle(
            (name_x0, inner_y0, name_x1, inner_y1),
            radius=18,
            fill=(35, 45, 90),
        )

        has_star = code.startswith("⭐") or code.startswith("⭐️")
        name_text = f"⭐️ {name}" if has_star else name

        name_w, name_h = _text_size(draw, name_text, font_row)
        max_name_width = name_x1 - name_x0 - block_pad_x * 2

        if name_w > max_name_width and max_name_width > 0:
            base_name = name_text
            while base_name and name_w > max_name_width:
                base_name = base_name[:-1]
                name_w, name_h = _text_size(draw, base_name + "…", font_row)
            name_text = base_name + "…"

        name_w, name_h = _text_size(draw, name_text, font_row)
        name_tx = name_x0 + (name_x1 - name_x0 - name_w) // 2
        name_ty = inner_y_center + TEXT_V_SHIFT - name_h // 2
        draw.text((name_tx, name_ty), name_text, font=font_row, fill=text_color)

    # --- рисуем все строки ---
    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)

        if i < len(rows_left):
            pos, code, name, pts = rows_left[i]
            _draw_row(left_x, row_y, pos, code, name, pts)

        if i < len(rows_right):
            pos, code, name, pts = rows_right[i]
            _draw_row(right_x, row_y, pos, code, name, pts)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf