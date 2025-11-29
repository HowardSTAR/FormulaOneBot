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

# небольшой сдвиг текста вверх для визуального выравнивания по центру
TEXT_V_SHIFT = -15


# --- Загрузка шрифтов (общая для всех картинок) ---

def _load_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
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
            # самый простой запасной вариант
            font_title = font_subtitle = font_row = font_emoji = ImageFont.load_default()

    return font_title, font_subtitle, font_row, font_emoji


def _normalize_team_key(text: str) -> str:
    """
    Нормализует название/код команды:
    - lower()
    - убираем всё, кроме a-z0-9
    Чтобы 'RB F1 Team', 'Red Bull', 'redbull' и т.п. сводились к одному ключу.
    """
    import re
    s = (text or "").lower()
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


FONT_TITLE, FONT_SUBTITLE, FONT_ROW, FONT_EMOJI = _load_fonts()


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


def _get_team_logo(name_or_code: str) -> Image.Image | None:
    """
    Возвращает логотип команды по её названию или коду
    (например 'McLaren', 'RB F1 Team', 'Sauber', 'Mercedes').
    """
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
    avatar_loader: Callable[[str, str], Image.Image | None] | None = None,
    card_color_func: Callable[[str], tuple[int, int, int]] | None = None,
) -> BytesIO:
    """
    Рисует картинку с результатами в стиле табло:
    1) позиция  2) аватар (пилот или команда)  3) имя  4) очки.

    rows: список кортежей
      (position, code, name, points_text)
      пример: ("01", "⭐️NOR", "Ландо Норрис", "25")

    card_color_func: опциональная функция, которая по позиции
    возвращает цвет карточки (R, G, B). Если не задана – используется
    стандартная палитра (оранжевый/зелёный).
    """
    # --- Общие настройки ---
    padding = 15          # отступы по краям (сделал побольше)
    header_gap = 40
    line_spacing = 24
    row_height = 120      # высота одной карточки
    avatar_size = 90      # размер аватара пилота (круглый)

    bg_color = (10, 10, 25)
    text_color = (235, 235, 245)
    accent_color = (255, 255, 255)
    separator_color = (70, 70, 120)

    # --- Шрифты ---
    font_title = FONT_TITLE
    font_subtitle = FONT_SUBTITLE
    font_row = FONT_ROW
    font_emoji = FONT_EMOJI

    # если не передали свой загрузчик – используем фото пилотов
    if avatar_loader is None:
        def avatar_loader(code: str, name: str) -> Image.Image | None:  # type: ignore[no-redef]
            return _get_driver_photo(code)

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

    # ---- палитра цветов карточек ----
    def _default_card_color_for_pos(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p <= 3:
            return (255, 132, 80)   # подиум
        if p <= 10:
            return (60, 190, 170)   # очковая зона
        return (55, 70, 110)        # остальные

    color_for_pos = card_color_func or _default_card_color_for_pos

    def _draw_row(col_x: int, row_y: int,
                  pos: str, code: str, name: str, pts: str) -> None:
        # фон карточки
        card_x0 = col_x
        card_y0 = row_y
        card_x1 = col_x + col_width
        card_y1 = row_y + row_height - 6

        card_color = color_for_pos(pos)
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

        # --- аватар пилота / команды ---
        draw.rounded_rectangle(
            (avatar_x0, inner_y0, avatar_x1, inner_y1),
            radius=18,
            fill=(25, 35, 70),
        )

        raw_code = code.replace("⭐️", "").replace("⭐", "").strip().upper()
        if len(raw_code) > 3:
            raw_code = raw_code[-3:]

        base_img = avatar_loader(raw_code, name)  # type: ignore[arg-type]
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

        # --- имя (со звёздочкой для избранных) ---
        draw.rounded_rectangle(
            (name_x0, inner_y0, name_x1, inner_y1),
            radius=18,
            fill=(35, 45, 90),
        )

        raw_code_for_star = code.strip()
        raw_name_for_star = name.strip()
        has_star = ("⭐" in raw_code_for_star) or ("⭐" in raw_name_for_star)

        clean_name = (
            raw_name_for_star
            .replace("⭐️", "")
            .replace("⭐", "")
            .strip()
        )
        base_name_text = clean_name or name

        max_name_width = name_x1 - name_x0 - block_pad_x * 2

        star_text = "⭐️" if has_star else ""
        if star_text:
            star_w, star_h = _text_size(draw, star_text, font_emoji)
            star_gap = 10
        else:
            star_w, star_h = 0, 0
            star_gap = 0

        name_to_draw = base_name_text
        name_w, name_h = _text_size(draw, name_to_draw, font_row)
        while name_to_draw and (star_w + star_gap + name_w) > max_name_width:
            name_to_draw = name_to_draw[:-1]
            name_w, name_h = _text_size(draw, name_to_draw + "…", font_row)
        if name_to_draw != base_name_text:
            name_to_draw = name_to_draw + "…"
            name_w, name_h = _text_size(draw, name_to_draw, font_row)

        total_text_width = star_w + star_gap + name_w
        block_height = inner_y1 - inner_y0
        text_block_h = max(name_h, star_h)
        base_ty = inner_y0 + (block_height - text_block_h) // 2 + TEXT_V_SHIFT

        start_tx = name_x0 + (name_x1 - name_x0 - total_text_width) // 2

        cur_x = start_tx
        if star_text:
            draw.text((cur_x, base_ty), star_text, font=font_emoji, fill=text_color)
            cur_x += star_w + star_gap

        draw.text((cur_x, base_ty), name_to_draw, font=font_row, fill=text_color)

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


def create_driver_standings_image(title: str, subtitle: str, rows: List[Tuple[str, str, str, str]]) -> BytesIO:
    """Картинка для личного зачёта пилотов."""
    def _driver_avatar_loader(code: str, name: str) -> Image.Image | None:
        return _get_driver_photo(code)

    # СВОЯ палитра для личного зачёта:
    # top-3 — «золото», очковая зона — голубой, остальные — тёмные.
    def _driver_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99
        if p == 1:
            return (250, 200, 80)     # золото
        if p == 2:
            return (210, 215, 225)    # серебро
        if p == 3:
            return (205, 140, 80)     # бронза

        # все остальные места
        return (55, 70, 110)

    return create_results_image(
        title,
        subtitle,
        rows,
        avatar_loader=_driver_avatar_loader,
        card_color_func=_driver_card_color,
    )


def create_constructor_standings_image(
    title: str,
    subtitle: str,
    rows: List[Tuple[str, str, str, str]]
) -> BytesIO:
    """Рисует картинку для Кубка конструкторов.

    rows: (position, constructor_code, constructor_name, points_text)
    Например: ("01", "MCL", "McLaren", "756").
    Для аватара используется именно имя команды, а не код.
    """

    def _team_avatar_loader(code: str, name: str) -> Image.Image | None:
        # для логотипа лучше всего подходит полное название
        src = name or code
        return _get_team_logo(src)

    # Палитра как в личном зачёте:
    # 1 — золото, 2 — серебро, 3 — бронза, остальные — тёмный.
    def _team_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99

        if p == 1:
            return (250, 200, 80)     # золото
        if p == 2:
            return (210, 215, 225)    # серебро
        if p == 3:
            return (205, 140, 80)     # бронза

        # остальные места
        return (55, 70, 110)

    return create_results_image(
        title,
        subtitle,
        rows,
        avatar_loader=_team_avatar_loader,
        card_color_func=_team_card_color,
    )


# --- Квалификация: картинка результатов квалификации ---

def create_quali_results_image(
    title: str,
    subtitle: str,
    rows: List[Tuple[str, str, str, str]],
) -> BytesIO:
    """Рисует картинку с результатами квалификации.

    rows: (position, driver_code, driver_name, best_time_text)
      position       — строка вида "01", "02", ...
      driver_code    — код пилота (VER, LEC, ...), может включать ⭐️
      driver_name    — отображаемое имя пилота
      best_time_text — лучший круг (например "1:32.123") или "—".

    Цвета:
      * P1 — золото
      * P2 — серебро
      * P3 — бронза
      * остальные с зафиксированным временем — бирюзовый
      * остальные без времени — тёмный.
    """

    # мапа: позиция -> есть ли у пилота зафиксированное время
    has_time_by_pos: dict[str, bool] = {}
    for pos, _code, _name, time_text in rows:
        t = (time_text or "").strip().upper()
        # считаем, что времени нет, если строка пустая или служебные статусы
        has_time = bool(t and t not in {"—", "NO TIME", "DNS", "DNF", "DSQ"})
        has_time_by_pos[pos] = has_time

    def _quali_avatar_loader(code: str, name: str) -> Image.Image | None:
        # для квалификации используем фото пилотов
        return _get_driver_photo(code)

    def _quali_card_color(pos: str) -> tuple[int, int, int]:
        try:
            p = int(pos)
        except ValueError:
            p = 99

        has_time = has_time_by_pos.get(pos, False)

        # подиум
        if p == 1:
            base = (250, 200, 80)     # золото
        elif p == 2:
            base = (210, 215, 225)    # серебро
        elif p == 3:
            base = (205, 140, 80)     # бронза
        else:
            if has_time:
                # есть зафиксированное время — подсветим бирюзовым
                base = (60, 190, 170)
            else:
                # без времени — более тёмный
                base = (45, 55, 85)

        return base

    return create_results_image(
        title,
        subtitle,
        rows,
        avatar_loader=_quali_avatar_loader,
        card_color_func=_quali_card_color,
    )


def create_season_image(season: int, races: list[dict]) -> BytesIO:
    """
    Рисует картинку с календарём сезона в том же стиле, что и результаты гонки:
    тёмный фон, карточки, две колонки.

    races — то, что возвращает get_season_schedule_short(season), ожидаются поля:
      - "round" (int)
      - "event_name" (str)
      - "country" (str)
      - "date" (YYYY-MM-DD)
    """
    # --- Базовые настройки оформления ---
    padding = 20
    header_gap = 32
    line_spacing = 20
    row_height = 110

    bg_color = (10, 10, 25)
    text_color = (235, 235, 245)
    accent_color = (255, 255, 255)
    separator_color = (70, 70, 120)

    title_font = FONT_TITLE
    subtitle_font = FONT_SUBTITLE
    row_font = FONT_ROW

    # отступы внутри "строки"
    gap_between_cols = 40              # расстояние между колонками
    block_pad_x = 16                   # горизонтальный паддинг текста в блоках
    block_gap = 8                      # расстояние между блоками внутри строки
    side_margin_inside = 24            # отступ слева/справа внутри карточки

    # Без гонок — отдаём заглушку
    safe_races = races if races else []
    if not safe_races:
        safe_races = [{
            "round": 0,
            "event_name": "Нет данных по календарю",
            "country": "",
            "date": date.today().isoformat(),
        }]

    # Определяем текущую дату (нужна только для цвета карточек)
    today = date.today()

    # Собираем список (race_dict, race_date)
    races_with_dates: list[tuple[dict, date]] = []
    for r in safe_races:
        try:
            rd = date.fromisoformat(r.get("date", today.isoformat()))
        except Exception:
            rd = today
        races_with_dates.append((r, rd))

    # Вспомогательное изображение для расчёта размеров текста
    temp_img = Image.new("RGB", (2400, 2400))
    draw_tmp = ImageDraw.Draw(temp_img)

    title = f"Календарь сезона {season}"
    subtitle = ""  # статус текстом не показываем

    title_w, title_h = _text_size(draw_tmp, title, title_font)
    subtitle_w, subtitle_h = (0, 0)
    if subtitle:
        subtitle_w, subtitle_h = _text_size(draw_tmp, subtitle, subtitle_font)

    # Для общей оценки ширины текста (не критично, но оставим)
    max_text = ""
    for r, rd in races_with_dates:
        rnd = r.get("round", 0)
        ev = r.get("event_name", "")
        country = r.get("country", "")
        date_str = rd.strftime("%d.%m.%Y")
        candidate = f"{rnd:02d} {ev} ({country}) {date_str}"
        if len(candidate) > len(max_text):
            max_text = candidate
    row_text_w, _ = _text_size(draw_tmp, max_text, row_font)

    # --- ВАЖНОЕ: считаем, какой минимум нужен по ширине колонки,
    #             чтобы ВЛЕЗАЛО полное название этапа + номер + дата ---

    max_round_w = 0
    max_gp_w = 0
    max_date_w = 0

    for r, rd in races_with_dates:
        round_num = int(r.get("round", 0))
        ev = r.get("event_name", "")
        country = r.get("country", "")
        date_str = rd.strftime("%d.%m.%Y")

        round_text = f"{round_num:02d}"
        gp_text = f"{ev} ({country})" if country else ev
        date_text = date_str

        w, _ = _text_size(draw_tmp, round_text, row_font)
        max_round_w = max(max_round_w, w)

        w, _ = _text_size(draw_tmp, gp_text, row_font)
        max_gp_w = max(max_gp_w, w)

        w, _ = _text_size(draw_tmp, date_text, row_font)
        max_date_w = max(max_date_w, w)

    # ширины блоков по максимумам
    round_block_w = max(80, max_round_w + block_pad_x * 2)
    date_block_w = max(220, max_date_w + block_pad_x * 2)
    gp_block_w = max_gp_w + block_pad_x * 2

    # минимальная ширина одной колонки, чтобы всё поместилось
    col_width_min = (
        side_margin_inside
        + round_block_w
        + block_gap
        + gp_block_w
        + block_gap
        + date_block_w
        + side_margin_inside
    )

    # --- Размеры картинки ---
    num_rows = len(races_with_dates)
    rows_per_col = (num_rows + 1) // 2

    # min_width теперь учитывает требуемую ширину двух колонок
    min_width_from_cols = 2 * padding + 2 * col_width_min + gap_between_cols
    min_width_basic = 1800  # запас по минимальной ширине

    img_width = max(
        min_width_basic,
        min_width_from_cols,
        title_w + 2 * padding,
        subtitle_w + 2 * padding,
        row_text_w + 2 * padding,
    )

    img_height = (
        padding
        + title_h
        + header_gap
        + (subtitle_h if subtitle else 0)
        + (header_gap if subtitle else 0)
        + rows_per_col * (row_height + line_spacing)
        + padding
    )

    img = Image.new("RGB", (img_width, img_height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # --- Заголовок ---
    cur_y = padding
    x_title = (img_width - title_w) // 2
    draw.text((x_title, cur_y), title, font=title_font, fill=accent_color)

    cur_y += title_h + header_gap
    if subtitle:
        x_subtitle = (img_width - subtitle_w) // 2
        draw.text((x_subtitle, cur_y), subtitle, font=subtitle_font, fill=text_color)
        cur_y += subtitle_h + header_gap

    # Линия под заголовком
    draw.line(
        (padding, cur_y, img_width - padding, cur_y),
        fill=separator_color,
        width=2,
    )
    cur_y += header_gap // 2

    start_y = cur_y

    # Параметры колонок в уже рассчитанной ширине
    col_width = (img_width - 2 * padding - gap_between_cols) // 2
    left_x = padding
    right_x = padding + col_width + gap_between_cols

    # Делим гонки на две колонки
    races_left = races_with_dates[:rows_per_col]
    races_right = races_with_dates[rows_per_col:]

    def _card_colors(is_finished: bool) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """
        Возвращает (основной цвет карточки, внутренний цвет) в зависимости
        от статуса гонки. Статус цветом остаётся, но иконок больше нет.
        """
        if is_finished:
            base = (190, 60, 62)      # прошедшие гонки — красноватый
        else:
            base = (60, 190, 120)     # будущие гонки — зелёный

        inner = (
            int(base[0] * 0.8),
            int(base[1] * 0.8),
            int(base[2] * 0.9),
        )
        return base, inner

    def _draw_season_row(col_x: int, row_y: int, r: dict, rd: date) -> None:
        round_num = int(r.get("round", 0))
        ev = r.get("event_name", "")
        country = r.get("country", "")

        finished = rd < today
        date_str = rd.strftime("%d.%m")

        # Координаты карточки
        card_x0 = col_x
        card_y0 = row_y
        card_x1 = col_x + col_width
        card_y1 = row_y + row_height - 6

        base_color, inner_color = _card_colors(finished)

        # Основная карточка
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x1, card_y1),
            radius=24,
            fill=inner_color,
        )

        # Цветная полоса слева
        draw.rounded_rectangle(
            (card_x0, card_y0, card_x0 + 16, card_y1),
            radius=24,
            fill=base_color,
        )

        inner_y0 = card_y0 + 10
        inner_y1 = card_y1 - 10
        block_height = inner_y1 - inner_y0

        # Текст для блоков
        round_text = f"{round_num:02d}"
        gp_text = f"{ev} ({country})" if country else ev
        date_block_text = date_str

        # Правая часть: дата
        date_x1 = card_x1 - side_margin_inside
        date_x0 = date_x1 - date_block_w

        # Слева номер этапа
        round_x0 = card_x0 + side_margin_inside
        round_x1 = round_x0 + round_block_w

        # Всё, что остаётся между номером и датой — под название Гран-при
        gp_x0 = round_x1 + block_gap
        gp_x1 = date_x0 - block_gap

        # --- Цвет блока в зависимости от статуса ---
        if finished:
            block_fill = (36, 10, 1)   # гонка прошла
        else:
            block_fill = (1, 36, 3)    # гонка ещё не прошла

        # --- Блок номера этапа ---
        draw.rounded_rectangle(
            (round_x0, inner_y0, round_x1, inner_y1),
            radius=18,
            fill=block_fill,
        )
        round_w, round_h = _text_size(draw, round_text, row_font)
        round_tx = round_x0 + (round_block_w - round_w) // 2
        round_ty = inner_y0 + (block_height - round_h) // 2 + TEXT_V_SHIFT
        draw.text((round_tx, round_ty), round_text, font=row_font, fill=text_color)

        # --- Блок даты ---
        draw.rounded_rectangle(
            (date_x0, inner_y0, date_x1, inner_y1),
            radius=18,
            fill=block_fill,
        )
        date_w, date_h = _text_size(draw, date_block_text, row_font)
        date_tx = date_x0 + (date_block_w - date_w) // 2
        date_ty = inner_y0 + (block_height - date_h) // 2 + TEXT_V_SHIFT
        draw.text((date_tx, date_ty), date_block_text, font=row_font, fill=text_color)

        # --- Блок названия Гран-при ---
        draw.rounded_rectangle(
            (gp_x0, inner_y0, gp_x1, inner_y1),
            radius=18,
            fill=block_fill,
        )

        # Здесь уже не должно быть обрезания, но оставим на всякий случай
        max_gp_width = gp_x1 - gp_x0 - block_pad_x * 2
        gp_text_to_draw = gp_text
        gp_w_cur, gp_h_cur = _text_size(draw, gp_text_to_draw, row_font)
        while gp_text_to_draw and gp_w_cur > max_gp_width:
            gp_text_to_draw = gp_text_to_draw[:-1]
            gp_w_cur, gp_h_cur = _text_size(draw, gp_text_to_draw + "…", row_font)
        if gp_text_to_draw != gp_text:
            gp_text_to_draw = gp_text_to_draw + "…"
            gp_w_cur, gp_h_cur = _text_size(draw, gp_text_to_draw, row_font)

        gp_tx = gp_x0 + (gp_x1 - gp_x0 - gp_w_cur) // 2
        gp_ty = inner_y0 + (block_height - gp_h_cur) // 2 + TEXT_V_SHIFT
        draw.text((gp_tx, gp_ty), gp_text_to_draw, font=row_font, fill=text_color)

    # Рисуем все строки в две колонки
    for i in range(rows_per_col):
        row_y = start_y + i * (row_height + line_spacing)

        if i < len(races_left):
            r, rd = races_left[i]
            _draw_season_row(left_x, row_y, r, rd)

        if i < len(races_right):
            r, rd = races_right[i]
            _draw_season_row(right_x, row_y, r, rd)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf