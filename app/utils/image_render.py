from io import BytesIO
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


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
    rows: List[Tuple[str, str, str]],
) -> BytesIO:
    """
    Генерирует PNG-картинку с результатами в виде тёмной карточки.

    :param title: Заголовок (например: 'Результаты гонки')
    :param subtitle: Подзаголовок ('Гран-при Лас-Вегаса, этап 22, сезон 2025')
    :param rows: список строк в формате (позиция, пилот/код, доп.инфо)
                 например: ('01', '⭐️ VER', 'Red Bull (25 очк.)')
                 Звёздочка в начале кода будет отрисована emoji-шрифтом.
    :return: BytesIO с готовым PNG
    """
    # --- Общие настройки ---
    padding = 60
    header_gap = 30
    line_spacing = 14
    row_height = 34

    bg_color = (10, 10, 25)
    text_color = (235, 235, 245)
    accent_color = (255, 215, 0)  # золото для заголовка
    separator_color = (70, 70, 120)

    # --- Загрузка шрифтов ---
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"

    try:
        font_title = ImageFont.truetype(str(fonts_dir / "Jost-Bold.ttf"), 44)
        font_subtitle = ImageFont.truetype(str(fonts_dir / "Jost-Regular.ttf"), 28)
        font_row = ImageFont.truetype(str(fonts_dir / "Jost-SemiBoldItalic.ttf"), 26)

        # отдельный шрифт для emoji (⭐️ и т.п.)
        try:
            font_emoji = ImageFont.truetype(
                str(fonts_dir / "NotoEmoji-Regular.ttf"), 30
            )
        except Exception:
            # если не получилось, рисуем emoji тем же шрифтом, что и текст
            font_emoji = font_row
    except Exception:
        # fallback — пробуем системные Jost, а если нет — дефолтный шрифт
        try:
            font_title = ImageFont.truetype("Jost-Bold.ttf", 44)
            font_subtitle = ImageFont.truetype("Jost-Regular.ttf", 28)
            font_row = ImageFont.truetype("Jost-SemiBoldItalic.ttf", 26)
            font_emoji = font_row
        except Exception:
            font_title = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()
            font_row = ImageFont.load_default()
            font_emoji = font_row

    # хотя бы одна строка, чтобы не падать на пустом списке
    safe_rows = rows if rows else [("—", "", "Нет данных")]

    # временное изображение для расчётов
    temp_img = Image.new("RGB", (2000, 2000))
    draw_tmp = ImageDraw.Draw(temp_img)

    title_w, title_h = _text_size(draw_tmp, title, font_title)
    subtitle_w, subtitle_h = _text_size(draw_tmp, subtitle, font_subtitle)

    # --- Верстаем в два столбца ---
    num_rows = len(safe_rows)
    rows_per_col = (num_rows + 1) // 2  # делим пополам, левая колонка получает +1 при нечётном

    # Примерная ширина строки — берём самую длинную по длине текста
    max_row_text = ""
    for pos, code, extra in safe_rows:
        candidate = f"{pos}. {code} {extra}"
        if len(candidate) > len(max_row_text):
            max_row_text = candidate

    row_text_w, row_text_h = _text_size(draw_tmp, max_row_text, font_row)

    # Базовая ширина и высота
    # Две колонки + отступ между ними
    min_width = 1100
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

    # разделительная линия
    cur_y += subtitle_h + header_gap
    draw.line(
        (padding, cur_y, img_width - padding, cur_y),
        fill=separator_color,
        width=2,
    )
    cur_y += header_gap // 2

    start_y = cur_y

    # координаты колонок
    left_x = padding
    right_x = img_width // 2 + 30

    rows_left = safe_rows[:rows_per_col]
    rows_right = safe_rows[rows_per_col:]

    def _draw_row(col_x: int, row_y: int, pos: str, code: str, extra: str) -> None:
        """
        Рисует одну строку: позиция, (возможно) звезда, код и доп.инфо.
        """
        x = col_x

        # 1. позиция
        pos_text = f"{pos}."
        if pos_text.strip() != ".":
            draw.text((x, row_y), pos_text, font=font_row, fill=text_color)
            pos_w, _ = _text_size(draw, pos_text, font_row)
            x += pos_w + 8

        # 2. звёздочка-emoji, если есть
        star = ""
        rest_code = code
        if code.startswith("⭐") or code.startswith("⭐️"):
            star = "⭐️"
            rest_code = code.replace("⭐️", "", 1).replace("⭐", "", 1).lstrip()

        if star:
            draw.text((x, row_y), star, font=font_emoji, fill=text_color)
            star_w, _ = _text_size(draw, star, font_emoji)
            x += star_w + 6

        # 3. код пилота + доп. текст
        main_text = rest_code
        if extra:
            if main_text:
                main_text += f" {extra}"
            else:
                main_text = extra

        if main_text:
            draw.text((x, row_y), main_text, font=font_row, fill=text_color)

    # --- Рисуем все строки в две колонки ---
    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)

        if i < len(rows_left):
            pos, code, extra = rows_left[i]
            _draw_row(left_x, row_y, pos, code, extra)

        if i < len(rows_right):
            pos, code, extra = rows_right[i]
            _draw_row(right_x, row_y, pos, code, extra)

    # Сохраняем картинку в память
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf