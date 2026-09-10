"""Shared reminder categories. Persisted bits must never be renumbered."""

SESSION_OPTIONS = (
    (1, "Свободные заезды (FP1, FP2, FP3)"),
    (2, "Квалификация"),
    (4, "Гонка"),
    (8, "Спринт-квалификация"),
    (16, "Спринт"),
)
ALL_SESSIONS = 31
SESSION_BITS = {"practice1": 1, "practice2": 1, "practice3": 1,
                "quali": 2, "race": 4, "sprint_quali": 8, "sprint": 16}


def session_enabled(mask: int | None, kind: str) -> bool:
    return bool((ALL_SESSIONS if mask is None else int(mask)) & SESSION_BITS.get(kind, 0))
