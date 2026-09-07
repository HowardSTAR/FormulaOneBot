"""One calendar deadline for the Mini App and result notifications."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

VOTING_TIMEZONE = ZoneInfo("Europe/Moscow")


def voting_closes_at(event: dict) -> datetime | None:
    # A Sunday round closes at the start of Wednesday in the app's Moscow calendar.
    try:
        if event.get("date"):
            race_date = datetime.fromisoformat(str(event["date"])).date()
        else:
            started = datetime.fromisoformat(str(event["race_start_utc"]).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            race_date = started.astimezone(VOTING_TIMEZONE).date()
        return datetime.combine(race_date + timedelta(days=3), time.min, VOTING_TIMEZONE).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None

