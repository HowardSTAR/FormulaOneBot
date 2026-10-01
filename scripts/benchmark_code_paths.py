"""Repeatable local code-path benchmark: no HTTP, Telegram or production DB.

Measures duplicated source work, portrait transforms and TLS configuration.
Timings describe these synthetic paths, not end-to-end production latency.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from app import f1_data
from app.api.miniapp_api import _render_head_crop_png_bytes


async def measure():
    f1_data._REDIS_CLIENT = None
    source_calls = 0
    with tempfile.TemporaryDirectory() as directory:
        f1_data._fallback_cache_dir = Path(directory)
        f1_data._MEMORY_CACHE.clear()

        @f1_data.cache_result(ttl=60, key_prefix="local_benchmark")
        async def fixture(season):
            nonlocal source_calls
            source_calls += 1
            await asyncio.sleep(.02)
            return pd.DataFrame({"round": range(1000), "points": [12.5] * 1000})

        start = time.perf_counter()
        results = await asyncio.gather(*(fixture(2026) for _ in range(20)))
        burst_ms = (time.perf_counter() - start) * 1000
        assert all(result.equals(results[0]) for result in results)

    path = ROOT / "app/assets/2026/pilots/RUS.webp"
    start = time.perf_counter()
    portraits = [_render_head_crop_png_bytes(path) for _ in range(10)]
    portrait_ms = (time.perf_counter() - start) * 1000
    assert len(set(portraits)) == 1
    start = time.perf_counter()
    for _ in range(10):
        async with f1_data._profile_http_session():
            pass
    tls_ms = (time.perf_counter() - start) * 1000
    return {"fixture_requests": 20, "fixture_source_calls": source_calls,
            "fixture_burst_ms": round(burst_ms, 2), "portrait_reads": 10,
            "portrait_total_ms": round(portrait_ms, 2), "tls_sessions": 10,
            "tls_setup_ms": round(tls_ms, 2)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(measure())
    raw = json.dumps(result, indent=2)
    print(raw)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
