import logging
from pathlib import Path
from typing import List, Tuple, Any

import aiosqlite

# Путь к БД: на уровень выше от папки app, файл bot.db
DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"

# Настраиваем простейший логгер для БД
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """
    Инициализация БД.
    Создает таблицы и проводит миграции (добавляет новые колонки),
    если их нет.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Включаем внешние ключи
        await db.execute("PRAGMA foreign_keys = ON;")

        # 2. Таблица пользователей
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

        # 3. Таблицы избранного
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

        # 4. Таблица состояния уведомлений (системная)
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

        # --- МИГРАЦИИ (Добавление колонок в старые базы) ---

        # Проверяем колонки в users
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

        # Если старая база, добавляем timezone
        if "timezone" not in columns:
            logger.info("Migrating DB: Adding 'timezone' column to users")
            await db.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Europe/Moscow'")

        # Если старая база, добавляем notify_before
        if "notify_before" not in columns:
            logger.info("Migrating DB: Adding 'notify_before' column to users")
            await db.execute("ALTER TABLE users ADD COLUMN notify_before INTEGER DEFAULT 60")

        # Проверяем колонки в notification_state
        async with db.execute("PRAGMA table_info(notification_state)") as cursor:
            notif_columns = [row[1] for row in await cursor.fetchall()]

        if "last_notified_quali_round" not in notif_columns:
            logger.info("Migrating DB: Adding 'last_notified_quali_round' to notification_state")
            await db.execute("ALTER TABLE notification_state ADD COLUMN last_notified_quali_round INTEGER")

        await db.commit()


async def get_or_create_user(telegram_id: int) -> int:
    """
    Возвращает внутренний id пользователя (PK).
    Если пользователя нет, создает его с дефолтными настройками.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Пытаемся найти
        cursor = await db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()

        if row:
            return row[0]

        # Создаем нового
        cursor = await db.execute(
            "INSERT INTO users (telegram_id) VALUES (?)",
            (telegram_id,)
        )
        await db.commit()
        return cursor.lastrowid


# --- Работа с настройками (Новое) --- #

async def get_user_settings(telegram_id: int) -> dict:
    """
    Получает настройки пользователя.
    Возвращает dict: {'timezone': str, 'notify_before': int}
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Используем LEFT JOIN или просто SELECT. 
        # Если юзера нет, get_or_create_user внутри логики бота обычно вызывается раньше,
        # но для надежности можем вернуть дефолт, если запись не найдена.
        cursor = await db.execute(
            "SELECT timezone, notify_before FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        row = await cursor.fetchone()

        if row:
            return {
                "timezone": row[0] if row[0] else "Europe/Moscow",
                "notify_before": row[1] if row[1] is not None else 60
            }

        # Если вдруг юзера нет в базе (редкий кейс), возвращаем дефолт
        return {"timezone": "Europe/Moscow", "notify_before": 60}


async def update_user_setting(telegram_id: int, key: str, value: Any) -> None:
    """
    Обновляет одну настройку пользователя.
    key: 'timezone' | 'notify_before'
    """
    allowed_keys = {"timezone", "notify_before"}
    if key not in allowed_keys:
        logger.error(f"Attempt to update invalid setting key: {key}")
        return

    # Сначала убеждаемся, что юзер существует
    await get_or_create_user(telegram_id)

    async with aiosqlite.connect(DB_PATH) as db:
        # f-строка безопасна здесь, так как мы проверили key по белому списку allowed_keys
        await db.execute(
            f"UPDATE users SET {key} = ? WHERE telegram_id = ?",
            (value, telegram_id)
        )
        await db.commit()


# --- Работа с любимыми пилотами --- #

async def add_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorite_drivers (user_id, driver_code) VALUES (?, ?)",
            (user_id, driver_code),
        )
        await db.commit()


async def remove_favorite_driver(telegram_id: int, driver_code: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorite_drivers WHERE user_id = ? AND driver_code = ?",
            (user_id, driver_code),
        )
        await db.commit()


async def get_favorite_drivers(telegram_id: int) -> List[str]:
    # Оптимизация: один запрос с JOIN вместо двух (get_or_create + select)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT fd.driver_code 
            FROM favorite_drivers fd
            JOIN users u ON u.id = fd.user_id
            WHERE u.telegram_id = ?
            ORDER BY fd.driver_code
            """,
            (telegram_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


# --- Работа с любимыми командами --- #

async def add_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorite_teams (user_id, constructor_name) VALUES (?, ?)",
            (user_id, constructor_name),
        )
        await db.commit()


async def remove_favorite_team(telegram_id: int, constructor_name: str) -> None:
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorite_teams WHERE user_id = ? AND constructor_name = ?",
            (user_id, constructor_name),
        )
        await db.commit()


async def get_favorite_teams(telegram_id: int) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT ft.constructor_name 
            FROM favorite_teams ft
            JOIN users u ON u.id = ft.user_id
            WHERE u.telegram_id = ?
            ORDER BY ft.constructor_name
            """,
            (telegram_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def clear_all_favorites(telegram_id: int) -> None:
    """
    Удаляет все подписки пользователя.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем id, чтобы удалить по ключу
        cursor = await db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        if not row:
            return
        user_id = row[0]

        await db.execute("DELETE FROM favorite_drivers WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM favorite_teams WHERE user_id = ?", (user_id,))
        await db.commit()


# --- Для системы уведомлений (mass sending) --- #

async def get_all_users_with_favorites() -> List[Tuple[int, int]]:
    """
    Возвращает список (telegram_id, user_id) всех пользователей,
    у которых есть хотя бы один любимый пилот или команда.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT DISTINCT u.telegram_id, u.id
            FROM users u
            LEFT JOIN favorite_drivers fd ON fd.user_id = u.id
            LEFT JOIN favorite_teams ft ON ft.user_id = u.id
            WHERE fd.user_id IS NOT NULL OR ft.user_id IS NOT NULL
            """
        )
        return await cursor.fetchall()


async def get_favorites_for_user_id(user_db_id: int) -> Tuple[List[str], List[str]]:
    """
    Получить любимых пилотов и команды по внутреннему user_id (для рассылки).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT driver_code FROM favorite_drivers WHERE user_id = ?",
            (user_db_id,),
        )
        drivers = [r[0] for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT constructor_name FROM favorite_teams WHERE user_id = ?",
            (user_db_id,),
        )
        teams = [r[0] for r in await cursor.fetchall()]

    return drivers, teams


# --- Состояние глобальных уведомлений (Notification State) --- #

_ALLOWED_COLUMNS = {
    "last_reminded_round",
    "last_notified_round",
    "last_notified_quali_round",
}


async def _get_round_value(season: int, column: str) -> int | None:
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column: {column}")

    # Больше не вызываем ensure_table здесь, так как init_db гарантирует структуру
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f'SELECT "{column}" FROM notification_state WHERE season = ?',
            (season,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def _set_round_value(season: int, column: str, round_number: int) -> None:
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column: {column}")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""
            INSERT INTO notification_state(season, "{column}")
            VALUES(?, ?)
            ON CONFLICT(season) DO UPDATE SET
                "{column}" = excluded."{column}"
            """,
            (season, round_number),
        )
        await db.commit()


# Обертки для удобства

async def get_last_reminded_round(season: int) -> int | None:
    return await _get_round_value(season, "last_reminded_round")


async def set_last_reminded_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_reminded_round", round_number)


async def get_last_notified_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_round")


async def set_last_notified_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_notified_round", round_number)


async def get_last_notified_quali_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_quali_round")


async def set_last_notified_quali_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_notified_quali_round", round_number)