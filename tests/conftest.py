"""
Pytest fixtures for TurboTears tests.
"""
import os
import random
import socket
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Collection must also be isolated: application modules read configuration on import.
_suite_directory = tempfile.TemporaryDirectory(prefix="f1hub-tests-")
os.environ["BOT_TOKEN"] = "123456:TEST"
os.environ["REDIS_URL"] = ""
os.environ["DATABASE_PATH"] = str(Path(_suite_directory.name) / "collection.db")
os.environ["EMAIL_DELIVERY_MODE"] = "mock"
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_EMAIL"] = "primary-admin@example.test"
os.environ["ADMIN_TELEGRAM_ID"] = "100000001"
os.environ["ADMIN_IDS"] = "100000001"


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Run opt-in read-only external API checks")
    parser.addoption("--test-order-seed", type=int, help="Shuffle cases with a reproducible seed")
    parser.addoption("--case-notes", action="store_true", help="Print the description before each case")


def pytest_configure(config):
    # unittest's skipUnless is evaluated at collection, before fixtures run.
    if config.getoption('--live'):
        os.environ['RUN_LIVE_PREDICTION_APIS'] = '1'
    else:
        os.environ.pop('RUN_LIVE_PREDICTION_APIS', None)


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.path.name == "test_prediction_api_sources_live.py":
            item.add_marker(pytest.mark.live)
            if not config.getoption("--live"):
                item.add_marker(pytest.mark.skip(reason="External APIs require --live"))
        else:
            integration = {"api_client", "app_with_overrides", "db_session", "temp_db_path", "store", "recovery"}
            item.add_marker(pytest.mark.integration if integration.intersection(item.fixturenames) else pytest.mark.unit)
    seed = config.getoption("--test-order-seed")
    if seed is not None:
        random.Random(seed).shuffle(items)


@pytest.fixture(autouse=True)
def offline_network(request, monkeypatch):
    """Default suites cannot contact external services, even from an unmocked fallback."""
    if request.node.get_closest_marker("live") and request.config.getoption("--live"):
        monkeypatch.setenv("RUN_LIVE_PREDICTION_APIS", "1")
        yield
        return
    import aiohttp
    import requests
    attempts = []
    def reject():
        attempts.append(request.node.nodeid)
        raise AssertionError(f"Unmocked external connection in {request.node.nodeid}; mock the transport")
    http_request = aiohttp.ClientSession._request
    async def guarded_http(client, method, url, **kwargs):
        if urlsplit(str(url)).hostname in {"127.0.0.1", "::1", "localhost"}:
            return await http_request(client, method, url, **kwargs)
        reject()
    sync_request = requests.Session.request
    def guarded_sync(client, method, url, **kwargs):
        if urlsplit(str(url)).hostname in {"127.0.0.1", "::1", "localhost"}:
            return sync_request(client, method, url, **kwargs)
        reject()
    connect = socket.socket.connect
    def guarded_connect(client, address):
        # Event loops use local sockets internally; ASGI requests use no sockets.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return connect(client, address)
        reject()
    monkeypatch.setattr(aiohttp.ClientSession, "_request", guarded_http)
    monkeypatch.setattr(requests.Session, "request", guarded_sync)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield
    assert not attempts, "An external connection was attempted and swallowed; mock the dependency explicitly"


@pytest_asyncio.fixture(autouse=True)
async def isolated_application_state(tmp_path, tmp_path_factory, monkeypatch):
    """Each case gets a fresh shared DB path and F1 cache, even without an API fixture."""
    from app.db import db
    from app import f1_data
    await db.close()
    original_path = db.db_path
    db.db_path = tmp_path / "application.db"
    monkeypatch.setenv("DATABASE_PATH", str(db.db_path))
    cache = tmp_path_factory.mktemp("f1-cache")
    monkeypatch.setattr(f1_data, "_fallback_cache_dir", cache)
    monkeypatch.setattr(f1_data, "_MEMORY_CACHE", OrderedDict())
    monkeypatch.setattr(f1_data, "_REDIS_CLIENT", None)
    try:
        yield
    finally:
        await db.close()
        db.db_path = original_path


@pytest_asyncio.fixture
async def db_session(isolated_application_state):
    from app.db import db
    await db.connect()
    await db.init_tables()
    return db


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def close_shared_database_after_suite():
    """Release the application's shared SQLite worker before pytest exits."""
    yield
    from app.db import db

    await db.close()
    _suite_directory.cleanup()


def _test_description(item: pytest.Item) -> str:
    """Human-readable test description from docstring or function name."""
    obj = getattr(item, "obj", None)
    doc: Optional[str] = getattr(obj, "__doc__", None) if obj else None
    if doc:
        first_line = doc.strip().splitlines()[0].strip()
        if first_line:
            return first_line
    return item.name.replace("_", " ")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Print what each test validates before execution."""
    if not item.config.getoption("--case-notes"):
        return
    tr = item.config.pluginmanager.getplugin("terminalreporter")
    if tr is None:
        return
    tr.write_line(f"[CHECK] {item.nodeid} -> {_test_description(item)}")


@pytest_asyncio.fixture
async def temp_db_path(tmp_path):
    """Временная БД для изолированных тестов."""
    return tmp_path / "isolated.db"


@pytest_asyncio.fixture
async def app_with_overrides(db_session):
    """
    FastAPI app с переопределёнными зависимостями для тестов:
    - get_current_user_id всегда возвращает тестовый user_id
    - Redis/DB можно мокировать
    """
    from app.api.miniapp_api import (
        get_current_user_id,
        get_optional_user_id,
        get_prediction_user_id,
        web_app,
    )
    from app.db import get_or_create_user

    async def fake_get_current_user_id():
        return 999888

    prediction_user_id = await get_or_create_user(999888)

    original_overrides = web_app.dependency_overrides.copy()
    web_app.dependency_overrides[get_current_user_id] = fake_get_current_user_id
    web_app.dependency_overrides[get_optional_user_id] = fake_get_current_user_id

    async def fake_get_prediction_user_id():
        return prediction_user_id

    web_app.dependency_overrides[get_prediction_user_id] = fake_get_prediction_user_id

    try:
        yield web_app
    finally:
        web_app.dependency_overrides.clear()
        web_app.dependency_overrides.update(original_overrides)


@pytest_asyncio.fixture
async def api_client(app_with_overrides):
    """HTTP клиент для тестирования API."""
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
def sample_driver_standings_df():
    """Пример DataFrame для тестов standings."""
    import pandas as pd

    return pd.DataFrame([
        {"position": 1, "points": 100, "driverCode": "VER", "givenName": "Max", "familyName": "Verstappen", "constructorId": "red_bull", "constructorName": "Red Bull", "driverId": "verstappen", "permanentNumber": "1"},
        {"position": 2, "points": 85, "driverCode": "NOR", "givenName": "Lando", "familyName": "Norris", "constructorId": "mclaren", "constructorName": "McLaren", "driverId": "norris", "permanentNumber": "4"},
    ])


@pytest.fixture
def sample_constructor_standings_df():
    """Пример DataFrame для тестов constructors."""
    import pandas as pd

    return pd.DataFrame([
        {"position": 1, "points": 180, "constructorId": "red_bull", "constructorName": "Red Bull"},
        {"position": 2, "points": 150, "constructorId": "mclaren", "constructorName": "McLaren"},
    ])


@pytest.fixture
def sample_schedule():
    """Пример расписания сезона."""
    return [
        {"round": 1, "date": "2024-03-02", "event_name": "Bahrain Grand Prix", "country": "Bahrain", "location": "Sakhir", "race_start_utc": "2024-03-02T15:00:00+00:00"},
        {"round": 2, "date": "2024-03-09", "event_name": "Saudi Arabian Grand Prix", "country": "Saudi Arabia", "location": "Jeddah", "race_start_utc": "2024-03-09T17:00:00+00:00"},
    ]
