"""Deterministic, evidence-based race recap. No AI, narrative guesses or writes."""
import asyncio
import math
from datetime import datetime, timezone
from html import escape
import pandas as pd

from app.f1_data import (cache_result, get_driver_standings_async,
                         get_constructor_standings_async, get_race_results_async, _profile_http_session)


@cache_result(ttl=600, key_prefix="recap_driver_results_v1")
async def driver_season_finishes(season: int, identifier: str) -> list[dict]:
    """One bounded season query, not a claim about a driver's entire career."""
    url = f"https://api.jolpi.ca/ergast/f1/{season}/drivers/{identifier}/results.json?limit=100"
    async with _profile_http_session() as session:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            payload = await response.json()
    mr = payload["MRData"]
    races = mr["RaceTable"]["Races"]
    rows = [{"round": int(race["round"]), "position": int(result["position"]), "id": result["Driver"]["driverId"]}
            for race in races if int(race["season"]) == season for result in race["Results"]]
    if len(rows) != int(mr["total"]) or any(row["id"] != identifier for row in rows):
        raise ValueError("Неполная история результатов пилота")
    return rows


def classified_rows(frame: pd.DataFrame | None) -> list[dict]:
    if frame is None or frame.empty or not {"Position", "Points", "Abbreviation"}.issubset(frame.columns):
        return []
    if "DataComplete" in frame and not bool(frame["DataComplete"].fillna(False).all()):
        return []
    rows = []
    try:
        for _, row in frame.iterrows():
            position, points = float(row["Position"]), float(row["Points"])
            code = row["Abbreviation"]
            if not math.isfinite(position) or not position.is_integer() or position < 1 or not math.isfinite(points) or not isinstance(code, str) or not code:
                return []
            grid = row.get("GridPosition")
            grid = int(grid) if grid is not None and pd.notna(grid) and float(grid).is_integer() else 0
            full_name = row.get("FullName")
            rows.append({"Position": int(position), "Points": points, "Abbreviation": code,
                         "FullName": full_name if isinstance(full_name, str) else code, "GridPosition": grid})
    except (TypeError, ValueError, OverflowError):
        return []
    if len(rows) < 5 or len({r["Position"] for r in rows}) != len(rows) or len({r["Abbreviation"] for r in rows}) != len(rows) or not any(r["Position"] == 1 for r in rows):
        return []
    if not any(r["Points"] > 0 for r in rows):
        return []  # A pre-race/live skeleton must not become a winner story.
    return rows


def build_recap(race: list[dict], before: list[dict], after: list[dict],
                teams_before: list[dict], teams_after: list[dict], first_podiums: list[str] | None = None) -> list[dict]:
    """Rank supported stories; never infer overtakes, causes or title clinches."""
    candidates = []

    def add(priority, category, title, text):
        candidates.append({"priority": priority, "category": category, "title": title, "text": text})

    def championship(old, new, team=False):
        key = "constructorId" if team else "driverId"
        label = "Кубок конструкторов" if team else "Чемпионат пилотов"
        def name(row):
            return row.get("constructorName", "") if team else f"{row.get('givenName', '')} {row.get('familyName', '')}".strip()
        old = sorted((r for r in old if r.get("position", 0) > 0), key=lambda r: r["position"])
        new = sorted((r for r in new if r.get("position", 0) > 0), key=lambda r: r["position"])
        if len(old) < 2 or len(new) < 2:
            return
        category = "constructors" if team else "championship"
        gap = new[0]["points"] - new[1]["points"]
        if old[0].get(key) and new[0].get(key) and old[0][key] != new[0][key]:
            add(95 if team else 100, category, f"Новый лидер: {name(new[0])}",
                f"{label}: P{next((r['position'] for r in old if r.get(key) == new[0][key]), '—')} → P1. "
                f"Теперь разница с {name(new[1])} — {gap:g} очк." + (" При равенстве очков место определяют дополнительные показатели." if gap == 0 else ""))
        elif [r.get(key) for r in old[:2]] == [r.get(key) for r in new[:2]]:
            previous = old[0]["points"] - old[1]["points"]
            if gap != previous:
                add((80 if gap <= 50 else 55) if team else 90, category,
                    f"{'Кубок конструкторов' if team else 'Личный зачёт'}: отрыв {'сократился' if gap < previous else 'вырос'}",
                    f"{label}: {name(new[0])} перед {name(new[1])} — {previous:g} → {gap:g} очк.")
        positions = {r.get(key): r["position"] for r in old if r.get(key)}
        movers = [(positions[r[key]] - r["position"], r) for r in new if r.get(key) in positions]
        if movers:
            gain, row = max(movers, key=lambda pair: pair[0])
            if gain >= 2 and (team or row.get("driverCode") not in (first_podiums or [])):
                add(72 if team else 75, category + "_move", f"{name(row)} поднялся в зачёте",
                    f"P{positions[row[key]]} → P{row['position']} (+{gain} поз.). Это изменение места в сезоне, не число обгонов.")

    championship(before, after)
    championship(teams_before, teams_after, True)
    finishers = sorted((r for r in race if r.get("Position", 0) > 0), key=lambda r: r["Position"])
    if finishers:
        winner = finishers[0]
        name = winner.get("FullName") or winner.get("Abbreviation", "Победитель")
        old = next((r for r in before if r.get("driverCode") == winner.get("Abbreviation")), None)
        new = next((r for r in after if r.get("driverCode") == winner.get("Abbreviation")), None)
        if old is not None and new is not None and old.get("wins") == 0 and new.get("wins", 0) == 1:
            add(85, "winner", f"Первая победа в сезоне: {name}",
                f"До этого этапа — 0 побед в Гран-при, теперь — 1. В чемпионате — P{new['position']}, {new['points']:g} очк.")
        else:
            add(50, "winner", f"{name} выиграл гонку",
                f"За Гран-при — {winner.get('Points', 0):g} очк." +
                (f" После уик-энда — P{new['position']} и {new['points']:g} очк. в чемпионате." if new else " Зачёт чемпионата пока не подтверждён."))
        for row in finishers[:3]:
            if row.get("Abbreviation") not in (first_podiums or []):
                continue
            if row["Position"] == 1 and old is not None and new is not None and old.get("wins") == 0 and new.get("wins") == 1:
                continue  # A first win already describes this first podium.
            standing = next((r for r in after if r.get("driverCode") == row.get("Abbreviation")), None)
            previous = next((r for r in before if r.get("driverCode") == row.get("Abbreviation")), None)
            movement = f" В зачёте: P{previous['position']} → P{standing['position']}." if standing and previous else ""
            add(88, "first_podium_" + row["Abbreviation"], f"Первый подиум сезона: {row.get('FullName') or row['Abbreviation']}",
                f"Финиш P{row['Position']:g}; в предыдущих Гран-при этого сезона подиумов не было.{movement}")
        gains = [(r.get("GridPosition", 0) - r["Position"], r) for r in finishers if r.get("GridPosition", 0) > 0]
        if gains:
            gain, row = max(gains, key=lambda pair: pair[0])
            if gain >= 5:
                add(60, "race_move", f"{row.get('FullName') or row.get('Abbreviation')}: +{gain} позиций",
                    f"Старт P{row['GridPosition']:g} → финиш P{row['Position']:g}. Это разница классификаций; она не доказывает {gain} обгонов на трассе.")
    return [{k: v for k, v in item.items() if k != "priority"}
            for item in sorted(candidates, key=lambda item: -item["priority"])[:3]]


@cache_result(ttl=120, key_prefix="race_recap_v2")
async def get_race_recap(season: int, round_num: int) -> dict:
    race = await get_race_results_async(season, round_num)
    rows = classified_rows(race)
    if not rows:
        return {"status": "waiting", "items": [], "note": "Ждём подтверждённую классификацию гонки.", "season": season, "round": round_num}

    async def standings(loader, round_number):
        if round_number == 0:
            return []
        try:
            frame = await loader(season, round_number)
            return frame.to_dict("records") if frame is not None and not frame.empty else []
        except Exception:
            return []

    before, after, teams_before, teams_after = await asyncio.gather(
        standings(get_driver_standings_async, round_num - 1), standings(get_driver_standings_async, round_num),
        standings(get_constructor_standings_async, round_num - 1), standings(get_constructor_standings_async, round_num))
    first_podiums, extra_sources = [], []
    for row in sorted(rows, key=lambda r: r["Position"])[:3]:
        standing = next((r for r in after if r.get("driverCode") == row["Abbreviation"]), None)
        if not standing or not standing.get("driverId"):
            continue
        try:
            finishes = await driver_season_finishes(season, standing["driverId"])
            # The current podium must appear too: an outdated feed cannot prove absence.
            current = any(r["round"] == round_num and r["position"] == row["Position"] for r in finishes)
            if current and not any(r["round"] < round_num and r["position"] <= 3 for r in finishes):
                first_podiums.append(row["Abbreviation"])
                extra_sources.append({"title": f"Гран-при сезона: {row['FullName']}",
                                      "url": f"https://api.jolpi.ca/ergast/f1/{season}/drivers/{standing['driverId']}/results.json"})
        except Exception:
            pass  # Never block a factual recap because an optional story is unavailable.
    items = build_recap(rows, before, after, teams_before, teams_after, first_podiums)
    sources = [{"title": "Результаты сезона Formula 1 (классификация загружена через FastF1)", "url": f"https://www.formula1.com/en/results/{season}/races"}]
    sources.extend(extra_sources)
    for number in (round_num - 1, round_num):
        if number > 0:
            for endpoint in ("driverStandings", "constructorStandings"):
                sources.append({"title": f"{endpoint} после этапа {number}", "url": f"https://api.jolpi.ca/ergast/f1/{season}/{number}/{endpoint}.json"})
    return {"season": season, "round": round_num,
            "status": "ready" if after and teams_after and (round_num == 1 or before and teams_before) else "partial",
            "items": items, "sources": sources, "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Автоматическая сводка по правилам, без ИИ. Изменения зачёта — за весь уик-энд, включая спринт и опубликованные корректировки. Первые победы и подиумы — в выбранном сезоне, не в карьере. Причины событий не выводятся из очков."}


def format_recap_telegram(recap: dict, spoiler: bool = False) -> str:
    lines = [f"• <b>{escape(item['title'])}</b>\n{escape(item['text'])}" for item in recap.get("items", [])]
    text = "\n\n".join(lines)
    return f'<span class="tg-spoiler">{text}</span>' if spoiler and text else text


def recap_caption(recap: dict, spoiler: bool = False) -> str:
    """Select whole stories within Telegram's budget; never truncate HTML."""
    if recap.get("status") == "waiting":
        return ""
    lines = []
    for item in recap.get("items", [])[:3]:
        line = f"• {escape(item['title'])}\n{escape(item['text'])}"
        if len("\n\n".join([*lines, line])) <= 680:
            lines.append(line)
    text = "\n\n".join(lines)
    if text and spoiler:
        text = f'<span class="tg-spoiler">{text}</span>'
    return "\n\nГлавное после гонки:\n" + text + "\nПодробности и источники — на сайте. Изменения зачёта — за уик-энд." if text else ""
