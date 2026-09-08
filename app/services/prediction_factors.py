"""Inspectable features with explicit priors and sample counts, not learned weights."""
import math


def features(driver, history, session, current):
    values = {k: [] for k in ("long", "recent", "team", "qualifying", "circuit", "teammate", "gains")}
    race_starts = race_failures = team_starts = team_failures = 0.0
    positions, timeline = [], []
    primary_seen = 0
    for event in history:
        kind = event.get("session", session)
        weight = event["weight"]
        rows = event["rows"]
        n = max(1, len(rows) - 1)
        own = next((r for r in rows if (driver.get("driver_id") and r.get("driver_id") == driver["driver_id"]) or r["code"] == driver["code"]), None)
        def same_team(row):
            return (bool(driver.get("team_id")) and row.get("team_id") == driver["team_id"]) or row["team"] == driver["team"]
        for row in rows:
            if same_team(row):
                if kind == session and not (kind == "race" and row.get("dnf")):
                    values["team"].append((1 - (row["position"] - 1) / n, weight))
                if kind == "race":
                    team_starts += weight
                    team_failures += weight * bool(row.get("dnf"))
        if own is None:
            continue
        strength = 1 - (own["position"] - 1) / n
        # Driver skill partly transfers between teams; car-dependent results less so.
        personal_weight = weight * (1 if same_team(own) else .55)
        if kind == "race":
            race_starts += personal_weight
            race_failures += personal_weight * bool(own.get("dnf"))
            if not own.get("dnf") and 1 <= own.get("grid", 0) <= len(rows):
                gain = (own["grid"] - own["position"]) / n
                values["gains"].append((.5 + .5 * gain, personal_weight))
        if kind == "qualifying":
            values["qualifying"].append((strength, personal_weight))
        if kind != session:
            continue
        primary_seen += 1
        if len(timeline) < 12:
            timeline.append({"season": event.get("season"), "round": event.get("round"),
                             "name": event.get("name", "Сессия"), "position": own["position"], "dnf": bool(own.get("dnf")),
                             "team": own["team"]})
        # Non-finishes modelled separately, rather than penalizing pace twice.
        if kind == "race" and own.get("dnf"):
            continue
        values["long"].append((strength, personal_weight))
        positions.append(strength)
        if primary_seen <= 6:
            values["recent"].append((strength, .85 ** (primary_seen - 1) * (1 if same_team(own) else .55)))
        if event.get("circuit"):
            values["circuit"].append((strength, personal_weight))
        mates = [r for r in rows if r["team"] == own["team"] and r["code"] != own["code"] and not (kind == "race" and r.get("dnf"))]
        if mates:
            margin = sum((r["position"] - own["position"]) / n for r in mates) / len(mates)
            values["teammate"].append((.5 + margin * .5, weight))
    weights = {"long": .20, "recent": .22, "team": .20, "qualifying": .12, "circuit": .10, "teammate": .10, "gains": .06} if session == "race" else {"long": .24, "recent": .22, "team": .18, "qualifying": .16, "circuit": .10, "teammate": .10, "gains": 0}
    labels = {"long": "Долгосрочная форма", "recent": "Последние 6 выступлений", "team": "Форма текущей команды",
              "qualifying": "Квалификационный темп", "circuit": "История этой трассы", "teammate": "Сравнение с напарником", "gains": "Старт → финиш"}
    current_map = {r["code"]: r["position"] for r in current}
    live_weight = (.30 if session == "race" else .12) if driver["code"] in current_map else 0
    factors = []
    for key, samples in values.items():
        if not weights[key]:
            continue
        effective = sum(w for _, w in samples)
        value = (1 + sum(v * w for v, w in samples)) / (2 + effective)
        weight = weights[key] * (1 - live_weight)
        factors.append({"key": key, "label": labels[key], "value": value, "weight": weight,
                        "contribution": (value - .5) * weight, "samples": len(samples), "effective_samples": effective})
    if live_weight:
        value = 1 - (current_map[driver["code"]] - 1) / max(1, len(current) - 1)
        factors.append({"key": "weekend", "label": "Текущий уикенд", "value": value,
                        "weight": live_weight, "contribution": (value - .5) * live_weight, "samples": 1, "effective_samples": 1})
    rating = sum(f["value"] * f["weight"] for f in factors)
    own_risk = (race_failures + 1) / (race_starts + 10)
    team_risk = (team_failures + 1) / (team_starts + 10)
    reliability = .6 * own_risk + .4 * team_risk if session == "race" else 0
    mean = sum(positions[:20]) / max(1, len(positions[:20]))
    deviation = math.sqrt(sum((p - mean) ** 2 for p in positions[:20]) / max(1, len(positions[:20])))
    noise = max(.9, min(1.25, .85 + deviation)) if len(positions) >= 4 else 1.25
    return {"rating": rating, "reliability": reliability, "noise": noise, "factors": factors,
            "timeline": timeline, "starts": primary_seen, "race_exposure": race_starts,
            "consistency": deviation if len(positions) >= 4 else None}
