"""Ordered, restartable migrations; runtime processes can require a ready schema."""
import asyncio
import time

from app.utils.process_lock import ProcessLock

LATEST_VERSION = 3


async def migrate(database):
    lock = ProcessLock(database.db_path.with_suffix('.migrate.lock'))
    deadline = time.monotonic() + 60
    while not lock.acquire():
        if time.monotonic() >= deadline:
            raise RuntimeError('Database migration is already running')
        await asyncio.sleep(.1)
    try:
        conn = database.conn
        await conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)')
        await conn.commit()
        applied = {r[0] for r in await (await conn.execute('SELECT version FROM schema_migrations')).fetchall()}
        if applied - set(range(1, LATEST_VERSION + 1)):
            raise RuntimeError('Database schema is newer than this application')
        if 1 not in applied:
            from app.migrations.legacy import initialize_legacy_schema
            # The existing idempotent schema also upgrades pre-migration databases.
            # It contains executescript, so the OS lock covers its internal commits.
            await initialize_legacy_schema(conn)
            await conn.execute('INSERT INTO schema_migrations VALUES(1,?)', (time.time(),))
            await conn.commit()
        from app.migrations.runtime import upgrade as runtime_upgrade
        from app.migrations.championship import upgrade as championship_upgrade
        for version, upgrade in ((2, runtime_upgrade), (3, championship_upgrade)):
            if version in applied:
                continue
            await conn.execute('BEGIN IMMEDIATE')
            try:
                await upgrade(conn)
                await conn.execute('INSERT INTO schema_migrations VALUES(?,?)', (version, time.time()))
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise
    finally:
        lock.close()


async def require_current(conn):
    try:
        version = (await (await conn.execute('SELECT MAX(version) FROM schema_migrations')).fetchone())[0]
    except Exception as exc:
        raise RuntimeError('Run python -m app.migrate before starting the application') from exc
    if version != LATEST_VERSION:
        raise RuntimeError('Database migration required: python -m app.migrate')
