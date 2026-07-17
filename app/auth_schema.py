"""SQLite schema and migration helpers for web authentication and account linking."""

from __future__ import annotations

import aiosqlite


USER_COLUMNS = {
    "id",
    "email",
    "password_hash",
    "telegram_id",
    "email_verified",
    "timezone",
    "notify_before",
    "notifications_enabled",
    "created_at",
    "updated_at",
    "archived_at",
}


CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT COLLATE NOCASE UNIQUE,
    password_hash TEXT,
    telegram_id INTEGER UNIQUE,
    email_verified INTEGER NOT NULL DEFAULT 0 CHECK (email_verified IN (0, 1)),
    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
    notify_before INTEGER NOT NULL DEFAULT 60,
    notifications_enabled INTEGER NOT NULL DEFAULT 0 CHECK (notifications_enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT,
    CHECK (email IS NOT NULL OR telegram_id IS NOT NULL),
    CHECK (password_hash IS NULL OR email IS NOT NULL)
);
"""


async def _table_info(conn: aiosqlite.Connection, table: str) -> list[aiosqlite.Row]:
    async with conn.execute(f'PRAGMA table_info("{table}")') as cursor:
        return list(await cursor.fetchall())


async def _users_need_rebuild(conn: aiosqlite.Connection) -> bool:
    columns = await _table_info(conn, "users")
    if not columns:
        return False
    names = {row["name"] for row in columns}
    telegram_column = next((row for row in columns if row["name"] == "telegram_id"), None)
    return not USER_COLUMNS.issubset(names) or bool(telegram_column and telegram_column["notnull"])


async def _rebuild_users(conn: aiosqlite.Connection) -> None:
    """Rebuild the legacy Telegram-only users table without changing user IDs."""
    old_columns = {row["name"] for row in await _table_info(conn, "users")}
    await conn.commit()
    await conn.execute("PRAGMA foreign_keys = OFF")
    try:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute("DROP TABLE IF EXISTS users_auth_migration")
        await conn.execute(CREATE_USERS_SQL.replace("users", "users_auth_migration", 1))

        def old_or_default(name: str, default_sql: str) -> str:
            return f'"{name}"' if name in old_columns else default_sql

        await conn.execute(
            f"""
            INSERT INTO users_auth_migration (
                id, email, password_hash, telegram_id, email_verified,
                timezone, notify_before, notifications_enabled,
                created_at, updated_at, archived_at
            )
            SELECT
                id,
                {old_or_default('email', 'NULL')},
                {old_or_default('password_hash', 'NULL')},
                telegram_id,
                {old_or_default('email_verified', '0')},
                COALESCE({old_or_default('timezone', "'Europe/Moscow'")}, 'Europe/Moscow'),
                COALESCE({old_or_default('notify_before', '60')}, 60),
                COALESCE({old_or_default('notifications_enabled', '0')}, 0),
                COALESCE({old_or_default('created_at', 'CURRENT_TIMESTAMP')}, CURRENT_TIMESTAMP),
                COALESCE({old_or_default('updated_at', old_or_default('created_at', 'CURRENT_TIMESTAMP'))}, CURRENT_TIMESTAMP),
                {old_or_default('archived_at', 'NULL')}
            FROM users
            """
        )
        await conn.execute("DROP TABLE users")
        await conn.execute("ALTER TABLE users_auth_migration RENAME TO users")
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.execute("PRAGMA foreign_keys = ON")


async def ensure_auth_schema(conn: aiosqlite.Connection) -> None:
    """Create or upgrade all authentication tables and their indexes."""
    conn.row_factory = aiosqlite.Row
    await conn.execute(CREATE_USERS_SQL)
    if await _users_need_rebuild(conn):
        await _rebuild_users(conn)

    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS verification_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE,
            code_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_verification_codes_email_created
            ON verification_codes(email, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_verification_codes_expiry
            ON verification_codes(expires_at);

        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            csrf_hash TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            user_agent TEXT,
            ip_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
            ON password_reset_tokens(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expiry
            ON password_reset_tokens(expires_at);

        CREATE TABLE IF NOT EXISTS telegram_link_sessions (
            token_hash TEXT PRIMARY KEY,
            token_hint TEXT NOT NULL UNIQUE,
            short_code_hash TEXT UNIQUE,
            web_user_id INTEGER NOT NULL,
            telegram_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'failed', 'expired', 'cancelled')),
            merge_policy TEXT CHECK (merge_policy IN ('keep_web', 'keep_telegram')),
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            failure_reason TEXT,
            FOREIGN KEY (web_user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_telegram_link_sessions_user
            ON telegram_link_sessions(web_user_id, status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_link_sessions_hint
            ON telegram_link_sessions(token_hint);
        CREATE INDEX IF NOT EXISTS idx_telegram_link_sessions_expiry
            ON telegram_link_sessions(expires_at);

        CREATE TABLE IF NOT EXISTS telegram_login_codes (
            code_hash TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'failed', 'expired', 'cancelled')),
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consumed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_telegram_login_codes_telegram
            ON telegram_login_codes(telegram_id, status);
        CREATE INDEX IF NOT EXISTS idx_telegram_login_codes_expiry
            ON telegram_login_codes(expires_at);

        CREATE TABLE IF NOT EXISTS auth_rate_limits (
            action TEXT NOT NULL,
            identifier_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            window_expires_at TEXT NOT NULL,
            PRIMARY KEY (action, identifier_hash)
        );

        CREATE TABLE IF NOT EXISTS account_merge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_user_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            strategy TEXT NOT NULL CHECK (strategy IN ('keep_web', 'keep_telegram')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.commit()
