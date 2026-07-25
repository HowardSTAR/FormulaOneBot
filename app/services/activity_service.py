"""Privacy-conscious activity tracking for authenticated site and bot users."""

from __future__ import annotations

from datetime import datetime, timezone

from app.admin_config import get_primary_admin_email, get_primary_admin_telegram_id
from app.db import Database


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_primary_admin(email: str | None, telegram_id: int | None) -> bool:
    primary_email = get_primary_admin_email()
    primary_telegram_id = get_primary_admin_telegram_id()
    return (
        bool(primary_email and email and email.strip().lower() == primary_email)
        or bool(primary_telegram_id is not None and telegram_id == primary_telegram_id)
    )


async def record_user_activity(
    database: Database,
    user_id: int,
    source: str,
    *,
    display_name: str | None = None,
    telegram_username: str | None = None,
) -> None:
    if source not in {"site", "bot"}:
        raise ValueError("Unsupported activity source")
    if not database.conn:
        await database.connect()
    assert database.conn is not None
    now = utc_iso()
    primary_telegram_id = get_primary_admin_telegram_id()
    async with database.write_lock:
        # One sample per five minutes is enough for rolling unique-user metrics
        # and prevents an active client from growing SQLite on every API call.
        await database.conn.execute(
            """
            INSERT INTO user_activity_events(user_id, source, occurred_at)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM user_activity_events
                WHERE user_id = ? AND source = ?
                  AND datetime(occurred_at) >= datetime(?, '-5 minutes')
            )
            """,
            (int(user_id), source, now, int(user_id), source, now),
        )
        if source == "bot":
            await database.conn.execute(
                """
                UPDATE users
                SET display_name = COALESCE(?, display_name),
                    telegram_username = ?,
                    role = CASE
                        WHEN ? IS NOT NULL AND telegram_id = ? THEN 'superadmin'
                        ELSE role
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    (display_name or "").strip()[:120] or None,
                    (telegram_username or "").strip().lstrip("@")[:64] or None,
                    primary_telegram_id,
                    primary_telegram_id,
                    now,
                    int(user_id),
                ),
            )
        await database.conn.commit()


async def record_telegram_activity(
    database: Database,
    telegram_id: int,
    *,
    display_name: str | None = None,
    telegram_username: str | None = None,
) -> None:
    if not database.conn:
        await database.connect()
    assert database.conn is not None
    async with database.write_lock:
        await database.conn.execute(
            "INSERT OR IGNORE INTO users(telegram_id) VALUES (?)",
            (int(telegram_id),),
        )
        async with database.conn.execute(
            "SELECT id FROM users WHERE telegram_id = ? AND archived_at IS NULL",
            (int(telegram_id),),
        ) as cursor:
            row = await cursor.fetchone()
        await database.conn.commit()
    if row:
        await record_user_activity(
            database,
            int(row["id"]),
            "bot",
            display_name=display_name,
            telegram_username=telegram_username,
        )
