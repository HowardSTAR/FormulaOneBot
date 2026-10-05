"""Add missing race facts; scored history changes only through confirmed CAS apply."""
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite
from app.db import db
from app.services.prediction_race_facts import get_prediction_race_facts
from app.services.prediction_service import historical_prediction_breakdown, prediction_breakdown, first_retirement_winners, EXACT_POINTS

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
    old_winners = first_retirement_winners(before['actual'])
    incoming_winners = first_retirement_winners(facts)
    compatible_retirement_group = (bool(before['actual'].get('first_retirement_driver'))
                                   and old_winners <= incoming_winners
                                   and before['actual']['first_retirement_driver'] in incoming_winners)
    tie_expansion = compatible_retirement_group and old_winners < incoming_winners
    retirement_group_conflict = bool(facts.get('first_retirement_drivers') and old_winners
                                     and not old_winners <= incoming_winners)
    # Never let a refreshed display contradict a previously confirmed answer.
    conflict = bool(facts.get('conflicts')) or retirement_group_conflict or any(
        before['actual'].get(k) is not None and facts.get(k) is not None and before['actual'][k] != facts[k]
        and not (k == 'first_retirement_driver' and compatible_retirement_group)
        for k in FIELDS
    )
    if (additions or tie_expansion) and not conflict:
        merged = json.loads(actual.get('race_facts_json') or 'null') or {}
        merged.update({key:value for key,value in facts.items()
                       if key not in {'manual_evidence','prepared_by'} and value is not None and value != []})
        if facts.get('manual_evidence'):
            changed = set(additions)
            if tie_expansion:
                changed.add('first_retirement_driver')
            field_sources = dict(merged.get('field_sources') or {})
            field_sources.update({key:'Ручное подтверждение' for key in changed})
            merged['field_sources'] = field_sources
            source_urls = dict(merged.get('source_urls') or {})
            source_urls.update({key:url for key,url in facts['manual_evidence']['urls'].items() if key in changed})
            merged['source_urls'] = source_urls
        merged.update({key:actual[key] for key in FIELDS if actual.get(key) is not None})
        if old_winners and not tie_expansion:
            merged['first_retirement_drivers'] = sorted(old_winners)
        actual['race_facts_json'] = json.dumps(merged,ensure_ascii=False)
    increase = sum(EXACT_POINTS[key] for key in additions)
    actual['max_points'] = (actual.get('max_points') or 0) + increase
    predictions, changes = [], []
    for old in before['predictions']:
        if old['points'] is None or old['max_points'] is None:
            raise ValueError('Есть нерассчитанные прогнозы. Сначала завершите исходный расчёт.')
        row = dict(old)
        delta = sum(EXACT_POINTS[k] for k,v in additions.items()
                    if (str(old[k]).upper() in incoming_winners if k == 'first_retirement_driver' else old[k] == v))
        if tie_expansion and str(old['first_retirement_driver']).upper() in incoming_winners - old_winners:
            delta += EXACT_POINTS['first_retirement_driver']
        row['points'] += delta
        row['max_points'] += increase
        items = historical_prediction_breakdown(old, before['actual'])
        fresh = {item['key']:item for item in prediction_breakdown(old,actual,historical=True)}
        row['breakdown_json'] = json.dumps([fresh[item['key']] if item['key'] in additions or (tie_expansion and item['key'] == 'first_retirement_driver') else item for item in items],ensure_ascii=False)
        predictions.append(row)
        changes.append({'user_id':row['user_id'],'old_points':old['points'],'new_points':row['points'],
                        'old_max':old['max_points'],'new_max':row['max_points'],'delta':delta})
    return {'actual':actual,'predictions':predictions}, {'additions':additions,
            'retirement_group':sorted(incoming_winners) if 'first_retirement_driver' in additions else [],
            'tie_expansion':sorted(incoming_winners) if tie_expansion else [],'changes':changes,
            'missing':[k for k in FIELDS if actual.get(k) is None],
            'note':facts.get('note'), 'source':facts.get('source','FastF1'), 'conflict':conflict,
            'manual_evidence':facts.get('manual_evidence'), 'prepared_by':facts.get('prepared_by')}


async def _store_preview(season, round_num, before, facts):
    after, summary = build_preview(before, facts)
    identifier = uuid.uuid4().hex
    state = ('conflict' if summary['conflict'] else
             'ready' if summary['additions'] or summary['tie_expansion'] else
             'waiting' if summary['missing'] else 'unchanged')
    async with connection() as conn:
        await conn.execute('INSERT INTO prediction_recovery(id,season,round,created,state,fingerprint,before_json,after_json,summary_json) VALUES(?,?,?,?,?,?,?,?,?)',
                           (identifier,season,round_num,time.time(),state,fingerprint(before),json.dumps(before),json.dumps(after),json.dumps(summary)))
        if summary['manual_evidence']:
            await conn.execute('INSERT INTO admin_audit_log(actor_user_id,action,details_json,created_at) VALUES(?,?,?,?)',
                               (summary['prepared_by'],'prediction_recovery.manual_preview',
                                json.dumps({'id':identifier,'season':season,'round':round_num,'state':state,
                                            'evidence':summary['manual_evidence']},ensure_ascii=False),
                                datetime.now(timezone.utc).isoformat()))
        await conn.execute('INSERT INTO prediction_recovery_checks VALUES(?,?,?) ON CONFLICT(season,round) DO UPDATE SET checked=excluded.checked',(season,round_num,time.time()))
        await conn.commit()
    return {'id':identifier,'season':season,'round':round_num,'state':state,**summary}


async def prepare(season, round_num):
    async with connection() as conn:
        before = await snapshot(conn,season,round_num)
    facts = await get_prediction_race_facts(season,round_num,prefer_openf1=True)
    return await _store_preview(season, round_num, before, facts)


async def prepare_manual(season, round_num, values, evidence, reason, actor):
    """Preview administrator-asserted facts without fetching external APIs or changing scores."""
    async with connection() as conn:
        before = await snapshot(conn, season, round_num)
    facts = {key: value for key, value in values.items() if value is not None}
    group = facts.get('first_retirement_drivers') or []
    if group:
        facts['first_retirement_driver'] = group[0]
    if not any(key in facts for key in FIELDS):
        raise ValueError('Укажите хотя бы один подтверждённый факт гонки.')
    facts.update({'source':'Ручное подтверждение',
                  'note':'Факты внесены администратором по указанным источникам; API не опрашивались.',
                  'prepared_by':actor,
                  'manual_evidence':{'urls':evidence,'reason':reason,
                                     'confirmed_at':datetime.now(timezone.utc).isoformat()}})
    return await _store_preview(season, round_num, before, facts)


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
        summary = json.loads(candidate['summary_json'])
        if summary.get('manual_evidence') and summary.get('prepared_by') != actor:
            raise ValueError('Ручные факты может применить только администратор, создавший предпросмотр.')
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
        if summary.get('manual_evidence'):
            await conn.execute('INSERT INTO admin_audit_log(actor_user_id,action,details_json,created_at) VALUES(?,?,?,?)',
                               (actor,'prediction_recovery.manual_apply',
                                json.dumps({'id':identifier,'season':candidate['season'],'round':candidate['round'],
                                            'additions':summary['additions'],'tie_expansion':summary['tie_expansion'],
                                            'evidence':summary['manual_evidence']},ensure_ascii=False),
                                datetime.now(timezone.utc).isoformat()))
        await conn.commit()
    return {'already_applied':False}


async def history():
    async with connection() as conn:
        rows = await (await conn.execute('SELECT id,season,round,created,state,summary_json,applied_by,applied_at FROM prediction_recovery ORDER BY created DESC LIMIT 30')).fetchall()
        return [{**{k:row[k] for k in row.keys() if k != 'summary_json'},**json.loads(row['summary_json'])} for row in rows]


async def calculated_rounds(season):
    """Read-only batch scope: rounds already scored, not future calendar events."""
    async with connection() as conn:
        rows = await (await conn.execute(
            'SELECT season,round,event_name,fastest_lap_driver,first_retirement_driver,safety_car,race_facts_json '
            'FROM prediction_round_results WHERE season=? ORDER BY round', (season,),
        )).fetchall()
    result = []
    for row in rows:
        try:
            details = json.loads(row['race_facts_json'] or '{}') or {}
        except (ValueError, TypeError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        retirement_group = details.get('first_retirement_drivers')
        if isinstance(retirement_group, str):
            retirement_group = [retirement_group]
        if not isinstance(retirement_group, list):
            retirement_group = []
        result.append({'season': row['season'], 'round': row['round'], 'event_name': row['event_name'],
                       'missing': [key for key in FIELDS if row[key] is None],
                       'current': {key: row[key] for key in FIELDS},
                       'first_retirement_drivers': retirement_group or
                           ([row['first_retirement_driver']] if row['first_retirement_driver'] else [])})
    return result


async def applied_round_for_notification(identifier):
    """Return a verified applied recovery; incomplete rounds cannot be announced as updated."""
    async with connection() as conn:
        row = await (await conn.execute(
            "SELECT r.state,r.season,r.round,p.event_name,p.fastest_lap_driver,p.first_retirement_driver,p.safety_car "
            "FROM prediction_recovery r JOIN prediction_round_results p ON p.season=r.season AND p.round=r.round "
            "WHERE r.id=?", (identifier,),
        )).fetchone()
    if row is None or row['state'] != 'applied':
        raise ValueError('Сначала примените проверенный пересчёт.')
    if any(row[key] is None for key in FIELDS):
        raise ValueError('Дополнительные факты гонки ещё неполные. Повторная рассылка недоступна.')
    return row['season'], row['round'], row['event_name']


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
