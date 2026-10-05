"""Estimated schedule windows when the source publishes only a start time."""

SESSION_MINUTES = {
    'practice1': 60, 'practice2': 60, 'practice3': 60,
    'quali': 90, 'sprint_quali': 60, 'sprint': 60, 'race': 180,
}


def calendar_session_minutes(name: str) -> int:
    label = name.lower()
    if 'sprint' in label or 'спринт' in label:
        return SESSION_MINUTES['sprint']
    if 'qualifying' in label or 'квалификац' in label:
        return SESSION_MINUTES['quali']
    if 'race' in label or 'гонка' in label:
        return SESSION_MINUTES['race']
    return SESSION_MINUTES['practice1']
