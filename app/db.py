import logging
import aiosqlite
from pathlib import Path
from typing import List, Tuple, Any, Optional

# Настройка путей и логгера
# 1. Защита от "баз-двойников": вычисляем абсолютный путь к корню проекта
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "data"

# Гарантируем, что папка data существует
DB_DIR.mkdir(exist_ok=True)

# Единый путь для всех компонентов системы
DB_PATH = DB_DIR / "bot.db"

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

        try:
            await self.conn.execute("ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 0")
            await self.conn.commit()
            logger.info("Миграция успешна: колонка notifications_enabled добавлена в старую базу.")
        except aiosqlite.OperationalError as e:
            # Если база уже была обновлена ранее, просто игнорируем ошибку
            if "duplicate column name" in str(e).lower():
                pass
            else:
                logger.error(f"Ошибка при миграции: {e}")

        await self.conn.commit()


# --- Создаем глобальный экземпляр БД ---
db = Database(DB_PATH)


# --- Хелперы (теперь используют db.conn) ---

async def get_or_create_user(telegram_id) -> int:
    """Ищет юзера по telegram_id. Если нет - создает."""
    if not db.conn: await db.connect()

    # Защита от Web API (которое шлет ID как строку)
    tg_id = int(telegram_id)

    # Ищем строго по telegram_id
    async with db.conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return row['id'] if hasattr(row, 'keys') else row[0]

    # Создаем, заполняя именно telegram_id
    await db.conn.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (tg_id,))
    await db.conn.commit()

    # Возвращаем внутренний id базы
    async with db.conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return row['id'] if hasattr(row, 'keys') else row[0]
        return 0


async def get_user_settings(telegram_id) -> dict:
    if not db.conn: await db.connect()

    tg_id = int(telegram_id)
    await get_or_create_user(tg_id)

    # Ищем по telegram_id и достаем новый столбец notifications_enabled
    async with db.conn.execute("SELECT timezone, notify_before, notifications_enabled FROM users WHERE telegram_id = ?",
                               (tg_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            keys = row.keys() if hasattr(row, 'keys') else []
            return {
                "timezone": row['timezone'] if 'timezone' in keys else row[0] or "Europe/Moscow",
                "notify_before": row['notify_before'] if 'notify_before' in keys else (
                    row[1] if row[1] is not None else 60),
                "notifications_enabled": bool(
                    row['notifications_enabled'] if 'notifications_enabled' in keys else row[2])
            }
        return {"timezone": "Europe/Moscow", "notify_before": 60, "notifications_enabled": False}


async def update_user_setting(telegram_id, key: str, value: Any) -> None:
    if key not in {"timezone", "notify_before", "notifications_enabled"}:
        return

    tg_id = int(telegram_id)
    await get_or_create_user(tg_id)

    # Обновляем строго по telegram_id
    await db.conn.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, tg_id))
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


async def get_all_users() -> list[int]:
    """Получает список ID всех пользователей из таблицы users для тихой рассылки."""
    if db.conn is None:
        logger.error("Критическая ошибка: соединение с БД не установлено (db.conn is None)")
        return []

    try:
        # Используем точные имена из вашего PRAGMA: telegram_id и users
        async with db.conn.execute("SELECT telegram_id FROM users") as cursor:
            rows = await cursor.fetchall()

            # Извлекаем данные по ключу telegram_id
            return [row["telegram_id"] for row in rows]

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей из таблицы users: {e}")
        return []


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