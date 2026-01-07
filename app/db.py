from pathlib import Path
from typing import List, Tuple

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"


async def init_db() -> None:
    """
    Инициализация БД: создаём таблицы, если их ещё нет.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS favorite_drivers (
                user_id INTEGER NOT NULL,
                driver_code TEXT NOT NULL,
                PRIMARY KEY (user_id, driver_code),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorite_teams (
                user_id INTEGER NOT NULL,
                constructor_name TEXT NOT NULL,
                PRIMARY KEY (user_id, constructor_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Глобально запоминаем, по какому этапу сезона уже отправили
            -- уведомление (чтобы не дублировать).
            CREATE TABLE IF NOT EXISTS notified_races (
                season INTEGER PRIMARY KEY,
                last_round_notified INTEGER NOT NULL
            );
            """
        )
        await db.commit()


async def get_or_create_user(telegram_id: int) -> int:
    """
    Возвращает id пользователя в БД, создаёт запись, если её ещё нет.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        if row:
            return row[0]

        cursor = await db.execute(
            "INSERT INTO users (telegram_id) VALUES (?)",
            (telegram_id,),
        )
        await db.commit()
        return cursor.lastrowid


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
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT driver_code FROM favorite_drivers WHERE user_id = ? ORDER BY driver_code",
            (user_id,),
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
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT constructor_name FROM favorite_teams WHERE user_id = ? ORDER BY constructor_name",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


# --- Для уведомлений --- #

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
    Получить любимых пилотов и команды по внутреннему user_id.
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


# --- Состояние уведомлений по сезонам (notification_state) --- #

async def _ensure_notification_table() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Если таблицы нет — создаём с базовыми колонками
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_state (
                season INTEGER PRIMARY KEY,
                last_notified_round INTEGER,
                last_reminded_round INTEGER
            )
            """
        )

        # 2. Проверяем, есть ли колонка last_notified_quali_round
        cursor = await db.execute("PRAGMA table_info(notification_state)")
        columns = [row[1] for row in await cursor.fetchall()]
        await cursor.close()

        if "last_notified_quali_round" not in columns:
            # 3. Добавляем недостающий столбец
            await db.execute(
                "ALTER TABLE notification_state "
                "ADD COLUMN last_notified_quali_round INTEGER"
            )

        await db.commit()


# Разрешенные имена колонок для защиты от SQL injection
_ALLOWED_COLUMNS = {
    "last_reminded_round",
    "last_notified_round",
    "last_notified_quali_round",
}


async def _get_round_value(season: int, column: str) -> int | None:
    """
    Получить значение раунда из указанной колонки.
    
    Args:
        season: Год сезона
        column: Имя колонки (должно быть в _ALLOWED_COLUMNS)
    
    Returns:
        Значение раунда или None
    """
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Недопустимое имя колонки: {column}")
    
    await _ensure_notification_table()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f'SELECT "{column}" FROM notification_state WHERE season = ?',
            (season,),
        )
        row = await cursor.fetchone()
        await cursor.close()

        if row is None:
            return None
        return row[0]


async def _set_round_value(season: int, column: str, round_number: int) -> None:
    """
    Установить значение раунда в указанную колонку.
    
    Args:
        season: Год сезона
        column: Имя колонки (должно быть в _ALLOWED_COLUMNS)
        round_number: Номер раунда
    """
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Недопустимое имя колонки: {column}")
    
    await _ensure_notification_table()
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


# --- Напоминание за сутки до гонки --- #

async def get_last_reminded_round(season: int) -> int | None:
    return await _get_round_value(season, "last_reminded_round")


async def set_last_reminded_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_reminded_round", round_number)


# --- Уведомление после гонки --- #

async def get_last_notified_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_round")


async def set_last_notified_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_notified_round", round_number)


# --- Уведомление после квалификации --- #

async def get_last_notified_quali_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_quali_round")


async def set_last_notified_quali_round(season: int, round_number: int) -> None:
    await _set_round_value(season, "last_notified_quali_round", round_number)


async def clear_all_favorites(telegram_id: int) -> None:
    """
    Удаляет всех любимых пилотов и команды для данного пользователя.
    """
    user_id = await get_or_create_user(telegram_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorite_drivers WHERE user_id = ?",
            (user_id,),
        )
        await db.execute(
            "DELETE FROM favorite_teams WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
