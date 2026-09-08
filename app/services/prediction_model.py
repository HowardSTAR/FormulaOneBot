"""Reproducible, deliberately uncalibrated ranking model. No I/O or live data."""
from __future__ import annotations

import numpy as np
import re

MODEL_VERSION = "rank-monte-carlo-v1"


def simulate(roster: list[dict], history: list[dict], session: str,
             current: list[dict], wet_probability: float | None, seed: int = 42,
             trials: int = 12000, news: list[dict] | None = None) -> dict:
    if len(roster) < 10 or not history:
        raise ValueError("Недостаточно истории или участников для расчёта")
    codes = [r["code"] for r in roster]
    if len(set(codes)) != len(codes):
        raise ValueError("Повторяющиеся участники")
    n = len(codes)
    ratings, reliability, explanations, news_noise = [], [], [], []
    current_map = {r["code"]: r["position"] for r in current}
    for driver in roster:
        personal, team, circuit = [], [], []
        failures, starts = 0, 0
        for event in history:
            for row in event["rows"]:
                value = 1 - (row["position"] - 1) / max(1, len(event["rows"]) - 1)
                weight = event["weight"]
                if row["team"] == driver["team"]:
                    team.append((value, weight))
                if row["code"] == driver["code"]:
                    personal.append((value, weight))
                    if event.get("circuit"):
                        circuit.append((value, weight))
                    if session == "race":
                        starts += 1
                        failures += int(row.get("dnf", False))
        def average(values):
            # Two neutral pseudo-observations shrink sparse/new-driver samples.
            return (1 + sum(v * w for v, w in values)) / (2 + sum(w for _, w in values))
        p, t, c = average(personal), average(team), average(circuit)
        rating = .60 * p + .30 * t + .10 * c
        reasons = [f"Форма пилота {p:.2f}, команды {t:.2f}, трассы {c:.2f} (шкала 0–1)",
                   f"Исторических выступлений: {len(personal)}; малые выборки сглажены"]
        surname = driver["name"].split()[-1]
        mentions = [item for item in (news or [])
                    if re.search(r"\b" + re.escape(surname) + r"\b", item["title"], re.I)
                    and re.search(r"\b(crash\w*|penalt\w*|injur\w*|damage\w*|reliab\w*|engine|gearbox|illness)\b", item["title"], re.I)]
        # Headlines cannot establish facts or direction of performance. A disclosed,
        # capped sensitivity heuristic broadens uncertainty, never assigns penalties.
        multiplier = 1 + .05 * min(3, len({item["url"] for item in mentions}))
        news_noise.append(multiplier)
        if mentions:
            reasons.append(f"Новостные упоминания риска: {len(mentions)}; разброс +{(multiplier - 1):.0%}. Это сигнал заголовка, не подтверждённый штраф или поломка")
        if driver["code"] in current_map:
            position = current_map[driver["code"]]
            strength = 1 - (position - 1) / max(1, len(current) - 1)
            weight = .30 if session == "race" else .12
            rating = (1 - weight) * rating + weight * strength
            reasons.append(f"Последняя доступная сессия уикенда: P{position}, вес {weight:.0%}")
        # Beta(1,9) prior: 10% before observations. Includes all non-finishes.
        reliability.append((failures + 1) / (starts + 10) if session == "race" else 0)
        ratings.append(rating)
        explanations.append(reasons)
    rng = np.random.default_rng(seed)
    ratings = np.asarray(ratings)
    # Missing weather is NOT treated as an observed dry forecast.
    wet = rng.random(trials) < (wet_probability if wet_probability is not None else 0)
    noise = np.where(wet, .24, .15) if wet_probability is not None else np.full(trials, .20)
    scores = ratings + (rng.gumbel(size=(trials, n)) - np.euler_gamma) * noise[:, None] * np.asarray(news_noise)[None, :]
    dnf = rng.random((trials, n)) < np.clip(np.asarray(reliability)[None, :] * np.where(wet[:, None], 1.3, 1), 0, .8)
    scores -= dnf * 5
    order = np.argsort(-scores, axis=1)
    positions = np.argsort(order, axis=1) + 1
    result = []
    for i, driver in enumerate(roster):
        result.append({**driver, "win": float(np.mean(positions[:, i] == 1)),
                       "podium": float(np.mean(positions[:, i] <= 3)),
                       "top10": float(np.mean(positions[:, i] <= 10)),
                       "expected": float(np.mean(positions[:, i])),
                       "range": np.quantile(positions[:, i], [.1, .9]).astype(int).tolist(),
                       "dnf": float(np.mean(dnf[:, i])), "reasons": explanations[i]})
    favorites = np.argsort(-ratings)
    scenarios = []
    # Disjoint winner groups. A sample top-five is not an exact-order probability.
    groups = [("Победа фаворита", favorites[:2]), ("Победа преследователя", favorites[2:6]),
              ("Неожиданный победитель", favorites[6:])]
    for label, group in groups:
        mask = np.isin(order[:, 0], group)
        if not mask.any():
            continue
        subset = order[mask]
        representative = subset[np.argmin(np.abs(positions[mask] - positions[mask].mean(axis=0)).sum(axis=1))]
        scenarios.append({"label": label, "probability": float(mask.mean()),
                          "top5": [roster[i]["name"] for i in representative[:5]],
                          "why": "Группа по исходному рейтингу: " + ", ".join(roster[i]["name"] for i in group)
                          + ". Разброс формы" + (" и риск схода" if session == "race" else "")
                          + " меняют порядок. Пятёрка ниже — пример, не вероятность точного порядка."})
    return {"version": MODEL_VERSION, "seed": seed, "trials": trials,
            "drivers": sorted(result, key=lambda d: d["expected"]), "scenarios": scenarios,
            "calibrated": False}


def evaluate(forecast: dict, actual: list[dict]) -> dict:
    lookup = {r["code"]: r["position"] for r in actual}
    matched = [r for r in forecast["drivers"] if r["code"] in lookup]
    if not matched:
        return {"matched": 0, "total": len(forecast["drivers"]), "mae": None,
                "winner_brier": None, "podium_brier": None}
    return {"matched": len(matched), "total": len(forecast["drivers"]),
            "mae": float(np.mean([abs(r["expected"] - lookup[r["code"]]) for r in matched])),
            "winner_brier": float(np.mean([(r["win"] - int(lookup[r["code"]] == 1)) ** 2 for r in matched])),
            "podium_brier": float(np.mean([(r["podium"] - int(lookup[r["code"]] <= 3)) ** 2 for r in matched]))}
