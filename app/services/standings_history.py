"""Official year-end standings, shared by the archive and comparisons.

An unavailable year is not a zero-point season. Team IDs deliberately remain
separate across renames: sporting continuity cannot be inferred from a name.
"""
import asyncio
import math
from datetime import datetime, timezone

from app.f1_data import _profile_http_session, cache_result

BASE = "https://api.jolpi.ca/ergast/f1"


def parse_standings(payload: dict, kind: str, season: int) -> list[dict]:
    lists = payload["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return []
    latest = max(lists, key=lambda item: int(item["round"]))
    if int(latest["season"]) != season:
        raise ValueError("Источник вернул другой сезон")
    driver = kind == "drivers"
    entries = latest["DriverStandings" if driver else "ConstructorStandings"]
    rows = []
    for entry in entries:
        entity = entry["Driver" if driver else "Constructor"]
        raw_position = str(entry.get("position") or "")
        position = int(raw_position) if raw_position.isdigit() and int(raw_position) > 0 else None
        points = float(entry["points"])
        if not math.isfinite(points):
            raise ValueError("Источник вернул некорректные очки")
        rows.append({
            "id": entity["driverId" if driver else "constructorId"],
            "name": f"{entity['givenName']} {entity['familyName']}" if driver else entity["name"],
            "position": position, "position_text": str(entry.get("positionText") or raw_position or "—"), "points": points,
            "wins": int(entry["wins"]), "round": int(latest["round"]),
            "teams": [team["name"] for team in entry.get("Constructors", [])],
        })
    return rows


@cache_result(ttl=3600, key_prefix="history_year_v1")
async def load_history_year(kind: str, season: int) -> list[dict]:
    endpoint = "driverStandings" if kind == "drivers" else "constructorStandings"
    rows = []
    offset = 0
    async with _profile_http_session() as session:
        while True:
            async with session.get(f"{BASE}/{season}/{endpoint}.json",
                                   params={"limit": 100, "offset": offset}, timeout=12) as response:
                response.raise_for_status()
                payload = await response.json()
            await asyncio.sleep(1.1)  # Only actual network reads are paced; cached years return immediately.
            page = parse_standings(payload, kind, season)
            rows.extend(page)
            total = int(payload["MRData"]["total"])
            offset += len(page)
            if offset >= total:
                break
            if not page:
                raise ValueError("Неполная страница исторического зачёта")
    return rows


async def get_standings_history(kind: str, ids: list[str], start: int, end: int) -> dict:
    series = {identifier: {"id": identifier, "name": identifier, "seasons": []} for identifier in ids}
    years = []
    for season in range(start, end + 1):
        try:
            rows = await load_history_year(kind, season)
            status = "available" if rows else "missing"
        except Exception:
            rows, status = [], "unavailable"
        lookup = {row["id"]: row for row in rows}
        years.append({"season": season, "status": status,
                      "source": f"{BASE}/{season}/{'driverStandings' if kind == 'drivers' else 'constructorStandings'}.json"})
        for identifier, item in series.items():
            row = lookup.get(identifier)
            if row:
                item["name"] = row["name"]
            item["seasons"].append({"season": season, "status": status,
                                    "current": season == datetime.now(timezone.utc).year,
                                    "standing": row})
    return {"kind": kind, "series": list(series.values()), "years": years,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Места сравниваются в зачёте каждого сезона. Системы начисления очков менялись; очки разных эпох напрямую несопоставимы. Текущий сезон — промежуточный. Разные ID команд не объединяются автоматически."}
