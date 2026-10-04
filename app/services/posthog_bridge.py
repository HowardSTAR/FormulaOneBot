"""First-party event forwarding to a configured PostHog instance, with durable retries."""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import aiohttp

log = logging.getLogger(__name__)
SCHEMA = '''CREATE TABLE IF NOT EXISTS posthog_outbox (
    event_id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    payload TEXT NOT NULL, created REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0, sent REAL
);
CREATE INDEX IF NOT EXISTS idx_posthog_outbox_pending ON posthog_outbox(sent,next_attempt);
'''

def config():
    host = os.getenv('POSTHOG_HOST','').strip().rstrip('/')
    key = os.getenv('POSTHOG_PROJECT_KEY','').strip()
    url = urlsplit(host)
    valid = bool(url.hostname and not url.username and not url.password and not url.query and not url.fragment
                 and url.path in ('','/') and (url.scheme == 'https' or (url.scheme == 'http' and url.hostname in ('localhost','127.0.0.1','posthog'))))
    return host if valid else '', key

async def enqueue(conn, event_id, visitor, user_id, event, properties, now=None):
    host, key = config()
    if not host or not key:
        return
    now = time.time() if now is None else now
    payload = {'uuid':event_id,'event':event,'distinct_id':hashlib.sha256(('turbotears:'+visitor).encode()).hexdigest(),
        'timestamp':datetime.fromtimestamp(now,timezone.utc).isoformat(),
        'properties':{**properties,'$process_person_profile':False,'$geoip_disable':True}}
    await conn.execute('INSERT OR IGNORE INTO posthog_outbox(event_id,user_id,payload,created) VALUES(?,?,?,?)',
        (event_id,user_id,json.dumps(payload),now))

async def status(conn):
    host,key = config()
    row = await (await conn.execute('''SELECT SUM(sent IS NULL) pending,SUM(sent IS NULL AND attempts>0) failed,
        MAX(sent) last_sent FROM posthog_outbox''')).fetchone()
    return {'configured':bool(host and key),'pending':row['pending'] or 0,'failed':row['failed'] or 0,'last_sent':row['last_sent']}

async def confirmed_prediction(database, visitor, user_id, season, round_num):
    """Best-effort analytics after a committed save, once per account and round."""
    host,key = config()
    if not host or not key:
        return
    try:
        visitor = str(uuid.UUID(visitor))
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'turbotears:prediction_saved:{user_id}:{season}:{round_num}'))
        async with database.write_lock:
            try:
                await enqueue(database.conn,event_id,visitor,user_id,'prediction_saved',
                              {'path':'/predictions','season':season,'round':round_num})
                await database.conn.commit()
            except Exception:
                await database.conn.rollback()
                raise
    except (ValueError,AttributeError):
        return  # No browser identifier for bot/direct API requests.
    except Exception:
        log.warning('Could not queue prediction analytics; prediction was saved')

async def flush(database, session):
    now = time.time()
    async with database.write_lock:
        await database.conn.execute('DELETE FROM posthog_outbox WHERE created<?',(now-30*86400,))
        await database.conn.commit()
    host,key = config()
    if not host or not key:
        return
    rows = await (await database.conn.execute('''SELECT event_id,payload,attempts FROM posthog_outbox
        WHERE sent IS NULL AND next_attempt<=? ORDER BY created LIMIT 50''',(now,))).fetchall()
    for row in rows:
        try:
            async with session.post(host+'/i/v0/e/',json={'api_key':key,**json.loads(row['payload'])},allow_redirects=False) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f'HTTP {response.status}')
            async with database.write_lock:
                await database.conn.execute('UPDATE posthog_outbox SET sent=? WHERE event_id=?',(time.time(),row['event_id']))
                await database.conn.commit()
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
            attempts=row['attempts']+1
            async with database.write_lock:
                await database.conn.execute('UPDATE posthog_outbox SET attempts=?,next_attempt=? WHERE event_id=?',
                    (attempts,time.time()+min(3600,30*2**min(attempts,7)),row['event_id']))
                await database.conn.commit()
async def worker(database):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        while True:
            try:
                await flush(database,session)
            except Exception:
                log.warning('PostHog forwarding failed; will retry')
            await asyncio.sleep(15)
