"""Add missing race facts; scored history changes only through confirmed CAS apply."""
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager

import aiosqlite
from app.db import db
from app.services.prediction_race_facts import get_prediction_race_facts
from app.services.prediction_service import prediction_breakdown, EXACT_POINTS

FIELDS = ('fastest_lap_driver', 'first_retirement_driver', 'safety_car')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS prediction_recovery (
 id TEXT PRIMARY KEY, season INTEGER NOT NULL, round INTEGER NOT NULL,
 created REAL NOT NULL, state TEXT NOT NULL, fingerprint TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL, summary_json TEXT NOT NULL,
 applied_by INTEGER, applied_at REAL
);
CREATE TABLE IF NOT EXISTS prediction_recovery_checks (
 season INTEGER NOT NULL, round INTEGER NOT NULL, checked REAL NOT NULL,
 PRIMARY KEY(season,round)
);
'''


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(db.db_path, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(SCHEMA)
        yield conn


async def snapshot(conn, season, round_num):
    actual = await (await conn.execute('SELECT * FROM prediction_round_results WHERE season=? AND round=?',(season,round_num))).fetchone()
    if actual is None:
        raise ValueError('Этап ещё не рассчитан. Дозагрузка доступна после первого расчёта.')
    rows = await (await conn.execute('SELECT * FROM race_predictions WHERE season=? AND round=? ORDER BY user_id',(season,round_num))).fetchall()
    return {'actual':dict(actual),'predictions':[dict(row) for row in rows]}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def build_preview(before, facts):
    actual = dict(before['actual'])
    additions = {key:facts[key] for key in FIELDS if actual.get(key) is None and facts.get(key) is not None}
    actual.update(additions)
    # Never let a refreshed display contradict a previously confirmed answer.
    conflict = any(before['actual'].get(k) is not None and facts.get(k) is not None and before['actual'][k] != facts[k] for k in FIELDS)
    if additions and not conflict:
        merged = json.loads(actual.get('race_facts_json') or 'null') or {}
        merged.update({key:value for key,value in facts.items() if value is not None and value != []})
        merged.update({key:actual[key] for key in FIELDS if actual.get(key) is not None})
        actual['race_facts_json'] = json.dumps(merged,ensure_ascii=False)
    increase = sum(EXACT_POINTS[key] for key in additions)
    actual['max_points'] = (actual.get('max_points') or 0) + increase
    predictions, changes = [], []
    for old in before['predictions']:
        if old['points'] is None or old['max_points'] is None:
            raise ValueError('Есть нерассчитанные прогнозы. Сначала завершите исходный расчёт.')
        row = dict(old)
        delta = sum(EXACT_POINTS[k] for k,v in additions.items() if old[k] == v)
        row['points'] += delta
        row['max_points'] += increase
        items = json.loads(old.get('breakdown_json') or 'null')
        if items is None:
            items = prediction_breakdown(old,before['actual'],historical=True)
            # Old snapshots cannot prove individual historical awards.
            for item in items:
                item.update(points=None,status='unknown',reason='Историческая разбивка не сохранена; прежний итог не изменён.')
        fresh = {item['key']:item for item in prediction_breakdown(old,actual,historical=True)}
        row['breakdown_json'] = json.dumps([fresh[item['key']] if item['key'] in additions else item for item in items],ensure_ascii=False)
        predictions.append(row)
        changes.append({'user_id':row['user_id'],'old_points':old['points'],'new_points':row['points'],
                        'old_max':old['max_points'],'new_max':row['max_points'],'delta':delta})
    return {'actual':actual,'predictions':predictions}, {'additions':additions,'changes':changes,
            'missing':[k for k in FIELDS if actual.get(k) is None],
            'note':facts.get('note'), 'source':facts.get('source','FastF1'), 'conflict':conflict}


async def prepare(season, round_num):
    async with connection() as conn:
        before = await snapshot(conn,season,round_num)
    facts = await get_prediction_race_facts(season,round_num)
    after, summary = build_preview(before,facts)
    identifier = uuid.uuid4().hex
    state = 'ready' if summary['additions'] else 'waiting'
    async with connection() as conn:
        await conn.execute('INSERT INTO prediction_recovery(id,season,round,created,state,fingerprint,before_json,after_json,summary_json) VALUES(?,?,?,?,?,?,?,?,?)',
                           (identifier,season,round_num,time.time(),state,fingerprint(before),json.dumps(before),json.dumps(after),json.dumps(summary)))
        await conn.execute('INSERT INTO prediction_recovery_checks VALUES(?,?,?) ON CONFLICT(season,round) DO UPDATE SET checked=excluded.checked',(season,round_num,time.time()))
        await conn.commit()
    return {'id':identifier,'season':season,'round':round_num,'state':state,**summary}


async def apply(identifier, actor):
    async with connection() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        candidate = await (await conn.execute('SELECT * FROM prediction_recovery WHERE id=?',(identifier,))).fetchone()
        if not candidate:
            raise ValueError('Проверка не найдена.')
        if candidate['state'] == 'applied':
            return {'already_applied':True}
        if candidate['state'] != 'ready':
            raise ValueError('Нет новых подтверждённых данных для применения.')
        if time.time()-candidate['created'] > 86400:
            await conn.execute("UPDATE prediction_recovery SET state='stale' WHERE id=?",(identifier,))
            await conn.commit()
            raise ValueError('Проверка старше суток. Загрузите свежие данные перед применением.')
        current = await snapshot(conn,candidate['season'],candidate['round'])
        if fingerprint(current) != candidate['fingerprint']:
            await conn.execute("UPDATE prediction_recovery SET state='stale' WHERE id=?",(identifier,))
            await conn.commit()
            raise ValueError('Результаты изменились после проверки. Создайте новый предпросмотр.')
        after = json.loads(candidate['after_json'])
        actual = after['actual']
        await conn.execute('UPDATE prediction_round_results SET fastest_lap_driver=?,first_retirement_driver=?,safety_car=?,max_points=?,race_facts_json=?,calculated_at=CURRENT_TIMESTAMP WHERE season=? AND round=?',
                           (*(actual.get(k) for k in FIELDS),actual['max_points'],actual.get('race_facts_json'),candidate['season'],candidate['round']))
        for row in after['predictions']:
            await conn.execute('UPDATE race_predictions SET points=?,max_points=?,breakdown_json=?,scored_at=CURRENT_TIMESTAMP WHERE user_id=? AND season=? AND round=?',
                               (row['points'],row['max_points'],row['breakdown_json'],row['user_id'],candidate['season'],candidate['round']))
        await conn.execute("UPDATE prediction_recovery SET state='applied',applied_by=?,applied_at=? WHERE id=?",(actor,time.time(),identifier))
        await conn.commit()
    return {'already_applied':False}


async def history():
    async with connection() as conn:
        rows = await (await conn.execute('SELECT id,season,round,created,state,summary_json,applied_by,applied_at FROM prediction_recovery ORDER BY created DESC LIMIT 30')).fetchall()
        return [{**{k:row[k] for k in row.keys() if k != 'summary_json'},**json.loads(row['summary_json'])} for row in rows]


async def refresh_missing():
    """One recent incomplete round per tick, at most once per hour; never apply."""
    async with connection() as conn:
        row = await (await conn.execute('''SELECT r.season,r.round FROM prediction_round_results r
            LEFT JOIN prediction_recovery_checks c ON c.season=r.season AND c.round=r.round
            WHERE (r.fastest_lap_driver IS NULL OR r.first_retirement_driver IS NULL OR r.safety_car IS NULL)
            AND datetime(r.calculated_at)>=datetime('now','-14 days') AND COALESCE(c.checked,0)<?
            AND NOT EXISTS (SELECT 1 FROM prediction_recovery p WHERE p.season=r.season AND p.round=r.round AND p.state='ready' AND p.created>strftime('%s','now')-86400)
            ORDER BY COALESCE(c.checked,0) LIMIT 1''',(time.time()-3600,))).fetchone()
        if row:
            await conn.execute('INSERT INTO prediction_recovery_checks VALUES(?,?,?) ON CONFLICT(season,round) DO UPDATE SET checked=excluded.checked',(row['season'],row['round'],time.time()))
            await conn.commit()
    if row:
        await prepare(row['season'],row['round'])
