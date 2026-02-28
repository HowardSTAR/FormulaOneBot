"""
Pytest fixtures for FormulaOneBot tests.
"""
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Устанавливаем тестовые переменные окружения ДО импорта app
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_PATH", "")


@pytest_asyncio.fixture
async def temp_db_path():
    """Временная БД для изолированных тестов."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def app_with_overrides(temp_db_path):
    """
    FastAPI app с переопределёнными зависимостями для тестов:
    - get_current_user_id всегда возвращает тестовый user_id
    - Redis/DB можно мокировать
    """
    os.environ["DATABASE_PATH"] = str(temp_db_path)

    from app.api.miniapp_api import web_app
    from app.auth import get_current_user_id
    from app.db import db

    async def fake_get_current_user_id():
        return 999888

    web_app.dependency_overrides[get_current_user_id] = fake_get_current_user_id

    # Инициализация БД для тестов
    await db.connect()
    await db.init_tables()

    yield web_app

    await db.close()
    web_app.dependency_overrides.clear()
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]


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
