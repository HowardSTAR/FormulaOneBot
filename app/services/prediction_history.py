"""Paginated multi-season archive. Cache complete downloads, never partial pages."""
import asyncio
import json
import time
from datetime import datetime, timezone

from app.db import db

BASE = "https://api.jolpi.ca/ergast/f1"
HISTORY_YEARS = 5


async def archive(client, year, session, cutoff):
    key = f"v2:{year}:{session}"
    cached = None
    if db.conn is not None:
        cached = await (await db.conn.execute("SELECT payload,fetched_at FROM prediction_history_cache WHERE key=?", (key,))).fetchone()
    ttl = 3600 if year == datetime.fromtimestamp(cutoff, timezone.utc).year else 7 * 86400
    if cached and cutoff - cached["fetched_at"] < ttl:
        return json.loads(cached["payload"])
    kind = "results" if session == "race" else "qualifying"
    field = "Results" if session == "race" else "QualifyingResults"
    merged, offset, total = {}, 0, None
    for _ in range(12):
        await asyncio.sleep(.4)  # Avoid bursting at the provider's shared endpoint.
        response = await client.get(f"{BASE}/{year}/{kind}/", params={"limit": 100, "offset": offset})
        response.raise_for_status()
        data = response.json()["MRData"]
        page_total = int(data["total"])
        if total is not None and page_total != total:
            raise ValueError("Архив изменился во время загрузки; повторите расчёт")
        total = page_total
        count = 0
        for race in data["RaceTable"]["Races"]:
            if int(race["season"]) != year:
                raise ValueError("Неверный сезон архива")
            number = int(race["round"])
            entry = merged.setdefault(number, {**race, field: []})
            rows = race.get(field, [])
            entry[field].extend(rows)
            count += len(rows)
        offset += count
        if offset >= total:
            break
        if not count:
            raise ValueError("Неполная страница архива")
    else:
        raise ValueError("Архив превышает допустимый размер")
    if offset != total:
        raise ValueError("Неполный архив")
    result = list(merged.values())
    if result and db.conn is not None:
        async with db.write_lock:
            await db.conn.execute("INSERT INTO prediction_history_cache(key,payload,fetched_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at", (key, json.dumps(result), time.time()))
            await db.conn.commit()
    return result


async def load_history(client, season, event, cutoff, normalize, parse_time):
    history, failures = [], []
    # Newest first: partial provider outages still leave current form usable.
    for year in range(season, season - HISTORY_YEARS, -1):
        for session in ("race", "qualifying"):
            try:
                races = await archive(client, year, session, cutoff)
            except Exception as exc:
                failures.append(f"{year} / {session}: {type(exc).__name__}")
                continue
            for race in races:
                end = parse_time(f"{race.get('date', '')}T{race.get('time') or '23:59:59Z'}") + 4 * 3600
                if end <= 4 * 3600 or end >= cutoff:
                    continue
                # Same-weekend sessions enter through the explicitly gated current input.
                if year == season and int(race["round"]) == int(event["round"]):
                    continue
                rows = normalize(race, session)
                if not rows:
                    continue
                circuit = race.get("Circuit", {})
                locality = circuit.get("Location", {}).get("locality", "")
                age_days = max(0, (cutoff - end) / 86400)
                # Long history remains relevant; recent form is a separate feature.
                weight = 2 ** (-age_days / 540)
                if year < 2026 <= season:
                    weight *= .4  # Explicit heuristic for a major regulations boundary.
                history.append({"season": year, "round": int(race["round"]), "name": race["raceName"],
                                "session": session, "ended_at": end, "weight": weight, "rows": rows,
                                "circuit_id": circuit.get("circuitId"),
                                "circuit": locality.casefold() == str(event.get("location", "")).casefold()
                                or race["raceName"].casefold() == str(event.get("event_name", "")).casefold()})
    history.sort(key=lambda h: h["ended_at"], reverse=True)
    return history, {"requested_years": list(range(season - HISTORY_YEARS + 1, season + 1)),
                     "loaded_years": sorted({h["season"] for h in history}),
                     "races": sum(h["session"] == "race" for h in history),
                     "qualifying": sum(h["session"] == "qualifying" for h in history),
                     "observations": sum(len(h["rows"]) for h in history), "unavailable": failures}
