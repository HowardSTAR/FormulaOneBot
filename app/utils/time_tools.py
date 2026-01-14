# utils/time_tools.py
from datetime import datetime
import pytz

# Словарь для перевода месяцев (чтобы не зависеть от локали системы)
RU_MONTHS = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
    7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}

def format_race_time(utc_time_str: str, user_timezone_str: str = "Europe/Moscow") -> str:
    """
    Принимает строку времени UTC (ISO) и возвращает красивую строку
    в часовом поясе юзера на русском языке.
    Пример входа: "2024-03-02T15:00:00Z"
    Пример выхода: "02 марта, 18:00"
    """
    if not utc_time_str:
        return "Время не определено"

    # 1. Парсим время (ISO формат)
    try:
        # replace("Z", "+00:00") нужен, если API отдает Z на конце
        utc_dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
    except ValueError:
        return utc_time_str  # Если формат кривой, возвращаем как есть

    # 2. Получаем таймзону юзера
    try:
        user_tz = pytz.timezone(user_timezone_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone("Europe/Moscow") # Fallback, если в базе мусор

    # 3. Конвертируем
    local_dt = utc_dt.astimezone(user_tz)

    # 4. Форматируем
    day = local_dt.day
    month_name = RU_MONTHS.get(local_dt.month, "")
    time_str = local_dt.strftime("%H:%M")

    return f"{day} {month_name}, {time_str}"