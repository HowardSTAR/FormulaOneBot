"""
Тесты функций базы данных.
"""
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# Устанавливаем БД до импорта app
_db_path = None


@pytest_asyncio.fixture
async def db_session():
    """Изолированная сессия БД для тестов."""
    global _db_path
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        _db_path = Path(f.name)
    os.environ["DATABASE_PATH"] = str(_db_path)

    from app.db import db

    await db.connect()
    await db.init_tables()
    yield db
    await db.close()
    if _db_path.exists():
        _db_path.unlink(missing_ok=True)
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]


@pytest.mark.asyncio
async def test_get_or_create_user(db_session):
    """get_or_create_user создаёт пользователя при первом обращении."""
    from app.db import get_or_create_user

    user_id = await get_or_create_user(telegram_id=12345678)
    assert user_id > 0

    # Повторный вызов возвращает тот же id
    user_id2 = await get_or_create_user(telegram_id=12345678)
    assert user_id == user_id2


@pytest.mark.asyncio
async def test_get_user_settings_default(db_session):
    """get_user_settings возвращает настройки по умолчанию."""
    from app.db import get_user_settings

    settings = await get_user_settings(telegram_id=999888)
    assert "timezone" in settings
    assert "notify_before" in settings
    assert "notifications_enabled" in settings
    assert settings["timezone"] in ("Europe/Moscow", "UTC") or settings["timezone"].startswith("Etc/")


@pytest.mark.asyncio
async def test_update_user_setting(db_session):
    """update_user_setting сохраняет значение."""
    from app.db import get_user_settings, update_user_setting, get_or_create_user

    await get_or_create_user(telegram_id=111222)
    await update_user_setting(111222, "timezone", "Europe/Moscow")
    await update_user_setting(111222, "notify_before", 120)

    settings = await get_user_settings(111222)
    assert settings["timezone"] == "Europe/Moscow"
    assert settings["notify_before"] == 120


@pytest.mark.asyncio
async def test_favorite_drivers(db_session):
    """Добавление и удаление избранных пилотов."""
    from app.db import (
        add_favorite_driver,
        remove_favorite_driver,
        get_favorite_drivers,
        get_or_create_user,
    )

    await get_or_create_user(telegram_id=333444)
    await add_favorite_driver(333444, "VER")
    await add_favorite_driver(333444, "NOR")

    favs = await get_favorite_drivers(333444)
    assert "VER" in favs
    assert "NOR" in favs

    await remove_favorite_driver(333444, "VER")
    favs = await get_favorite_drivers(333444)
    assert "VER" not in favs
    assert "NOR" in favs


@pytest.mark.asyncio
async def test_favorite_teams(db_session):
    """Добавление и удаление избранных команд."""
    from app.db import (
        add_favorite_team,
        remove_favorite_team,
        get_favorite_teams,
        get_or_create_user,
    )

    await get_or_create_user(telegram_id=555666)
    await add_favorite_team(555666, "Red Bull")
    await add_favorite_team(555666, "Ferrari")

    favs = await get_favorite_teams(555666)
    assert "Red Bull" in favs
    assert "Ferrari" in favs

    await remove_favorite_team(555666, "Red Bull")
    favs = await get_favorite_teams(555666)
    assert "Red Bull" not in favs
    assert "Ferrari" in favs


@pytest.mark.asyncio
async def test_race_votes(db_session):
    """Сохранение и получение оценок гонок."""
    from app.db import save_race_vote, get_user_votes, get_or_create_user

    await get_or_create_user(telegram_id=777888)
    await save_race_vote(777888, 2024, 1, 5)
    await save_race_vote(777888, 2024, 2, 4)

    race_votes, driver_votes = await get_user_votes(777888, 2024)
    assert race_votes[1] == 5
    assert race_votes[2] == 4


@pytest.mark.asyncio
async def test_driver_votes(db_session):
    """Сохранение и получение голосов за пилота дня."""
    from app.db import save_driver_vote, get_user_votes, get_or_create_user

    await get_or_create_user(telegram_id=999000)
    await save_driver_vote(999000, 2024, 1, "VER")

    race_votes, driver_votes = await get_user_votes(999000, 2024)
    assert driver_votes[1] == "VER"


@pytest.mark.asyncio
async def test_get_race_vote_stats(db_session):
    """get_race_vote_stats возвращает средние оценки."""
    from app.db import save_race_vote, get_race_vote_stats, get_or_create_user

    await get_or_create_user(telegram_id=111333)
    await save_race_vote(111333, 2024, 1, 5)
    await save_race_vote(111333, 2024, 1, 3)

    stats = await get_race_vote_stats(2024)
    assert any(r[0] == 1 for r in stats)


@pytest.mark.asyncio
async def test_get_driver_vote_stats(db_session):
    """get_driver_vote_stats возвращает голоса за пилотов."""
    from app.db import save_driver_vote, get_driver_vote_stats, get_or_create_user

    await get_or_create_user(telegram_id=222444)
    await save_driver_vote(222444, 2024, 1, "VER")
    await save_driver_vote(222444, 2024, 2, "VER")

    stats = await get_driver_vote_stats(2024)
    assert any(d == "VER" for d, _ in stats)
