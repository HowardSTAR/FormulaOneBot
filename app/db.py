import logging
import os
import asyncio
import json
import aiosqlite
from pathlib import Path
from typing import List, Tuple, Any, Optional
from app.race_rules import SUPPORTED_TRACK_IDS, validate_race_path

# Настройка путей и логгера
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)

# DATABASE_PATH — опционально, иначе всегда data/bot.db
_raw = os.environ.get("DATABASE_PATH")
if _raw:
    DB_PATH = Path(_raw).resolve()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    DB_PATH = (DB_DIR / "bot.db").resolve()

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self.write_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()

    async def connect(self):
        """Открывает соединение и включает WAL-режим для скорости."""
        async with self._connection_lock:
            if self.conn is not None:
                return
            connection = await aiosqlite.connect(self.db_path)
            # Включаем доступ к полям по именам (dict-like access)
            connection.row_factory = aiosqlite.Row
            # bot и web работают с одним SQLite-файлом в разных контейнерах.
            # Вместо мгновенного `database is locked` ждём освобождения записи.
            try:
                await connection.execute("PRAGMA foreign_keys = ON;")
                await connection.execute("PRAGMA busy_timeout = 30000;")
                await connection.execute("PRAGMA journal_mode = WAL;")
                await connection.commit()
            except BaseException:
                await connection.close()
                raise
            # Publish only a fully configured connection, not a half-open one.
            self.conn = connection
            logger.info("Database connection established (WAL mode enabled).")

    async def close(self):
        """Закрывает соединение."""
        async with self._connection_lock:
            if self.conn:
                try:
                    await self.conn.close()
                finally:
                    self.conn = None
                logger.info("Database connection closed.")

    async def init_tables(self):
        """Compatibility entry point for explicit migrations and isolated tests."""
        from app.migrations import migrate
        await self.connect()
        await migrate(self)

    async def initialize(self):
        """Production requires migration first; local development can bootstrap."""
        await self.connect()
        if os.getenv('DATABASE_AUTO_MIGRATE', 'true').lower() in {'1', 'true', 'yes'}:
            await self.init_tables()
        else:
            from app.migrations import require_current
            await require_current(self.conn)


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
    async with db.conn.execute("SELECT timezone, notify_before, notifications_enabled, reminder_sessions, results_spoiler, notify_before_mask FROM users WHERE telegram_id = ?",
                               (tg_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            from app.session_reminders import reminder_intervals
            keys = row.keys() if hasattr(row, 'keys') else []
            return {
                "notify_before_minutes": reminder_intervals(row[5], row[1]),
                "reminder_sessions": row[3],
                "results_spoiler": bool(row[4]),
                "timezone": row['timezone'] if 'timezone' in keys else row[0] or "Europe/Moscow",
                "notify_before": row['notify_before'] if 'notify_before' in keys else (
                    row[1] if row[1] is not None else 60),
                "notifications_enabled": bool(
                    row['notifications_enabled'] if 'notifications_enabled' in keys else row[2])
            }
        return {"timezone": "Europe/Moscow", "notify_before": 60, "notify_before_minutes": [60], "notifications_enabled": False, "reminder_sessions": 31, "results_spoiler": False}


async def toggle_notification_interval(telegram_id: int, minutes: int) -> list[int]:
    from app.session_reminders import INTERVAL_BITS, reminder_intervals
    if type(minutes) is not int or minutes not in INTERVAL_BITS:
        raise ValueError("Invalid reminder interval")
    await get_or_create_user(telegram_id)
    async with db.write_lock:
        # One SQL update, not read-modify-write: bot/web use separate processes
        # and their Python locks alone cannot protect the shared SQLite file.
        cases = " ".join(f"WHEN {value} THEN {bit}" for value, bit in INTERVAL_BITS.items())
        current = f"COALESCE(notify_before_mask, CASE notify_before {cases} ELSE 4 END)"
        cursor = await db.conn.execute(
            f"UPDATE users SET notify_before_mask=({current} | ?) - ({current} & ?),updated_at=CURRENT_TIMESTAMP WHERE telegram_id=? RETURNING notify_before_mask",
            (INTERVAL_BITS[minutes], INTERVAL_BITS[minutes], telegram_id))
        row = await cursor.fetchone()
        await cursor.close()
        await db.conn.commit()
    return reminder_intervals(row[0])


async def update_user_setting(telegram_id, key: str, value: Any) -> None:
    if key not in {"timezone", "notify_before", "notifications_enabled", "reminder_sessions", "results_spoiler"}:
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
    """Устаревший: возвращает (telegram_id, user_id). Используйте get_users_favorites_for_notifications."""
    if not db.conn: await db.connect()
    async with db.conn.execute("SELECT DISTINCT telegram_id, id FROM users WHERE telegram_id IS NOT NULL") as cursor:
        rows = await cursor.fetchall()
        return [(r['telegram_id'], r['id']) for r in rows]


async def get_users_favorites_for_notifications(notifications_only: bool = True) -> dict:
    """
    Возвращает {telegram_id: {"drivers": [...], "teams": [...]}} для пользователей с избранным.
    Используется для рассылки результатов гонок и квалификации.
    """
    if not db.conn: await db.connect()
    # The legacy flag controls Telegram sound, never membership of a broadcast.
    notif_filter = " AND u.archived_at IS NULL"
    result: dict = {}
    async with db.conn.execute(
        "SELECT u.telegram_id, fd.driver_code FROM users u "
        "JOIN favorite_drivers fd ON fd.user_id = u.id WHERE u.telegram_id IS NOT NULL"
        f"{notif_filter}"
    ) as cursor:
        async for row in cursor:
            tg_id = row['telegram_id']
            if tg_id not in result:
                result[tg_id] = {"drivers": [], "teams": []}
            result[tg_id]["drivers"].append(str(row['driver_code']).upper())
    async with db.conn.execute(
        "SELECT u.telegram_id, ft.constructor_name FROM users u "
        "JOIN favorite_teams ft ON ft.user_id = u.id WHERE u.telegram_id IS NOT NULL"
        f"{notif_filter}"
    ) as cursor:
        async for row in cursor:
            tg_id = row['telegram_id']
            if tg_id not in result:
                result[tg_id] = {"drivers": [], "teams": []}
            result[tg_id]["teams"].append(str(row['constructor_name']))
    return result


async def get_favorites_for_user_id(user_db_id: int) -> Tuple[List[str], List[str]]:
    if not db.conn: await db.connect()
    async with db.conn.execute("SELECT driver_code FROM favorite_drivers WHERE user_id = ?", (user_db_id,)) as cursor:
        drivers = [r['driver_code'] for r in await cursor.fetchall()]
    async with db.conn.execute("SELECT constructor_name FROM favorite_teams WHERE user_id = ?",
                               (user_db_id,)) as cursor:
        teams = [r['constructor_name'] for r in await cursor.fetchall()]
    return drivers, teams


async def _get_round_value(season: int, column: str) -> int | None:
    # f-строка безопасна, т.к. column передается внутри кода, а не от юзера
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(f'SELECT "{column}" FROM notification_state WHERE season = ?', (season,)) as cursor:
            row = await cursor.fetchone()
            return row[column] if row else None


async def _set_round_value(season: int, column: str, value: int) -> None:
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute(
            f'INSERT INTO notification_state(season, "{column}") VALUES(?, ?) ON CONFLICT(season) DO UPDATE SET "{column}"=excluded."{column}"',
            (season, value))
        await conn.commit()


async def get_all_users() -> list[int]:
    """Получает список ID всех пользователей из таблицы users для тихой рассылки."""
    if db.conn is None:
        logger.error("Критическая ошибка: соединение с БД не установлено (db.conn is None)")
        return []

    try:
        # Используем точные имена из вашего PRAGMA: telegram_id и users
        async with db.conn.execute("SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL") as cursor:
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


async def was_reminder_sent(telegram_id: int, season: int, round_num: int, is_quali: bool, notify_before_min: int) -> bool:
    """Проверяет, отправляли ли уже напоминание этому пользователю для данного этапа/типа/за сколько минут."""
    q = (
        "SELECT 1 FROM event_reminder_sent "
        "WHERE telegram_id = ? AND season = ? AND round = ? AND is_quali = ? AND notify_before_min = ?"
    )
    # A receipt must see the committed state, even if the shared connection has
    # an older transaction open in another bot task.
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        async with conn.execute(q, (telegram_id, season, round_num, 1 if is_quali else 0, notify_before_min)) as cur:
            row = await cur.fetchone()
    return row is not None


async def set_reminder_sent(telegram_id: int, season: int, round_num: int, is_quali: bool, notify_before_min: int) -> None:
    """Отмечает, что напоминание этому пользователю для данного этапа/типа/за сколько минут отправлено."""
    # Keep delivery receipts independent of unrelated work on db.conn. A
    # pending read transaction on that shared connection cannot be upgraded to
    # a writer after a different connection commits (SQLITE_BUSY_SNAPSHOT).
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute(
            "INSERT OR IGNORE INTO event_reminder_sent (telegram_id, season, round, is_quali, notify_before_min) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, season, round_num, 1 if is_quali else 0, notify_before_min),
        )
        await conn.commit()


async def get_last_notified_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                            "last_notified_round")


async def set_last_notified_round(season: int, r: int) -> None: await _set_round_value(season, "last_notified_round", r)


async def get_last_notified_recap_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_recap_round")


async def set_last_notified_recap_round(season: int, r: int) -> None:
    await _set_round_value(season, "last_notified_recap_round", r)


async def get_last_notified_quali_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                                  "last_notified_quali_round")


async def set_last_notified_quali_round(season: int, r: int) -> None: await _set_round_value(season,
                                                                                             "last_notified_quali_round",
                                                                                             r)


async def get_last_notified_sprint_quali_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_sprint_quali_round")


async def set_last_notified_sprint_quali_round(season: int, r: int) -> None:
    await _set_round_value(season, "last_notified_sprint_quali_round", r)


async def get_last_notified_sprint_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_sprint_round")


async def set_last_notified_sprint_round(season: int, r: int) -> None:
    await _set_round_value(season, "last_notified_sprint_round", r)


async def get_last_notified_voting_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_voting_round")


async def set_last_notified_voting_round(season: int, r: int) -> None:
    await _set_round_value(season, "last_notified_voting_round", r)


async def get_last_notified_voting_invite_round(season: int) -> int | None:
    return await _get_round_value(season, "last_notified_voting_invite_round")


async def set_last_notified_voting_invite_round(season: int, r: int) -> None:
    await _set_round_value(season, "last_notified_voting_invite_round", r)


# --- Голосования (гонка 1–5, пилот дня) ---

async def save_race_vote(telegram_id: int, season: int, round_num: int, rating: int) -> None:
    """Сохраняет оценку гонки (1–5)."""
    if not db.conn: await db.connect()
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute(
        "INSERT OR REPLACE INTO race_votes (user_id, season, round, rating) VALUES (?, ?, ?, ?)",
        (user_id, season, round_num, rating),
    )
    await db.conn.commit()


async def save_driver_vote(telegram_id: int, season: int, round_num: int, driver_code: str) -> None:
    """Сохраняет голос за пилота дня."""
    if not db.conn: await db.connect()
    user_id = await get_or_create_user(telegram_id)
    await db.conn.execute(
        "INSERT OR REPLACE INTO driver_votes (user_id, season, round, driver_code) VALUES (?, ?, ?, ?)",
        (user_id, season, round_num, driver_code.upper()),
    )
    await db.conn.commit()


async def get_user_votes(telegram_id: int, season: int) -> Tuple[dict, dict]:
    """Возвращает (race_votes: {round: rating}, driver_votes: {round: driver_code})."""
    if not db.conn: await db.connect()
    user_id = await get_or_create_user(telegram_id)
    race_votes = {}
    async with db.conn.execute(
        "SELECT round, rating FROM race_votes WHERE user_id = ? AND season = ?",
        (user_id, season),
    ) as cursor:
        for row in await cursor.fetchall():
            race_votes[row["round"]] = row["rating"]
    driver_votes = {}
    async with db.conn.execute(
        "SELECT round, driver_code FROM driver_votes WHERE user_id = ? AND season = ?",
        (user_id, season),
    ) as cursor:
        for row in await cursor.fetchall():
            driver_votes[row["round"]] = row["driver_code"]
    return race_votes, driver_votes


async def get_race_vote_stats(season: int, until_day: int = 10) -> List[Tuple[int, float, int]]:
    """
    Средние оценки гонок за сезон.
    until_day: обновлять статистику до N-го числа месяца (по умолчанию 10).
    Возвращает [(round, avg_rating, count), ...] отсортировано по round.
    """
    if not db.conn: await db.connect()
    async with db.conn.execute(
        """
        SELECT round, AVG(rating) as avg_rating, COUNT(*) as cnt
        FROM race_votes WHERE season = ?
        GROUP BY round
        ORDER BY round
        """,
        (season,),
    ) as cursor:
        return [(r["round"], round(r["avg_rating"], 2), r["cnt"]) for r in await cursor.fetchall()]


async def get_race_avg_for_round(season: int, round_num: int) -> Tuple[float | None, int]:
    """Средняя оценка гонки по этапу: (avg, count) или (None, 0)."""
    if not db.conn: await db.connect()
    async with db.conn.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(*) as cnt FROM race_votes WHERE season = ? AND round = ?",
        (season, round_num),
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["cnt"] > 0:
            return (round(row["avg_rating"], 2), row["cnt"])
        return (None, 0)


async def get_driver_vote_stats(season: int) -> List[Tuple[str, int]]:
    """Голоса за пилотов дня за сезон: [(driver_code, count), ...] по убыванию count."""
    if not db.conn: await db.connect()
    async with db.conn.execute(
        """
        SELECT driver_code, COUNT(*) as cnt
        FROM driver_votes WHERE season = ?
        GROUP BY driver_code
        ORDER BY cnt DESC
        """,
        (season,),
    ) as cursor:
        return [(r["driver_code"], r["cnt"]) for r in await cursor.fetchall()]


async def get_driver_vote_round_winners(season: int) -> List[Tuple[int, str, int]]:
    """Победители голосования «Пилот дня» по этапам.

    Возвращает по одной записи на этап: ``(round, driver_code, count)``.
    При равенстве голосов результат стабилен: выигрывает код, который идёт
    первым по алфавиту.
    """
    if not db.conn:
        await db.connect()
    async with db.conn.execute(
        """
        SELECT round, driver_code, COUNT(*) AS cnt
        FROM driver_votes
        WHERE season = ?
        GROUP BY round, driver_code
        ORDER BY round ASC, cnt DESC, driver_code ASC
        """,
        (season,),
    ) as cursor:
        rows = await cursor.fetchall()

    winners: List[Tuple[int, str, int]] = []
    seen_rounds: set[int] = set()
    for row in rows:
        round_num = int(row["round"])
        if round_num in seen_rounds:
            continue
        seen_rounds.add(round_num)
        winners.append((round_num, str(row["driver_code"]), int(row["cnt"])))
    return winners


async def get_driver_vote_winner(season: int, round_num: int) -> Tuple[str | None, int]:
    """Пилот дня по этапу: (driver_code, count) или (None, 0) если нет голосов."""
    if not db.conn: await db.connect()
    async with db.conn.execute(
        """
        SELECT driver_code, COUNT(*) as cnt
        FROM driver_votes WHERE season = ? AND round = ?
        GROUP BY driver_code
        ORDER BY cnt DESC, driver_code ASC
        LIMIT 1
        """,
        (season, round_num),
    ) as cursor:
        row = await cursor.fetchone()
        return (row["driver_code"], row["cnt"]) if row else (None, 0)


# --- Игра на реакцию: профиль и лидерборд ---

def _normalize_reaction_name(name: str | None) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    value = " ".join(value.split())
    return value[:32]


def _normalize_reflex_mode(mode: str | None) -> str:
    value = (mode or "").strip().lower()
    if value not in {"timed", "endless"}:
        raise ValueError("mode must be 'timed' or 'endless'")
    return value


def _normalize_reflex_difficulty(difficulty: str | None) -> str:
    value = (difficulty or "").strip().lower()
    if value not in {"easy", "medium", "hard"}:
        raise ValueError("difficulty must be easy/medium/hard")
    return value


async def get_reaction_profile(telegram_id: int) -> dict:
    """Возвращает профиль участия пользователя в лидерборде реакции."""
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    await get_or_create_user(tg_id)

    async with db.conn.execute(
        """
        SELECT display_name, leaderboard_opt_in, prompt_seen
        FROM reaction_leaderboard_profiles
        WHERE telegram_id = ?
        """,
        (tg_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        user = await (await db.conn.execute(
            """SELECT pp.display_name FROM users u
               JOIN prediction_profiles pp ON pp.user_id = u.id WHERE u.telegram_id = ?""", (tg_id,)
        )).fetchone()
        return {"display_name": _normalize_reaction_name(user["display_name"] if user else ""),
                "participate": False, "prompt_seen": False}

    return {
        "display_name": (row["display_name"] or "").strip(),
        "participate": bool(row["leaderboard_opt_in"]),
        "prompt_seen": bool(row["prompt_seen"]),
    }


async def upsert_reaction_profile(
    telegram_id: int,
    display_name: str | None = None,
    participate: bool | None = None,
    prompt_seen: bool | None = None,
) -> dict:
    """Создает/обновляет профиль лидерборда реакции."""
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    await get_or_create_user(tg_id)

    current = await get_reaction_profile(tg_id)
    next_name = _normalize_reaction_name(display_name if display_name is not None else current["display_name"])
    next_participate = current["participate"] if participate is None else bool(participate)
    next_prompt_seen = current["prompt_seen"] if prompt_seen is None else bool(prompt_seen)

    await db.conn.execute(
        """
        INSERT INTO reaction_leaderboard_profiles (telegram_id, display_name, leaderboard_opt_in, prompt_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
          display_name = excluded.display_name,
          leaderboard_opt_in = excluded.leaderboard_opt_in,
          prompt_seen = excluded.prompt_seen,
          updated_at = CURRENT_TIMESTAMP
        """,
        (tg_id, next_name, int(next_participate), int(next_prompt_seen)),
    )
    await db.conn.commit()

    return {"display_name": next_name, "participate": next_participate, "prompt_seen": next_prompt_seen}


async def ensure_race_game_profile(telegram_id: int) -> tuple[dict, bool]:
    """Create an opted-in profile on the first completed Emerald Loop race.

    An existing profile is never changed, so a user's explicit opt-out remains
    authoritative. The boolean return value tells the API whether this call
    created the profile automatically.
    """
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    await get_or_create_user(tg_id)

    async with db.conn.execute(
        "SELECT 1 FROM reaction_leaderboard_profiles WHERE telegram_id = ?",
        (tg_id,),
    ) as cursor:
        if await cursor.fetchone():
            return await get_reaction_profile(tg_id), False

    async with db.conn.execute(
        """SELECT COALESCE(pp.display_name, u.display_name) AS display_name, u.telegram_username
           FROM users u LEFT JOIN prediction_profiles pp ON pp.user_id = u.id WHERE u.telegram_id = ?""",
        (tg_id,),
    ) as cursor:
        user = await cursor.fetchone()
    suggested_name = _normalize_reaction_name(
        (user["display_name"] if user else None)
        or (user["telegram_username"] if user else None)
        or f"Pilot #{str(tg_id)[-4:]}"
    )
    insert = await db.conn.execute(
        """
        INSERT OR IGNORE INTO reaction_leaderboard_profiles(
            telegram_id, display_name, leaderboard_opt_in, prompt_seen
        ) VALUES (?, ?, 1, 1)
        """,
        (tg_id, suggested_name),
    )
    await db.conn.commit()
    return await get_reaction_profile(tg_id), bool(insert.rowcount)


async def save_reaction_score(telegram_id: int, time_ms: int) -> bool:
    """
    Сохраняет результат реакции в мс, если пользователь участвует в лидерборде.
    Возвращает True, если результат сохранен.
    """
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    profile = await get_reaction_profile(tg_id)
    if not profile["participate"]:
        return False

    normalized_time = int(time_ms)
    if normalized_time <= 0:
        return False

    await db.conn.execute(
        "INSERT INTO reaction_leaderboard_scores (telegram_id, time_ms) VALUES (?, ?)",
        (tg_id, normalized_time),
    )
    await db.conn.commit()
    return True


async def get_reaction_leaderboard(telegram_id: int | None = None) -> dict:
    """
    Возвращает таблицу лидеров (по лучшему времени каждого пользователя).
    Формат: {"entries": [...], "me": {...} | None}
    """
    if not db.conn:
        await db.connect()

    async with db.conn.execute(
        """
        SELECT
            p.telegram_id AS telegram_id,
            p.display_name AS display_name,
            MIN(s.time_ms) AS best_time_ms
        FROM reaction_leaderboard_profiles p
        JOIN reaction_leaderboard_scores s ON s.telegram_id = p.telegram_id
        WHERE p.leaderboard_opt_in = 1
        GROUP BY p.telegram_id, p.display_name
        ORDER BY best_time_ms ASC, p.telegram_id ASC
        """
    ) as cursor:
        rows = await cursor.fetchall()

    entries: list[dict] = []
    me: dict | None = None
    current_place = 0
    last_time: int | None = None

    for index, row in enumerate(rows, start=1):
        best_time = int(row["best_time_ms"])
        if last_time is None or best_time != last_time:
            current_place = index
            last_time = best_time
        name = (row["display_name"] or "").strip() or f"Pilot #{str(row['telegram_id'])[-4:]}"
        item = {
            "place": current_place,
            "telegram_id": int(row["telegram_id"]),
            "name": name,
            "time_ms": best_time,
            "is_me": bool(telegram_id is not None and int(row["telegram_id"]) == int(telegram_id)),
        }
        entries.append(item)
        if item["is_me"]:
            me = item

    return {"entries": entries, "me": me}


# --- Emerald Loop: сохранение результатов и лидерборд ---

async def save_race_game_score(
    telegram_id: int,
    time_ms: int,
    telemetry: list[dict] | None = None,
    track_id: str = "emerald-loop-v1",
    return_score_id: bool = False,
) -> bool | int:
    """Сохраняет время трёх кругов для участника общего игрового рейтинга."""
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    profile, _ = await ensure_race_game_profile(tg_id)
    if not profile["participate"]:
        return False

    normalized_time = int(time_ms)
    if normalized_time < 15_000 or normalized_time > 3_600_000:
        return False

    normalized_track = str(track_id or "").strip()
    if normalized_track not in SUPPORTED_TRACK_IDS:
        return False
    try:
        validate_race_path(normalized_track, telemetry or [])
    except (ValueError, TypeError, KeyError):
        return False
    telemetry_json = (
        json.dumps(telemetry, ensure_ascii=False, separators=(",", ":"))
        if telemetry
        else None
    )
    async with db.write_lock:
        await db.conn.execute('BEGIN IMMEDIATE')
        try:
            cursor = await db.conn.execute(
                """
                INSERT INTO race_game_scores (telegram_id, time_ms, track_id, telemetry_json)
                VALUES (?, ?, ?, ?)
                """,
                (tg_id, normalized_time, normalized_track, telemetry_json),
            )
            from app.services.weekly_race_overtakes import record_overtakes
            await record_overtakes(db.conn,cursor.lastrowid)
            await db.conn.commit()
        except BaseException:
            await db.conn.rollback()
            raise
    return cursor.lastrowid if return_score_id else True


async def get_race_game_leaderboard(
    telegram_id: int | None = None,
    track_id: str = "emerald-loop-v1",
) -> dict:
    """Возвращает лучшее время каждого участника Emerald Loop."""
    if not db.conn:
        await db.connect()

    async with db.conn.execute(
        """
        SELECT
            p.telegram_id AS telegram_id,
            p.display_name AS display_name,
            MIN(s.time_ms) AS best_time_ms
        FROM reaction_leaderboard_profiles p
        JOIN race_game_scores s ON s.telegram_id = p.telegram_id
        WHERE p.leaderboard_opt_in = 1 AND s.track_id = ?
        GROUP BY p.telegram_id, p.display_name
        ORDER BY best_time_ms ASC, p.telegram_id ASC
        """,
        (track_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    entries: list[dict] = []
    me: dict | None = None
    current_place = 0
    last_time: int | None = None

    for index, row in enumerate(rows, start=1):
        best_time = int(row["best_time_ms"])
        if last_time is None or best_time != last_time:
            current_place = index
            last_time = best_time
        name = (row["display_name"] or "").strip() or f"Pilot #{str(row['telegram_id'])[-4:]}"
        item = {
            "place": current_place,
            "telegram_id": int(row["telegram_id"]),
            "name": name,
            "time_ms": best_time,
            "is_me": bool(telegram_id is not None and int(row["telegram_id"]) == int(telegram_id)),
        }
        entries.append(item)
        if item["is_me"]:
            me = item

    ghost: dict | None = None
    async with db.conn.execute(
        """
        SELECT p.telegram_id, p.display_name, s.time_ms, s.telemetry_json
        FROM race_game_scores s
        JOIN reaction_leaderboard_profiles p ON p.telegram_id = s.telegram_id
        WHERE p.leaderboard_opt_in = 1
          AND s.track_id = ?
          AND s.telemetry_json IS NOT NULL
          AND s.telemetry_json <> ''
        ORDER BY s.time_ms ASC, s.id ASC
        LIMIT 1
        """,
        (track_id,),
    ) as cursor:
        fastest = await cursor.fetchone()
    # Never show a slower available replay as the current record holder.
    if (fastest is not None and fastest["telemetry_json"] and entries
            and int(fastest["time_ms"]) == entries[0]["time_ms"]):
        try:
            samples = json.loads(fastest["telemetry_json"])
            if isinstance(samples, list) and len(samples) >= 2:
                ghost_time = int(fastest["time_ms"])
                leaderboard_place = next(
                    (
                        entry["place"]
                        for entry in entries
                        if entry["telegram_id"] == int(fastest["telegram_id"])
                    ),
                    None,
                )
                ghost = {
                    "name": (fastest["display_name"] or "").strip() or "Ghost Racer",
                    "time_ms": ghost_time,
                    "samples": samples,
                    "leaderboard_place": leaderboard_place,
                    "is_global_best": bool(entries and ghost_time == entries[0]["time_ms"]),
                }
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Invalid Emerald Loop ghost telemetry ignored")

    progress = None
    if telegram_id is not None:
        stats = await (await db.conn.execute('SELECT COUNT(*) attempts,MIN(time_ms) best_time_ms FROM race_game_scores WHERE telegram_id=? AND track_id=?',(int(telegram_id),track_id))).fetchone()
        first = await (await db.conn.execute('SELECT time_ms FROM race_game_scores WHERE telegram_id=? AND track_id=? ORDER BY id LIMIT 1',(int(telegram_id),track_id))).fetchone()
        recent = await (await db.conn.execute('SELECT time_ms,created_at FROM race_game_scores WHERE telegram_id=? AND track_id=? ORDER BY id DESC LIMIT 10',(int(telegram_id),track_id))).fetchall()
        progress = {**dict(stats),'improvement_ms':int(first[0])-int(stats['best_time_ms']) if first else None,'recent':[dict(r) for r in recent]}
    return {"entries": entries, "me": me, "ghost": ghost, "track_id": track_id, "progress":progress}


# --- Reflex Grid: сохранение результатов и лидерборд ---

async def save_reflex_grid_score(
    telegram_id: int,
    mode: str,
    difficulty: str,
    score: int,
    time_ms: int,
) -> bool:
    """
    Сохраняет результат новой игры Reflex Grid.
    Использует те же настройки участия/имени, что и реакция (общий профиль).
    """
    if not db.conn:
        await db.connect()
    tg_id = int(telegram_id)
    profile = await get_reaction_profile(tg_id)
    if not profile["participate"]:
        return False

    normalized_mode = _normalize_reflex_mode(mode)
    normalized_difficulty = _normalize_reflex_difficulty(difficulty)
    normalized_score = int(score)
    normalized_time = int(time_ms)

    if normalized_score < 0 or normalized_time <= 0:
        return False

    await db.conn.execute(
        """
        INSERT INTO reflex_grid_scores (telegram_id, mode, difficulty, score, time_ms)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tg_id, normalized_mode, normalized_difficulty, normalized_score, normalized_time),
    )
    await db.conn.commit()
    return True


async def get_reflex_grid_leaderboard(
    mode: str,
    difficulty: str,
    telegram_id: int | None = None,
) -> dict:
    """
    Возвращает лидерборд Reflex Grid для выбранных режима и сложности.
    timed   -> выше score лучше, при равенстве меньше time_ms лучше
    endless -> меньше time_ms лучше, при равенстве выше score лучше
    """
    if not db.conn:
        await db.connect()
    normalized_mode = _normalize_reflex_mode(mode)
    normalized_difficulty = _normalize_reflex_difficulty(difficulty)

    if normalized_mode == "timed":
        query = """
        SELECT
            p.telegram_id AS telegram_id,
            p.display_name AS display_name,
            s.score AS score,
            s.time_ms AS time_ms
        FROM reaction_leaderboard_profiles p
        JOIN reflex_grid_scores s ON s.telegram_id = p.telegram_id
        WHERE p.leaderboard_opt_in = 1
          AND s.mode = ?
          AND s.difficulty = ?
          AND NOT EXISTS (
              SELECT 1
              FROM reflex_grid_scores s2
              WHERE s2.telegram_id = s.telegram_id
                AND s2.mode = s.mode
                AND s2.difficulty = s.difficulty
                AND (
                    s2.score > s.score
                    OR (s2.score = s.score AND s2.time_ms < s.time_ms)
                    OR (s2.score = s.score AND s2.time_ms = s.time_ms AND s2.id < s.id)
                )
          )
        ORDER BY s.score DESC, s.time_ms ASC, p.telegram_id ASC
        """
    else:
        query = """
        SELECT
            p.telegram_id AS telegram_id,
            p.display_name AS display_name,
            s.score AS score,
            s.time_ms AS time_ms
        FROM reaction_leaderboard_profiles p
        JOIN reflex_grid_scores s ON s.telegram_id = p.telegram_id
        WHERE p.leaderboard_opt_in = 1
          AND s.mode = ?
          AND s.difficulty = ?
          AND NOT EXISTS (
              SELECT 1
              FROM reflex_grid_scores s2
              WHERE s2.telegram_id = s.telegram_id
                AND s2.mode = s.mode
                AND s2.difficulty = s.difficulty
                AND (
                    s2.time_ms < s.time_ms
                    OR (s2.time_ms = s.time_ms AND s2.score > s.score)
                    OR (s2.time_ms = s.time_ms AND s2.score = s.score AND s2.id < s.id)
                )
          )
        ORDER BY s.time_ms ASC, s.score DESC, p.telegram_id ASC
        """

    async with db.conn.execute(query, (normalized_mode, normalized_difficulty)) as cursor:
        rows = await cursor.fetchall()

    entries: list[dict] = []
    me: dict | None = None
    current_place = 0
    last_rank_key: tuple[int, int] | None = None

    for index, row in enumerate(rows, start=1):
        score_value = int(row["score"])
        time_value = int(row["time_ms"])
        if normalized_mode == "timed":
            rank_key = (score_value, -time_value)
        else:
            rank_key = (-time_value, score_value)
        if last_rank_key is None or rank_key != last_rank_key:
            current_place = index
            last_rank_key = rank_key
        name = (row["display_name"] or "").strip() or f"Pilot #{str(row['telegram_id'])[-4:]}"
        item = {
            "place": current_place,
            "telegram_id": int(row["telegram_id"]),
            "name": name,
            "score": score_value,
            "time_ms": time_value,
            "mode": normalized_mode,
            "difficulty": normalized_difficulty,
            "is_me": bool(telegram_id is not None and int(row["telegram_id"]) == int(telegram_id)),
        }
        entries.append(item)
        if item["is_me"]:
            me = item

    return {"entries": entries, "me": me}


# --- Чаты (группы) для общих уведомлений — без пользователей и избранного ---

async def add_group_chat(chat_id: int) -> None:
    """Добавить чат (группу) для рассылки общих уведомлений."""
    if not db.conn:
        await db.connect()
    await db.conn.execute(
        "INSERT OR IGNORE INTO group_chats (chat_id) VALUES (?)",
        (chat_id,),
    )
    await db.conn.commit()


async def remove_group_chat(chat_id: int) -> None:
    """Удалить чат из рассылки (бот удалён из группы)."""
    if not db.conn:
        await db.connect()
    await db.conn.execute("DELETE FROM group_chats WHERE chat_id = ?", (chat_id,))
    await db.conn.commit()


async def get_all_group_chats() -> List[int]:
    """Список chat_id всех групп для рассылки."""
    if not db.conn:
        await db.connect()
    async with db.conn.execute("SELECT chat_id FROM group_chats") as cursor:
        rows = await cursor.fetchall()
        return [r["chat_id"] for r in rows]
