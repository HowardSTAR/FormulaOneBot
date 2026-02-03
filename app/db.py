import logging
import aiosqlite
from pathlib import Path
from typing import List, Tuple, Any, Optional

# Настройка путей и логгера
DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Открывает соединение и включает WAL-режим для скорости."""
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.db_path)
            # Включаем доступ к полям по именам (dict-like access)
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA foreign_keys = ON;")
            # WAL-режим критически важен для конкурентной записи и чтения
            await self.conn.execute("PRAGMA journal_mode = WAL;")
            await self.conn.commit()
            logger.info("Database connection established (WAL mode enabled).")

    async def close(self):
        """Закрывает соединение."""
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Database connection closed.")

    async def init_tables(self):
        """Создает таблицы (миграции)."""
        if not self.conn:
            await self.connect()

        # 1. Таблица пользователей
        await self.conn.execute(
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

        # Проверка и добавление колонок (миграции "на лету")
        async with self.conn.execute("PRAGMA table_info(users)") as cursor:
            columns = [row['name'] for row in await cursor.fetchall()]

        if "timezone" not in columns:
            await self.conn.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Europe/Moscow'")
        if "notify_before" not in columns:
            await self.conn.execute("ALTER TABLE users ADD COLUMN notify_before INTEGER DEFAULT 60")

        # 2. Таблицы избранного
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorite_drivers (
                user_id INTEGER NOT NULL,
                driver_code TEXT NOT NULL,
                PRIMARY KEY (user_id, driver_code),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        await self.conn.execute(
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
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_state (
                season INTEGER PRIMARY KEY,
                last_notified_round INTEGER,
                last_reminded_round INTEGER,
                last_notified_quali_round INTEGER
            );
            """
        )
        async with self.conn.execute("PRAGMA table_info(notification_state)") as cursor:
            cols = [row['name'] for row in await cursor.fetchall()]
        if "last_notified_quali_round" not in cols:
            await self.conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_quali_round INTEGER")

        await self.conn.commit()


# --- Создаем глобальный экземпляр БД ---
db = Database(DB_PATH)


# --- Хелперы (теперь используют db.conn) ---

async def get_or_create_user(telegram_id: int) -> int:
    # Важно: всегда проверяем, есть ли соединение (на случай вызова вне контекста бота)
    if not db.conn: await db.connect()

    async with db.conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return row['id']  # Обращаемся по имени колонки благодаря row_factory

    # Если не найден
    cursor = await db.conn.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
    await db.conn.commit()
    return cursor.lastrowid


async def get_user_settings(telegram_id: int) -> dict:
    if not db.conn: await db.connect()
    async with db.conn.execute("SELECT timezone, notify_before FROM users WHERE telegram_id = ?",
                               (telegram_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return {
                "timezone": row['timezone'] or "Europe/Moscow",
                "notify_before": row['notify_before'] if row['notify_before'] is not None else 60
            }
        return {"timezone": "Europe/Moscow", "notify_before": 60}


async def update_user_setting(telegram_id: int, key: str, value: Any) -> None:
    if key not in {"timezone", "notify_before"}: return
    await get_or_create_user(telegram_id)  # Убедимся, что юзер создан

    # ВНИМАНИЕ: f-строка безопасна только потому, что мы проверили key выше
    await db.conn.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, telegram_id))
    await db.conn.commit()


# --- Избранное (пилоты) ---
async def add_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute("INSERT OR IGNORE INTO favorite_drivers (user_id, driver_code) VALUES (?, ?)",
                          (user_id, driver_code))
    await db.conn.commit()


async def remove_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute("DELETE FROM favorite_drivers WHERE user_id = ? AND driver_code = ?", (user_id, driver_code))
    await db.conn.commit()


async def get_favorite_drivers(telegram_id: int) -> List[str]:
    user_id = await get_or_create_user(telegram_id)
    async with db.conn.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = ? ORDER BY driver_code",
                               (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [r['driver_code'] for r in rows]


# --- Избранное (команды) ---
async def add_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute("INSERT OR IGNORE INTO favorite_teams (user_id, constructor_name) VALUES (?, ?)",
                          (user_id, constructor_name))
    await db.conn.commit()


async def remove_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute("DELETE FROM favorite_teams WHERE user_id = ? AND constructor_name = ?",
                          (user_id, constructor_name))
    await db.conn.commit()


async def get_favorite_teams(telegram_id: int) -> List[str]:
    user_id = await get_or_create_user(telegram_id)
    async with db.conn.execute(
            "SELECT constructor_name FROM favorite_teams WHERE user_id = ? ORDER BY constructor_name",
            (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [r['constructor_name'] for r in rows]


# --- Уведомления ---
async def get_all_users_with_favorites() -> List[Tuple[int, int]]:
    if not db.conn: await db.connect()
    # Возвращаем список (telegram_id, db_id)
    async with db.conn.execute("SELECT DISTINCT telegram_id, id FROM users") as cursor:
        rows = await cursor.fetchall()
        return [(r['telegram_id'], r['id']) for r in rows]


async def get_favorites_for_user_id(user_db_id: int) -> Tuple[List[str], List[str]]:
    if not db.conn: await db.connect()
    async with db.conn.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = ?", (user_db_id,)) as cursor:
        drivers = [r['driver_code'] for r in await cursor.fetchall()]
    async with db.conn.execute("SELECT constructor_name FROM favorite_teams WHERE user_id = ?",
                               (user_db_id,)) as cursor:
        teams = [r['constructor_name'] for r in await cursor.fetchall()]
    return drivers, teams


async def _get_round_value(season: int, column: str) -> int | None:
    if not db.conn: await db.connect()
    # f-строка безопасна, т.к. column передается внутри кода, а не от юзера
    async with db.conn.execute(f'SELECT "{column}" FROM notification_state WHERE season = ?', (season,)) as cursor:
        row = await cursor.fetchone()
        return row[column] if row else None


async def _set_round_value(season: int, column: str, value: int) -> None:
    if not db.conn: await db.connect()
    await db.conn.execute(
        f'INSERT INTO notification_state(season, "{column}") VALUES(?, ?) ON CONFLICT(season) DO UPDATE SET "{column}"=excluded."{column}"',
        (season, value))
    await db.conn.commit()


# Алиасы (оставил как было для совместимости с app/handlers/races.py)
async def get_last_reminded_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                            "last_reminded_round")


async def set_last_reminded_round(season: int, r: int) -> None: await _set_round_value(season, "last_reminded_round", r)


async def get_last_notified_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                            "last_notified_round")


async def set_last_notified_round(season: int, r: int) -> None: await _set_round_value(season, "last_notified_round", r)


async def get_last_notified_quali_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                                  "last_notified_quali_round")


async def set_last_notified_quali_round(season: int, r: int) -> None: await _set_round_value(season,
                                                                                             "last_notified_quali_round",
                                                                                             r)