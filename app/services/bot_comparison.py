"""Two-participant comparisons from the same published standings as the tables."""
import asyncio
import math
from datetime import datetime, timezone


def participant_points(frame, identifier, kind):
    if frame is None or frame.empty or "points" not in frame:
        return None
    columns = ("driverId", "driverCode") if kind == "drivers" else ("constructorId", "constructorName")
    if not any(column in frame for column in columns):
        return None
    for column in columns:
        if column in frame:
            selected = frame[frame[column].astype(str) == identifier]
            if len(selected) > 1:
                return None
            if len(selected) == 1:
                try:
                    value = float(selected.iloc[0]["points"])
                    return value if math.isfinite(value) else None
                except (TypeError, ValueError):
                    return None
    # A published table can precede a driver's first appearance; an unavailable
    # table above is never a zero. Stable IDs avoid historical code collisions.
    return 0.0


async def load_points_series(season, kind, identifiers, schedule, fetch, progress=None):
    latest = await asyncio.wait_for(fetch(season), timeout=20)
    if latest is None or latest.empty:
        raise ValueError("Опубликованный зачёт сейчас недоступен.")
    now = datetime.now(timezone.utc)
    published_round = latest.attrs.get("round")
    events = []
    for event in sorted(schedule or [], key=lambda e: int(e["round"])):
        if event.get("is_cancelled") or event.get("is_testing"):
            continue
        if published_round is not None and int(event["round"]) > int(published_round):
            continue
        try:
            at = datetime.fromisoformat(str(event["race_start_utc"]).replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if at > now:
                continue
        except (KeyError, ValueError, TypeError):
            if season >= now.year:
                continue
        events.append(event)
    if not events:
        raise ValueError("В этом сезоне ещё нет этапов с опубликованным зачётом.")
    limiter = asyncio.Semaphore(2)
    completed = 0
    async def snapshot(event):
        nonlocal completed
        try:
            if published_round is not None and int(event["round"]) == int(published_round):
                frame = latest
            else:
                async with limiter:
                    frame = await asyncio.wait_for(fetch(season, int(event["round"])), timeout=20)
            if frame is not None and frame.attrs.get("round") not in (None, int(event["round"])):
                frame = None
            values = [participant_points(frame, identifier, kind) for identifier in identifiers]
        except Exception:
            values = [None] * len(identifiers)
        completed += 1
        if progress:
            await progress(completed, len(events))
        return values
    tasks = [asyncio.create_task(snapshot(event)) for event in events]
    try:
        values = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not any(any(value is not None for value in pair) for pair in values):
        raise ValueError("Данные этапов недоступны. Попробуйте позже.")
    return {"events": events, "histories": [[pair[i] for pair in values] for i in range(len(identifiers))],
            "totals": [participant_points(latest, identifier, kind) for identifier in identifiers],
            "missing": sum(any(value is None for value in pair) for pair in values)}
