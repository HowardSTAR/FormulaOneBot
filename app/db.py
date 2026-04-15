import logging
import os
import aiosqlite
from pathlib import Path
from typing import List, Tuple, Any, Optional

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
        if "last_notified_voting_round" not in cols:
            await self.conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_voting_round INTEGER")
        if "last_notified_voting_invite_round" not in cols:
            await self.conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_voting_invite_round INTEGER")

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

        # 4. Таблицы голосований (гонка 1–5, пилот дня)
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS race_votes (
                user_id INTEGER NOT NULL,
                season INTEGER NOT NULL,
                round INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, season, round),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_votes (
                user_id INTEGER NOT NULL,
                season INTEGER NOT NULL,
                round INTEGER NOT NULL,
                driver_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, season, round),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        # 5. Чаты (группы/супергруппы) для общих уведомлений — без пользователей и избранного
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_chats (
                chat_id INTEGER PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 6. Уже отправленные напоминания (по пользователю/этап/квали-или-гонка/за сколько минут)
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_reminder_sent (
                telegram_id INTEGER NOT NULL,
                season INTEGER NOT NULL,
                round INTEGER NOT NULL,
                is_quali INTEGER NOT NULL,
                notify_before_min INTEGER NOT NULL,
                PRIMARY KEY (telegram_id, season, round, is_quali, notify_before_min)
            );
            """
        )

        # 7. Лидерборд игры на реакцию (отдельные таблицы, не затрагивают существующие)
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_leaderboard_profiles (
                telegram_id INTEGER PRIMARY KEY,
                display_name TEXT DEFAULT '',
                leaderboard_opt_in INTEGER NOT NULL DEFAULT 0,
                prompt_seen INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_leaderboard_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                time_ms INTEGER NOT NULL CHECK (time_ms > 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reaction_scores_telegram ON reaction_leaderboard_scores(telegram_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reaction_scores_time ON reaction_leaderboard_scores(time_ms)"
        )

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
    """Устаревший: возвращает (telegram_id, user_id). Используйте get_users_favorites_for_notifications."""
    if not db.conn: await db.connect()
    async with db.conn.execute("SELECT DISTINCT telegram_id, id FROM users") as cursor:
        rows = await cursor.fetchall()
        return [(r['telegram_id'], r['id']) for r in rows]


async def get_users_favorites_for_notifications(notifications_only: bool = True) -> dict:
    """
    Возвращает {telegram_id: {"drivers": [...], "teams": [...]}} для пользователей с избранным.
    Используется для рассылки результатов гонок и квалификации.
    """
    if not db.conn: await db.connect()
    notif_filter = " WHERE u.notifications_enabled = 1" if notifications_only else ""
    result: dict = {}
    async with db.conn.execute(
        "SELECT u.telegram_id, fd.driver_code FROM users u "
        "JOIN favorite_drivers fd ON fd.user_id = u.id"
        f"{notif_filter}"
    ) as cursor:
        async for row in cursor:
            tg_id = row['telegram_id']
            if tg_id not in result:
                result[tg_id] = {"drivers": [], "teams": []}
            result[tg_id]["drivers"].append(str(row['driver_code']).upper())
    async with db.conn.execute(
        "SELECT u.telegram_id, ft.constructor_name FROM users u "
        "JOIN favorite_teams ft ON ft.user_id = u.id"
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


async def was_reminder_sent(telegram_id: int, season: int, round_num: int, is_quali: bool, notify_before_min: int) -> bool:
    """Проверяет, отправляли ли уже напоминание этому пользователю для данного этапа/типа/за сколько минут."""
    if not db.conn:
        await db.connect()
    q = (
        "SELECT 1 FROM event_reminder_sent "
        "WHERE telegram_id = ? AND season = ? AND round = ? AND is_quali = ? AND notify_before_min = ?"
    )
    async with db.conn.execute(q, (telegram_id, season, round_num, 1 if is_quali else 0, notify_before_min)) as cur:
        row = await cur.fetchone()
    return row is not None


async def set_reminder_sent(telegram_id: int, season: int, round_num: int, is_quali: bool, notify_before_min: int) -> None:
    """Отмечает, что напоминание этому пользователю для данного этапа/типа/за сколько минут отправлено."""
    if not db.conn:
        await db.connect()
    await db.conn.execute(
        "INSERT OR IGNORE INTO event_reminder_sent (telegram_id, season, round, is_quali, notify_before_min) VALUES (?, ?, ?, ?, ?)",
        (telegram_id, season, round_num, 1 if is_quali else 0, notify_before_min),
    )
    await db.conn.commit()


async def get_last_notified_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                            "last_notified_round")


async def set_last_notified_round(season: int, r: int) -> None: await _set_round_value(season, "last_notified_round", r)


async def get_last_notified_quali_round(season: int) -> int | None: return await _get_round_value(season,
                                                                                                  "last_notified_quali_round")


async def set_last_notified_quali_round(season: int, r: int) -> None: await _set_round_value(season,
                                                                                             "last_notified_quali_round",
                                                                                             r)


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


async def get_driver_vote_winner(season: int, round_num: int) -> Tuple[str | None, int]:
    """Пилот дня по этапу: (driver_code, count) или (None, 0) если нет голосов."""
    if not db.conn: await db.connect()
    async with db.conn.execute(
        """
        SELECT driver_code, COUNT(*) as cnt
        FROM driver_votes WHERE season = ? AND round = ?
        GROUP BY driver_code
        ORDER BY cnt DESC
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
        return {"display_name": "", "participate": False, "prompt_seen": False}

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