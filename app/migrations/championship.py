"""Nullable title forecasts preserve all predictions made before this feature."""


async def upgrade(conn):
    columns = {row[1] for row in await (await conn.execute('PRAGMA table_info(race_predictions)')).fetchall()}
    for name in ('championship_json', 'championship_context_json'):
        if name not in columns:
            await conn.execute(f'ALTER TABLE race_predictions ADD COLUMN {name} TEXT')
