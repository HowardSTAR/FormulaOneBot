"""Version 1: existing idempotent schema, retained for upgrades and fresh installs."""
import logging
import aiosqlite

logger = logging.getLogger(__name__)


async def initialize_legacy_schema(conn):
    # 1. Таблица пользователей
    from app.auth_schema import ensure_auth_schema
    await ensure_auth_schema(conn)
    from app.services.boosty_service import SCHEMA as boosty_schema
    await conn.executescript(boosty_schema)
    from app.services.user_profiles import SCHEMA as user_profiles_schema
    await conn.executescript(user_profiles_schema)
    from app.services.trophies import SCHEMA as trophies_schema
    await conn.executescript(trophies_schema)
    from app.services.telegram_outbox import SCHEMA as telegram_outbox_schema
    await conn.executescript(telegram_outbox_schema)
    from app.services.prediction_recovery import SCHEMA as prediction_recovery_schema
    await conn.executescript(prediction_recovery_schema)
    from app.admin_notifications_schema import SCHEMA as admin_notifications_schema
    from app.services.recap_news import ensure_schema as ensure_recap_news_schema
    await ensure_recap_news_schema(conn)
    from app.services.web_notifications import initialize as initialize_web_notifications
    await conn.executescript(admin_notifications_schema)
    await initialize_web_notifications(conn)
    from app.services.prediction_analytics import ensure_schema
    await ensure_schema(conn)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS site_visits (
            visitor_id TEXT NOT NULL,
            user_id INTEGER,
            path TEXT NOT NULL,
            bucket INTEGER NOT NULL,
            PRIMARY KEY(visitor_id, path, bucket)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_site_visits_bucket ON site_visits(bucket)")
    visit_columns = await (await conn.execute('PRAGMA table_info(site_visits)')).fetchall()
    if 'platform' not in {r['name'] for r in visit_columns}:
        await conn.execute("ALTER TABLE site_visits ADD COLUMN platform TEXT NOT NULL DEFAULT 'unknown'")
    await conn.execute('''CREATE TABLE IF NOT EXISTS product_events (
        visitor_id TEXT NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        event TEXT NOT NULL, path TEXT NOT NULL, platform TEXT NOT NULL,
        season INTEGER NOT NULL, round INTEGER NOT NULL, bucket INTEGER NOT NULL,
        created REAL NOT NULL, error_code INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(visitor_id,event,path,season,round,bucket)
    )''')
    await conn.execute('CREATE INDEX IF NOT EXISTS idx_product_events_created ON product_events(created)')
    from app.services.posthog_bridge import SCHEMA as posthog_schema
    await conn.executescript(posthog_schema)
    await conn.executescript('''CREATE TABLE IF NOT EXISTS ui_events (
        event_id TEXT PRIMARY KEY, visitor_id TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        event TEXT NOT NULL, path TEXT NOT NULL, action TEXT NOT NULL,
        destination TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL, created REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ui_events_created ON ui_events(created);
    CREATE INDEX IF NOT EXISTS idx_ui_events_visitor_created ON ui_events(visitor_id,created);
    ''')

    # Проверка и добавление колонок (миграции "на лету")
    # 2. Таблицы избранного
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS favorite_drivers (
            user_id INTEGER NOT NULL,
            driver_code TEXT NOT NULL,
            PRIMARY KEY (user_id, driver_code),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    await conn.execute(
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
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_state (
            season INTEGER PRIMARY KEY,
            last_notified_round INTEGER,
            last_reminded_round INTEGER,
            last_notified_quali_round INTEGER,
            last_notified_sprint_quali_round INTEGER,
            last_notified_sprint_round INTEGER
        );
        """
    )
    async with conn.execute("PRAGMA table_info(notification_state)") as cursor:
        cols = [row['name'] for row in await cursor.fetchall()]
    if "last_notified_quali_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_quali_round INTEGER")
    if "last_notified_sprint_quali_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_sprint_quali_round INTEGER")
    if "last_notified_sprint_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_sprint_round INTEGER")
    if "last_notified_recap_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_recap_round INTEGER")
    # При первом развёртывании новых типов не рассылаем задним числом спринты
    # уже завершённых этапов. Если текущий этап ещё не закрыт гонкой/квалой,
    # значение останется на предыдущем раунде и нужный спринт будет отправлен.
    await conn.execute(
        "UPDATE notification_state SET last_notified_sprint_quali_round = "
        "COALESCE(last_notified_quali_round, last_notified_round) "
        "WHERE last_notified_sprint_quali_round IS NULL"
    )
    await conn.execute(
        "UPDATE notification_state SET last_notified_sprint_round = "
        "COALESCE(last_notified_round, last_notified_quali_round) "
        "WHERE last_notified_sprint_round IS NULL"
    )
    if "last_notified_voting_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_voting_round INTEGER")
    if "last_notified_voting_invite_round" not in cols:
        await conn.execute("ALTER TABLE notification_state ADD COLUMN last_notified_voting_invite_round INTEGER")

    try:
        await conn.execute("ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN DEFAULT 0")
        await conn.commit()
        logger.info("Миграция успешна: колонка notifications_enabled добавлена в старую базу.")
    except aiosqlite.OperationalError as e:
        # Если база уже была обновлена ранее, просто игнорируем ошибку
        if "duplicate column name" in str(e).lower():
            pass
        else:
            logger.error(f"Ошибка при миграции: {e}")

    # 4. Таблицы голосований (гонка 1–5, пилот дня)
    await conn.execute(
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
    await conn.execute(
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
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS group_chats (
            chat_id INTEGER PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # 6. Уже отправленные напоминания (по пользователю/этап/квали-или-гонка/за сколько минут)
    await conn.execute(
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
    await conn.execute(
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
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reaction_leaderboard_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            time_ms INTEGER NOT NULL CHECK (time_ms > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reaction_scores_telegram ON reaction_leaderboard_scores(telegram_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reaction_scores_time ON reaction_leaderboard_scores(time_ms)"
    )

    # 8. Лучшие времена браузерной гонки Emerald Loop.
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS race_game_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            time_ms INTEGER NOT NULL CHECK (time_ms >= 15000 AND time_ms <= 3600000),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_race_game_scores_telegram ON race_game_scores(telegram_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_race_game_scores_time ON race_game_scores(time_ms)"
    )
    async with conn.execute("PRAGMA table_info(race_game_scores)") as cursor:
        race_game_columns = {row["name"] for row in await cursor.fetchall()}
    if "track_id" not in race_game_columns:
        await conn.execute(
            "ALTER TABLE race_game_scores ADD COLUMN track_id TEXT NOT NULL DEFAULT 'emerald-loop-v1'"
        )
    if "telemetry_json" not in race_game_columns:
        await conn.execute("ALTER TABLE race_game_scores ADD COLUMN telemetry_json TEXT")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_race_game_track_time "
        "ON race_game_scores(track_id, time_ms)"
    )

    # 9. Результаты игры Reflex Grid (лидерборд по режимам и сложности)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflex_grid_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('timed', 'endless')),
            difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
            score INTEGER NOT NULL CHECK (score >= 0),
            time_ms INTEGER NOT NULL CHECK (time_ms > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reflex_grid_mode_difficulty ON reflex_grid_scores(mode, difficulty)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reflex_grid_telegram ON reflex_grid_scores(telegram_id)"
    )

    # 10. Прогнозы на этапы Formula 1 и история начисления баллов.
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_profiles (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    # Legacy prediction profiles were keyed by Telegram ID. Migrate them
    # to the canonical users.id so email-only accounts can participate and
    # existing Telegram profiles keep their history.
    async with conn.execute("PRAGMA table_info(prediction_profiles)") as cursor:
        profile_columns = {row["name"] for row in await cursor.fetchall()}
    if "user_id" not in profile_columns:
        await conn.execute("DROP TABLE IF EXISTS prediction_profiles_v2")
        await conn.execute(
            """
            CREATE TABLE prediction_profiles_v2 (
                user_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        await conn.execute(
            """
            INSERT OR IGNORE INTO prediction_profiles_v2(
                user_id, display_name, created_at, updated_at
            )
            SELECT u.id, pp.display_name, pp.created_at, pp.updated_at
            FROM prediction_profiles pp
            JOIN users u ON u.telegram_id = pp.telegram_id
            """
        )
        await conn.execute("DROP TABLE prediction_profiles")
        await conn.execute(
            "ALTER TABLE prediction_profiles_v2 RENAME TO prediction_profiles"
        )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS race_predictions (
            user_id INTEGER NOT NULL,
            season INTEGER NOT NULL,
            round INTEGER NOT NULL,
            sprint_pole_driver TEXT,
            sprint_winner_driver TEXT,
            pole_driver TEXT NOT NULL,
            winner_driver TEXT NOT NULL,
            second_driver TEXT NOT NULL,
            third_driver TEXT NOT NULL,
            fourth_driver TEXT NOT NULL,
            fifth_driver TEXT NOT NULL,
            fastest_lap_driver TEXT NOT NULL,
            first_retirement_driver TEXT NOT NULL,
            safety_car INTEGER NOT NULL CHECK (safety_car IN (0, 1)),
            points INTEGER,
            max_points INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scored_at TIMESTAMP,
            PRIMARY KEY (user_id, season, round),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_round_results (
            season INTEGER NOT NULL,
            round INTEGER NOT NULL,
            event_name TEXT NOT NULL,
            sprint_pole_driver TEXT,
            sprint_winner_driver TEXT,
            pole_driver TEXT,
            winner_driver TEXT,
            second_driver TEXT,
            third_driver TEXT,
            fourth_driver TEXT,
            fifth_driver TEXT,
            fastest_lap_driver TEXT,
            first_retirement_driver TEXT,
            safety_car INTEGER CHECK (safety_car IN (0, 1) OR safety_car IS NULL),
            max_points INTEGER NOT NULL DEFAULT 0,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (season, round)
        );
        """
    )
    # Миграция существующей БД: спринт-поля nullable, поэтому старые
    # прогнозы и рассчитанные этапы остаются валидными.
    for table_name in ("race_predictions", "prediction_round_results"):
        async with conn.execute(f"PRAGMA table_info({table_name})") as cursor:
            prediction_cols = {row["name"] for row in await cursor.fetchall()}
        if table_name == "race_predictions" and "breakdown_json" not in prediction_cols:
            await conn.execute("ALTER TABLE race_predictions ADD COLUMN breakdown_json TEXT")
        if table_name == "prediction_round_results" and "race_facts_json" not in prediction_cols:
            await conn.execute("ALTER TABLE prediction_round_results ADD COLUMN race_facts_json TEXT")
        if "sprint_pole_driver" not in prediction_cols:
            await conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN sprint_pole_driver TEXT"
            )
        if "sprint_winner_driver" not in prediction_cols:
            await conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN sprint_winner_driver TEXT"
            )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_notification_state (
            season INTEGER NOT NULL,
            round INTEGER NOT NULL,
            opened_sent INTEGER NOT NULL DEFAULT 0,
            closing_sent INTEGER NOT NULL DEFAULT 0,
            results_sent INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (season, round)
        );
        """
    )
    async with conn.execute("PRAGMA table_info(prediction_notification_state)") as cursor:
        notification_columns = {row[1] for row in await cursor.fetchall()}
    if "closing_sent" not in notification_columns:
        await conn.execute("ALTER TABLE prediction_notification_state ADD COLUMN closing_sent INTEGER NOT NULL DEFAULT 0")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_predictions_round ON race_predictions(season, round)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_predictions_user ON race_predictions(user_id)"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invite_token TEXT NOT NULL UNIQUE,
            invite_expires TEXT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_league_members (
            league_id INTEGER NOT NULL REFERENCES prediction_leagues(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY(league_id,user_id)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_prediction_league_user ON prediction_league_members(user_id)")
    league_columns = {r['name'] for r in await (await conn.execute('PRAGMA table_info(prediction_leagues)')).fetchall()}
    for column, definition in [('mode', "TEXT NOT NULL DEFAULT 'season'"), ('season', 'INTEGER'), ('rounds_json', 'TEXT')]:
        if column not in league_columns:
            await conn.execute(f'ALTER TABLE prediction_leagues ADD COLUMN {column} {definition}')
    from app.services.engagement import SCHEMA as engagement_schema
    await conn.executescript(engagement_schema)
    from app.services.weekly_race_overtakes import SCHEMA as weekly_overtakes_schema
    await conn.executescript(weekly_overtakes_schema)

    # 10. Журнал сообщений формы обратной связи (доставка в Telegram отмечается отдельно).
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_feedback_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            sender_name TEXT NOT NULL,
            sender_contact TEXT NOT NULL,
            message TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    await conn.commit()
