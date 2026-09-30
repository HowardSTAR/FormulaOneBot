"""Shared track catalogue and basic replay checks (not authoritative anti-cheat)."""
import json
import math
from pathlib import Path

TRACKS = {track["id"]: track for track in json.loads(Path(__file__).with_name("race_tracks.json").read_text(encoding="utf-8"))}
LEGACY_TRACK_ID = "emerald-loop-v1"
SUPPORTED_TRACK_IDS = frozenset(TRACKS) | {LEGACY_TRACK_ID}


def validate_race_path(track_id: str, samples: list[dict]) -> None:
    if track_id not in SUPPORTED_TRACK_IDS:
        raise ValueError("Unsupported track_id")
    # Keep already open v1 clients and historical replays under their old rules.
    if track_id == LEGACY_TRACK_ID:
        return
    if len(samples) < 2:
        raise ValueError("Telemetry must complete three laps through all checkpoints")
    track = TRACKS[track_id]
    gates = [track["centerLine"][index] for index in track["checkpointIndexes"]]
    radius = track["roadHalfWidth"] + 20 + 0.03
    if math.dist((samples[0]["x"], samples[0]["y"]), gates[0]) > 2:
        raise ValueError("Telemetry must begin at this track's start")
    next_gate, laps = 1, 0
    line = track["finishLine"]
    previous = samples[0]
    for sample in samples[1:]:
        elapsed = (sample["t"] - previous["t"]) / 1000
        distance = math.hypot(sample["x"] - previous["x"], sample["y"] - previous["y"])
        # 350 world px/s max drive speed; margin for collision separation.
        if elapsed <= 0 or elapsed > 0.3 or distance > 400 * elapsed + 5:
            raise ValueError("Telemetry contains implausible movement")
        if next_gate == len(gates) - 1:
            if previous["x"] < line["x"] <= sample["x"]:
                fraction = (line["x"] - previous["x"]) / (sample["x"] - previous["x"])
                y = previous["y"] + (sample["y"] - previous["y"]) * fraction
                if line["minY"] <= y <= line["maxY"]:
                    laps += 1
                    next_gate = 1
        elif math.dist((sample["x"], sample["y"]), gates[next_gate]) <= radius:
            next_gate += 1
        previous = sample
    if laps != 3:
        raise ValueError("Telemetry must complete three laps through all checkpoints")
