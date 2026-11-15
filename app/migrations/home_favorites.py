"""Account-wide selection for the two drivers and team on the home screen."""


async def upgrade(conn):
    await conn.execute('''CREATE TABLE home_favorites (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        drivers TEXT NOT NULL,
        teams TEXT NOT NULL
    )''')
