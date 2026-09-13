SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_notification_batches (
 id TEXT PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
 title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL,
 filters TEXT NOT NULL, push INTEGER NOT NULL, created_at REAL NOT NULL,
 sent_at REAL, recipients INTEGER NOT NULL DEFAULT 0, queued INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS admin_notification_targets (
 batch_id TEXT NOT NULL REFERENCES admin_notification_batches(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 PRIMARY KEY(batch_id,user_id)
);
"""
