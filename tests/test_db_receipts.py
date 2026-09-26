import aiosqlite
import pytest

from app.db import db, set_reminder_sent, was_reminder_sent, set_last_notified_quali_round, get_last_notified_quali_round


@pytest.mark.asyncio
async def test_receipt_survives_stale_read_on_shared_connection(tmp_path, monkeypatch):
    path = tmp_path / "receipts.db"
    monkeypatch.setattr(db, "db_path", path)
    async with aiosqlite.connect(path) as setup:
        await setup.execute("PRAGMA journal_mode=WAL")
        await setup.execute("CREATE TABLE event_reminder_sent (telegram_id INTEGER, season INTEGER, round INTEGER, is_quali INTEGER, notify_before_min INTEGER, PRIMARY KEY (telegram_id, season, round, is_quali, notify_before_min))")
        await setup.execute("CREATE TABLE other_writes (value INTEGER)")
        await setup.execute("CREATE TABLE notification_state (season INTEGER PRIMARY KEY, last_notified_quali_round INTEGER)")
        await setup.commit()

    async with aiosqlite.connect(path) as stale_reader:
        await stale_reader.execute("BEGIN")
        await (await stale_reader.execute("SELECT * FROM event_reminder_sent")).fetchall()
        async with aiosqlite.connect(path) as other_writer:
            await other_writer.execute("INSERT INTO other_writes VALUES (1)")
            await other_writer.commit()

        await set_reminder_sent(123, 2026, 15, False, 20000)
        assert await was_reminder_sent(123, 2026, 15, False, 20000)
        await set_last_notified_quali_round(2026, 15)
        assert await get_last_notified_quali_round(2026) == 15
        await stale_reader.rollback()
