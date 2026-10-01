"""Contract checks for shared optimizations; no external services or real DB."""
import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import io
import os
import pickle
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pandas as pd
from PIL import Image
import pytest

from app import f1_data
from app.api import miniapp_api as api
from app.db import Database
from app.utils import classification_card, portrait_render
from app.utils.singleflight import SingleFlight


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(f1_data, "_fallback_cache_dir", tmp_path)
    monkeypatch.setattr(f1_data, "_MEMORY_CACHE", OrderedDict())
    monkeypatch.setattr(f1_data, "_REDIS_CLIENT", None)
    return tmp_path


@pytest.mark.asyncio
async def test_twenty_identical_reads_share_source_and_keep_dataframe_metadata(isolated_cache):
    calls = 0
    @f1_data.cache_result(ttl=60)
    async def source(season):
        nonlocal calls
        calls += 1
        await asyncio.sleep(.01)
        frame = pd.DataFrame({"points": [12.5, 0]})
        frame.attrs["round"] = 15
        return frame
    results = await asyncio.gather(*(source(2026) for _ in range(20)))
    assert calls == 1
    assert all(result.attrs == {"round": 15} and result["points"].tolist() == [12.5, 0] for result in results)
    assert (await source(2026)).equals(results[0]) and calls == 1
    f1_data._MEMORY_CACHE.clear()
    assert (await source(2026)).attrs == {"round": 15} and calls == 1  # persisted cache


@pytest.mark.asyncio
async def test_different_seasons_arguments_and_identities_never_share_results(isolated_cache):
    calls = []
    @f1_data.cache_result()
    async def source(season, person):
        calls.append((season, person))
        return (season, person)
    values = [(2025, "one"), (2026, "one"), (2026, "two")]
    assert await asyncio.gather(*(source(*value) for value in values)) == values
    assert sorted(calls) == values


@pytest.mark.asyncio
async def test_one_cancelled_reader_does_not_cancel_the_other():
    flight, started, release = SingleFlight(), asyncio.Event(), asyncio.Event()
    calls = 0
    async def source():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "correct"
    first = asyncio.create_task(flight.run("same", source))
    await started.wait()
    second = asyncio.create_task(flight.run("same", source))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == "correct" and calls == 1
    assert not flight._pending


@pytest.mark.asyncio
async def test_last_reader_cancels_source_and_leaves_no_orphan():
    flight, started, stopped = SingleFlight(), asyncio.Event(), asyncio.Event()
    async def source():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    reader = asyncio.create_task(flight.run("same", source))
    await started.wait()
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader
    assert stopped.is_set() and not flight._pending


@pytest.mark.asyncio
async def test_failed_read_is_not_cached_and_can_retry(isolated_cache):
    calls = 0
    @f1_data.cache_result()
    async def source():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return {"points": 0}
    with pytest.raises(RuntimeError, match="temporary"):
        await source()
    assert await source() == {"points": 0} and calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, [], {}, ()])
async def test_missing_results_are_still_not_persistently_cached(isolated_cache, value):
    source = AsyncMock(return_value=value)
    cached = f1_data.cache_result()(source)
    # AsyncMock has no stable function name; give it the same callable contract.
    source.__name__ = "missing"
    assert await cached() == value
    assert await cached() == value
    assert source.await_count == 2
    assert not list(isolated_cache.glob("*.pkl"))


@pytest.mark.asyncio
async def test_empty_dataframe_retains_short_negative_ttl(isolated_cache):
    @f1_data.cache_result(ttl=3600)
    async def source():
        return pd.DataFrame()
    assert (await source()).empty
    expires, _ = next(iter(f1_data._MEMORY_CACHE.values()))
    assert 0 < expires - time.time() <= 60


@pytest.mark.asyncio
async def test_disk_reads_and_writes_do_not_run_on_event_loop(isolated_cache, monkeypatch):
    main_thread, threads = threading.get_ident(), []
    original_get, original_set = f1_data._fallback_cache_get, f1_data._fallback_cache_set
    def read(*args):
        threads.append(threading.get_ident())
        return original_get(*args)
    def write(*args):
        threads.append(threading.get_ident())
        return original_set(*args)
    monkeypatch.setattr(f1_data, "_fallback_cache_get", read)
    monkeypatch.setattr(f1_data, "_fallback_cache_set", write)
    @f1_data.cache_result()
    async def source():
        return ["published"]
    assert await source() == ["published"]
    assert len(threads) == 2 and all(thread != main_thread for thread in threads)


def test_memory_cache_evicts_lru_not_live_data_and_expired_entries(isolated_cache, monkeypatch):
    monkeypatch.setattr(f1_data, "_MEMORY_CACHE_LIMIT", 2)
    future = time.time() + 60
    f1_data._remember_cache("one", future, 1)
    f1_data._remember_cache("two", future, 2)
    assert f1_data._memory_cache_get("one") == 1
    f1_data._remember_cache("three", future, 3)
    assert list(f1_data._MEMORY_CACHE) == ["one", "three"]
    f1_data._remember_cache("expired", time.time() - 1, "old")
    assert f1_data._memory_cache_get("expired") is None


def test_parallel_disk_writers_leave_one_valid_file_not_partial_pickle(isolated_cache):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: f1_data._fallback_cache_set("same", [n] * 1000, 60), range(20)))
    files = list(isolated_cache.iterdir())
    assert len(files) == 1 and files[0].suffix == ".pkl"
    expires, data = pickle.loads(files[0].read_bytes())
    assert expires > time.time() and len(data) == 1000 and len(set(data)) == 1


def test_failed_disk_replace_keeps_previous_file_and_cleans_temporary(isolated_cache, monkeypatch):
    f1_data._fallback_cache_set("same", "old", 60)
    def failed(*args):
        raise OSError("read-only")
    monkeypatch.setattr(f1_data.os, "replace", failed)
    f1_data._fallback_cache_set("same", "new", 60)
    assert len(list(isolated_cache.iterdir())) == 1
    assert pickle.loads(next(isolated_cache.iterdir()).read_bytes())[1] == "old"


@pytest.mark.asyncio
async def test_corrupt_file_and_unavailable_redis_still_fall_back(isolated_cache, monkeypatch):
    client = SimpleNamespace(get=AsyncMock(side_effect=OSError("offline")), setex=AsyncMock(side_effect=OSError("offline")))
    monkeypatch.setattr(f1_data, "_REDIS_CLIENT", client)
    @f1_data.cache_result()
    async def source():
        return [12.5]
    key = f1_data._cache_key("", "source", (), {})
    import hashlib
    (isolated_cache / (hashlib.md5(key.encode()).hexdigest() + ".pkl")).write_bytes(b"invalid")
    assert await source() == [12.5]


@pytest.mark.asyncio
async def test_redis_initialization_and_shutdown_close_pools_without_flushing(monkeypatch):
    old = SimpleNamespace(aclose=AsyncMock())
    current = SimpleNamespace(ping=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(f1_data, "_REDIS_CLIENT", old)
    monkeypatch.setattr(f1_data.Redis, "from_url", lambda url: current)
    await f1_data.init_redis_cache("redis://fixture")
    old.aclose.assert_awaited_once()
    assert f1_data._REDIS_CLIENT is current
    await f1_data.close_redis_cache()
    current.aclose.assert_awaited_once()
    assert f1_data._REDIS_CLIENT is None


@pytest.mark.asyncio
async def test_failed_redis_initialization_releases_failed_pool(monkeypatch):
    client = SimpleNamespace(ping=AsyncMock(side_effect=OSError("offline")), aclose=AsyncMock())
    monkeypatch.setattr(f1_data, "_REDIS_CLIENT", None)
    monkeypatch.setattr(f1_data.Redis, "from_url", lambda url: client)
    await f1_data.init_redis_cache("redis://fixture")
    client.aclose.assert_awaited_once()
    assert f1_data._REDIS_CLIENT is None


@pytest.mark.asyncio
async def test_concurrent_database_connect_opens_once_with_same_pragmas(tmp_path, monkeypatch):
    from app import db as db_module
    original, calls = db_module.aiosqlite.connect, []
    def connect(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(db_module.aiosqlite, "connect", connect)
    database = Database(tmp_path / "isolated.db")
    await asyncio.gather(*(database.connect() for _ in range(20)))
    try:
        assert len(calls) == 1
        for statement, expected in [("PRAGMA foreign_keys", 1), ("PRAGMA busy_timeout", 30000), ("PRAGMA journal_mode", "wal")]:
            cursor = await database.conn.execute(statement)
            assert (await cursor.fetchone())[0] == expected
    finally:
        await asyncio.gather(*(database.close() for _ in range(10)))
    assert database.conn is None


@pytest.mark.asyncio
async def test_failed_database_configuration_closes_half_open_connection(tmp_path, monkeypatch):
    from app import db as db_module
    connection = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("configuration")), close=AsyncMock())
    monkeypatch.setattr(db_module.aiosqlite, "connect", AsyncMock(return_value=connection))
    database = Database(tmp_path / "isolated.db")
    with pytest.raises(RuntimeError, match="configuration"):
        await database.connect()
    assert database.conn is None
    connection.close.assert_awaited_once()


def test_portrait_cache_preserves_pixels_and_reopens_on_file_change(tmp_path, monkeypatch):
    path = tmp_path / "Pilot.png"
    Image.new("RGBA", (100, 300), "red").save(path)
    original_open, calls = portrait_render.Image.open, []
    def opened(file):
        calls.append(file)
        return original_open(file)
    monkeypatch.setattr(portrait_render.Image, "open", opened)
    first = portrait_render.render_head_crop_png_bytes(path)
    assert portrait_render.render_head_crop_png_bytes(path) == first and len(calls) == 1
    with original_open(io.BytesIO(first)) as rendered:
        assert rendered.size == (100, 105) and rendered.getpixel((0, 0)) == (255, 0, 0, 255)
    stamp = path.stat()
    Image.new("RGBA", (100, 300), "blue").save(path)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10000000))
    second = portrait_render.render_head_crop_png_bytes(path)
    assert second != first and len(calls) == 2


def test_portrait_cache_key_includes_crop_and_verified_manifest(tmp_path):
    path = tmp_path / "RUS.png"
    Image.new("RGBA", (320, 800), "red").save(path)
    before = portrait_render.render_head_crop_png_bytes(path)
    assert Image.open(io.BytesIO(before)).size == (320, 280)
    (tmp_path / "sources.json").write_text("{}")
    verified = portrait_render.render_head_crop_png_bytes(path)
    assert Image.open(io.BytesIO(verified)).size == (256, 256)
    (tmp_path / "sources.json").unlink()
    different_crop = portrait_render.render_head_crop_png_bytes(path, .5)
    assert Image.open(io.BytesIO(different_crop)).size == (320, 400)


@pytest.mark.asyncio
async def test_public_portrait_etag_revalidates_without_changing_strict_404(tmp_path, monkeypatch):
    path = tmp_path / "Pilot.png"
    Image.new("RGBA", (100, 300), "red").save(path)
    monkeypatch.setattr(api, "_find_local_pilot_portrait_path", lambda *args: path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.web_app), base_url="http://test") as client:
        response = await client.get("/api/pilot-portrait", params={"code": "RUS", "strict": True})
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        tag = response.headers["etag"]
        for candidate in (tag, f"W/{tag}", f'"other", {tag}'):
            unchanged = await client.get("/api/pilot-portrait", headers={"If-None-Match": candidate})
            assert unchanged.status_code == 304 and not unchanged.content
        path.unlink()
        assert (await client.get("/api/pilot-portrait", params={"strict": True})).status_code == 404


@pytest.mark.asyncio
async def test_logo_png_encoding_runs_off_event_loop(monkeypatch):
    threads, main_thread = [], threading.get_ident()
    class Logo:
        def save(self, output, format):
            assert format == "PNG"
            threads.append(threading.get_ident())
            output.write(b"fixture_png")
    monkeypatch.setattr(api, "_get_team_logo", lambda *args: Logo())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.web_app), base_url="http://test") as client:
        response = await client.get("/api/team-logo", params={"team": "mercedes", "season": 2026})
        assert response.status_code == 200 and response.content == b"fixture_png"
    assert threads and all(thread != main_thread for thread in threads)


def test_fonts_reuse_within_thread_but_not_between_render_threads():
    barrier = threading.Barrier(2)
    def render():
        first = classification_card._font(27, True)
        assert classification_card._font(27, True) is first
        barrier.wait(timeout=5)
        return first
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: render(), range(2)))
    assert first is not second


def test_singleflight_is_reusable_across_independent_event_loops():
    flight = SingleFlight()
    async def run(value):
        async def source():
            return value
        return await flight.run("same", source)
    assert asyncio.run(run(1)) == 1
    assert asyncio.run(run(2)) == 2
    assert not flight._pending
