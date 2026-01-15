from datetime import datetime
import pytz

RU_MONTHS = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
    7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}

def format_race_time(utc_time_str: str, user_timezone_str: str = "Europe/Moscow") -> str:
    """
    Принимает UTC строку.
    Возвращает: "08 марта 18:00 (UTC+3)" (без запятой)
    """
    if not utc_time_str:
        return "Время не определено"

    try:
        utc_dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    except ValueError:
        return utc_time_str

    try:
        user_tz = pytz.timezone(user_timezone_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone("Europe/Moscow")

    local_dt = utc_dt.astimezone(user_tz)

    day = local_dt.day
    month_name = RU_MONTHS.get(local_dt.month, "")
    time_str = local_dt.strftime("%H:%M")

    # Считаем оффсет (UTC+3)
    offset_hours = local_dt.utcoffset().total_seconds() / 3600
    if offset_hours == 0:
        offset_str = "UTC"
    elif offset_hours > 0:
        offset_str = f"UTC+{offset_hours:g}"
    else:
        offset_str = f"UTC{offset_hours:g}"

    # Было: f"{day} {month_name}, {time_str} ({offset_str})"
    # Стало (без запятой):
    return f"{day} {month_name} {time_str} ({offset_str})"