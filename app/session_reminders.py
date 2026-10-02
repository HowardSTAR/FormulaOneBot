"""Shared reminder categories. Persisted bits must never be renumbered."""

SESSION_OPTIONS = (
    (1, "Свободные заезды (FP1, FP2, FP3)"),
    (2, "Квалификация"),
    (4, "Гонка"),
    (8, "Спринт-квалификация"),
    (16, "Спринт"),
)
ALL_SESSIONS = 31
REMINDER_INTERVALS = (15, 30, 60, 120, 1440)
INTERVAL_BITS = {minutes: 1 << index for index, minutes in enumerate(REMINDER_INTERVALS)}
SESSION_BITS = {"practice1": 1, "practice2": 1, "practice3": 1,
                "quali": 2, "race": 4, "sprint_quali": 8, "sprint": 16}


def session_enabled(mask: int | None, kind: str) -> bool:
    return bool((ALL_SESSIONS if mask is None else int(mask)) & SESSION_BITS.get(kind, 0))


def reminder_intervals(mask: int | None, legacy_minutes: int | None = 60) -> list[int]:
    """NULL preserves the previous single interval; zero explicitly disables reminders."""
    if mask is None:
        return [int(legacy_minutes or 60)]
    return [minutes for minutes, bit in INTERVAL_BITS.items() if int(mask) & bit]


def interval_mask(minutes: list[int]) -> int:
    if not isinstance(minutes, list) or any(type(value) is not int or value not in INTERVAL_BITS for value in minutes):
        raise ValueError("Выберите интервалы: 15, 30, 60, 120 или 1440 минут")
    return sum(INTERVAL_BITS[value] for value in set(minutes))


def reminder_enabled(mask: int | None, legacy_minutes: int | None, event_key: str) -> bool:
    """Recheck a queued reminder against the recipient's current lead-time selection."""
    parts = event_key.split(":")
    return len(parts) >= 5 and parts[4] in {str(value) for value in reminder_intervals(mask, legacy_minutes)}
