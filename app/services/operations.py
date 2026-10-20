"""Operational read model shared by worker probes and the existing admin UI."""
import asyncio
import logging
import shutil
import sqlite3
import time
from contextlib import asynccontextmanager, closing

import aiosqlite

from app.db import db

log = logging.getLogger(__name__)


@asynccontextmanager
async def connection(database=None):
    async with aiosqlite.connect((database or db).db_path, timeout=10) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def component(name, instance, *, starting=False, stopping=False):
    now = time.time()
    async with connection() as conn:
        if starting:
            await conn.execute('INSERT INTO runtime_components VALUES(?,?,?,NULL,?) ON CONFLICT(name) DO UPDATE SET started=excluded.started,heartbeat=excluded.heartbeat,stopped=NULL,instance=excluded.instance',
                               (name, now, now, instance))
        else:
            await conn.execute('UPDATE runtime_components SET heartbeat=?,stopped=? WHERE name=? AND instance=?',
                               (now, now if stopping else None, name, instance))
        await conn.commit()


async def heartbeat(name, instance):
    while True:
        try:
            await component(name, instance)
        except Exception:
            log.exception('Cannot persist %s heartbeat', name)
        await asyncio.sleep(15)


async def register_job(name, interval):
    async with connection() as conn:
        await conn.execute('INSERT INTO runtime_jobs(name,interval_seconds) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET interval_seconds=excluded.interval_seconds', (name, interval))
        await conn.commit()


async def run_tracked(name, function, *args, **kwargs):
    started = time.time()
    async with connection() as conn:
        await conn.execute('UPDATE runtime_jobs SET last_started=? WHERE name=?', (started, name))
        await conn.commit()
    error = None
    try:
        return await function(*args, **kwargs)
    except asyncio.CancelledError:
        error = 'interrupted'
        raise
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        finished = time.time()
        async with connection() as conn:
            await conn.execute('''UPDATE runtime_jobs SET last_finished=?,duration=?,error=?,
                failures=CASE WHEN ? IS NULL THEN 0 ELSE failures+1 END,
                last_success=CASE WHEN ? IS NULL THEN ? ELSE last_success END WHERE name=?''',
                (finished, finished-started, error, error, error, finished, name))
            await conn.commit()


def component_ready(path, name, max_age=90):
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)) as conn:
            row = conn.execute('SELECT heartbeat,stopped FROM runtime_components WHERE name=?',(name,)).fetchone()
        return bool(row and row[1] is None and 0 <= time.time()-row[0] <= max_age)
    except sqlite3.Error:
        return False


def worker_ready(path, max_age=90):
    return component_ready(path, 'worker', max_age)


async def status(database=None):
    now = time.time()
    database = database or db
    async with connection(database) as conn:
        components = [dict(r) for r in await (await conn.execute('SELECT * FROM runtime_components ORDER BY name')).fetchall()]
        jobs = [dict(r) for r in await (await conn.execute('SELECT * FROM runtime_jobs ORDER BY name')).fetchall()]
        forecast = await (await conn.execute("SELECT COUNT(*) pending,MIN(created_at) oldest FROM prediction_analytics WHERE status='pending'")).fetchone()
    for item in components:
        item['healthy'] = item['stopped'] is None and 0 <= now-item['heartbeat'] <= 90
        item.pop('instance')
    worker = next((r for r in components if r['name'] == 'worker'), None)
    for item in jobs:
        reference = item['last_success'] or (worker['started'] if worker else 0)
        item['overdue'] = now-reference > max(90, 3*item['interval_seconds'])
    from app.utils.backup import backup_status
    backups = await asyncio.to_thread(backup_status)
    disk = await asyncio.to_thread(shutil.disk_usage, database.db_path.parent)
    return {'worker_healthy': bool(worker and worker['healthy']), 'components': components,
            'jobs': jobs, 'forecasts': dict(forecast), 'backups': backups, 'disk_free_bytes': disk.free}
