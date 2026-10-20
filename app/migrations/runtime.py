"""Durable forecast execution and operational status, without a new broker."""


async def upgrade(conn):
    for name, definition in [
        ('attempts', 'INTEGER NOT NULL DEFAULT 0'),
        ('next_attempt', 'REAL NOT NULL DEFAULT 0'),
        ('lease_token', 'TEXT'), ('lease_until', 'REAL NOT NULL DEFAULT 0'),
        ('snapshot', 'TEXT'),
    ]:
        await conn.execute(f'ALTER TABLE prediction_analytics ADD COLUMN {name} {definition}')
    await conn.execute('CREATE INDEX idx_forecast_due ON prediction_analytics(status,next_attempt,lease_until)')
    await conn.execute('''CREATE TABLE runtime_components (
        name TEXT PRIMARY KEY, started REAL NOT NULL, heartbeat REAL NOT NULL,
        stopped REAL, instance TEXT NOT NULL)''')
    await conn.execute('''CREATE TABLE runtime_jobs (
        name TEXT PRIMARY KEY, interval_seconds REAL NOT NULL,
        last_started REAL, last_finished REAL, last_success REAL,
        duration REAL, failures INTEGER NOT NULL DEFAULT 0, error TEXT)''')
