from pathlib import Path
from typing import List, Tuple, Any
import logging
import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"
logger = logging.getLogger(__name__)

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")

        # 1. Таблица пользователей
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                timezone TEXT DEFAULT 'Europe/Moscow',
                notify_before INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Миграция колонок users
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        if "timezone" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Europe/Moscow'")
        if "notify_before" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN notify_before INTEGER DEFAULT 60")

        # 2. Таблицы избранного
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS favorite_drivers (
                user_id INTEGER NOT NULL,
                driver_code TEXT NOT NULL,
                PRIMARY KEY (user_id, driver_code),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS favorite_teams (
                user_id INTEGER NOT NULL,
                constructor_name TEXT NOT NULL,
                PRIMARY KEY (user_id, constructor_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        # 3. Таблица уведомлений
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_state (
                season INTEGER PRIMARY KEY,
                last_notified_round INTEGER,
                last_reminded_round INTEGER,
                last_notified_quali_round INTEGER
            );
            """
        )
        async with db.execute("PRAGMA table_info(notification_state)") as cursor:
            cols = [row[1] for row in await cursor.fetchall()]
        if "last_notified_quali_round" not in cols:
            await db.execute("ALTER TABLE notification_state ADD COLUMN last_notified_quali_round INTEGER")

        await db.commit()


async def get_or_create_user(telegram_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        if row: return row[0]
        cursor = await db.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
        await db.commit()
        return cursor.lastrowid

# --- НАСТРОЙКИ (Этого не хватало!) ---
async def get_user_settings(telegram_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT timezone, notify_before FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        if row:
            return {"timezone": row[0] or "Europe/Moscow", "notify_before": row[1] if row[1] is not None else 60}
        return {"timezone": "Europe/Moscow", "notify_before": 60}

async def update_user_setting(telegram_id: int, key: str, value: Any) -> None:
    if key not in {"timezone", "notify_before"}: return
    await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, telegram_id))
        await db.commit()

# --- Избранное (пилоты) ---
async def add_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO favorite_drivers (user_id, driver_code) VALUES (?, ?)", (user_id, driver_code))
        await db.commit()

async def remove_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM favorite_drivers WHERE user_id = ? AND driver_code = ?", (user_id, driver_code))
        await db.commit()

async def get_favorite_drivers(telegram_id: int) -> List[str]:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = ? ORDER BY driver_code", (user_id,))
        return [r[0] for r in await cursor.fetchall()]

# --- Избранное (команды) ---
async def add_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO favorite_teams (user_id, constructor_name) VALUES (?, ?)", (user_id, constructor_name))
        await db.commit()

async def remove_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM favorite_teams WHERE user_id = ? AND constructor_name = ?", (user_id, constructor_name))
        await db.commit()

async def get_favorite_teams(telegram_id: int) -> List[str]:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT constructor_name FROM favorite_teams WHERE user_id = ? ORDER BY constructor_name", (user_id,))
        return [r[0] for r in await cursor.fetchall()]

# --- Уведомления ---
async def get_all_users_with_favorites() -> List[Tuple[int, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT telegram_id, id FROM users") # Упростил для надежности
        return await cursor.fetchall()

async def get_favorites_for_user_id(user_db_id: int) -> Tuple[List[str], List[str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = ?", (user_db_id,))
        drivers = [r[0] for r in await cursor.fetchall()]
        cursor = await db.execute("SELECT constructor_name FROM favorite_teams WHERE user_id = ?", (user_db_id,))
        teams = [r[0] for r in await cursor.fetchall()]
    return drivers, teams

async def _get_round_value(season: int, column: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(f'SELECT "{column}" FROM notification_state WHERE season = ?', (season,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def _set_round_value(season: int, column: str, value: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'INSERT INTO notification_state(season, "{column}") VALUES(?, ?) ON CONFLICT(season) DO UPDATE SET "{column}"=excluded."{column}"', (season, value))
        await db.commit()

async def get_last_reminded_round(season: int) -> int | None: return await _get_round_value(season, "last_reminded_round")
async def set_last_reminded_round(season: int, r: int) -> None: await _set_round_value(season, "last_reminded_round", r)
async def get_last_notified_round(season: int) -> int | None: return await _get_round_value(season, "last_notified_round")
async def set_last_notified_round(season: int, r: int) -> None: await _set_round_value(season, "last_notified_round", r)
async def get_last_notified_quali_round(season: int) -> int | None: return await _get_round_value(season, "last_notified_quali_round")
async def set_last_notified_quali_round(season: int, r: int) -> None: await _set_round_value(season, "last_notified_quali_round", r)