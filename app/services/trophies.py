"""Permanent, server-awarded trophies and acknowledged celebration receipts."""
import asyncio
from datetime import datetime, timezone

from app.db import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_trophies (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 family TEXT NOT NULL,
 season INTEGER NOT NULL DEFAULT 0,
 level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 2),
 earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 seen_at TEXT,
 PRIMARY KEY(user_id,family,season,level)
);
CREATE TABLE IF NOT EXISTS user_trophy_badges (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 family TEXT NOT NULL,
 season INTEGER NOT NULL,
 level INTEGER NOT NULL,
 FOREIGN KEY(user_id,family,season,level)
  REFERENCES user_trophies(user_id,family,season,level) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS trophy_support_periods (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 start REAL NOT NULL,
 end REAL NOT NULL CHECK(end>=start),
 PRIMARY KEY(user_id,start,end)
);
"""
TIERS = ['Бронза', 'Серебро', 'Золото']
FAMILIES = {
    'oracle': ('Оракул паддока', 'Прогнозы', [1, 5, 15]),
    'podium': ('Идеальная тройка', 'Прогнозы', [1, 3, 7]),
    'rhythm': ('В ритме сезона', 'Участие', [3, None, None]),
    'lights': ('Пять огней', 'Реакция', [3, 3, 3]),
    'ghost': ('Быстрее своей тени', 'Гонка', [3, 10, 25]),
    'atlas': ('Без границ', 'Исследование', [1, 2, 3]),
    'grid': ('Дирижёр сетки', 'Reflex Grid', [10, 15, 20]),
    'heart': ('Сердце проекта', 'Поддержка', [30, 90, 365]),
}
RULES = {
    'oracle': 'Только рассчитанные прогнозы основной гонки. Спринты исключены. Верный победитель учитывается один раз за этап.',
    'podium': 'Весь подиум должен совпасть в правильном порядке в одной основной гонке. Разрозненные верные позиции не складываются.',
    'rhythm': 'Только рассчитанные прогнозы текущего сезона, поданные до дедлайна. Бронза — 3 этапа, серебро — половина актуального календаря с округлением вверх, золото — все этапы после окончания сезона. Отменённые этапы исключаются из цели и прогресса. Добавленные увеличивают цель. Выданные награды сохраняются с годом сезона.',
    'lights': 'Три сохранённых успешных старта с реакцией не медленнее порога. Не обязательно подряд. Более быстрые старты подходят предыдущим уровням.',
    'ghost': 'Полный валидный заезд из трёх кругов на той же версии трассы. Первый результат создаёт базу и не считается. Следующие сравниваются с предыдущим подтверждённым личным рекордом: время ≤ рекорд × 1,05. Повторять результат можно, улучшать рекорд не обязательно. Счётчики разных трасс складываются.',
    'atlas': 'Нужен сохранённый результат в каждой игре: тест реакции, Emerald Loop, Reflex Grid. Режимы одной игры не считаются разными играми.',
    'grid': 'Одна сохранённая попытка: режим «По времени», 10 секунд, сложность «Средний 4×4». Результаты попыток не складываются. Более высокий результат подходит предыдущим уровням.',
    'heart': 'Суммарное подтверждённое оплаченное время поддержки Boosty с момента начала учёта. Пересекающиеся периоды не удваиваются. Перерыв не сбрасывает счётчик. Поддержка необязательна; выданные трофеи остаются навсегда.',
}


def award_id(family, season, level):
    return f'{family}:{season}:{level}'


def condition(family, target, level, season):
    if family == 'rhythm':
        if target is None:
            return f'Календарь сезона {season} уточняется.'
        label = ['разных Гран-при', 'Гран-при — половину календаря', 'Гран-при — весь сезон'][level]
        return f'Сделать прогноз на {target} {label} сезона {season}.' + (' Награда после завершения сезона.' if level == 2 else '')
    return {
        'oracle': f'Угадать победителя в {target} Гран-при.',
        'podium': f'Угадать весь подиум в правильном порядке в {target} Гран-при.',
        'lights': f'Показать реакцию ≤ {[350, 280, 220][level]} мс в 3 успешных стартах.',
        'ghost': f'Завершить {target} заездов не более чем на 5% медленнее личного рекорда.',
        'atlas': f'Получить зачтённый результат в {target} разных играх.',
        'grid': f'Набрать {target} попаданий за 10 секунд на сетке 4×4.',
        'heart': f'Поддерживать TurboTears суммарно {target} дней.',
    }[family]


def support_days(periods, now):
    """Union confirmed paid intervals, capped at now; no invented past tenure."""
    seconds, finish = 0, 0
    for start, end in sorted(periods):
        end = min(end, now)
        start = max(start, finish)
        if end > start:
            seconds += end - start
            finish = end
    return int(seconds // 86400)


async def calendar_for(season):
    from app.f1_data import get_season_schedule_short_async
    try:
        return await asyncio.wait_for(get_season_schedule_short_async(season), timeout=5)
    except Exception:
        # A missing calendar cannot justify a guessed half/full-season target.
        return []


async def progress_for(user_id, season, schedule, now):
    user = await (await db.conn.execute('SELECT telegram_id FROM users WHERE id=? AND archived_at IS NULL', (user_id,))).fetchone()
    if not user:
        raise ValueError('Профиль не найден')
    telegram_id = user['telegram_id']
    predictions = await (await db.conn.execute('''
        SELECT p.season,p.round,p.winner_driver=r.winner_driver AS winner,
        p.winner_driver=r.winner_driver AND p.second_driver=r.second_driver
        AND p.third_driver=r.third_driver AS podium
        FROM race_predictions p JOIN prediction_round_results r USING(season,round)
        WHERE p.user_id=? AND p.points IS NOT NULL AND r.winner_driver IS NOT NULL
    ''', (user_id,))).fetchall()
    active = {int(r['round']) for r in schedule if r.get('round') and not r.get('is_cancelled')}
    scored = {r['round'] for r in predictions if r['season'] == season}
    # Season completion requires every remaining main race to have a result,
    # plus time for the final race to finish. Forecast participation is separate.
    results = {r[0] for r in await (await db.conn.execute(
        'SELECT round FROM prediction_round_results WHERE season=? AND winner_driver IS NOT NULL', (season,))).fetchall()}
    starts = []
    for race in schedule:
        if race.get('is_cancelled'):
            continue
        try:
            start = datetime.fromisoformat(race['race_start_utc'].replace('Z', '+00:00'))
            starts.append(start.replace(tzinfo=timezone.utc).timestamp() if start.tzinfo is None else start.timestamp())
        except (KeyError, TypeError, ValueError):
            starts.append(float('inf'))
    closed = bool(active and active <= results and starts and max(starts) + 6 * 3600 <= now)
    reactions = [r[0] for r in await (await db.conn.execute(
        'SELECT time_ms FROM reaction_leaderboard_scores WHERE telegram_id=?', (telegram_id,))).fetchall()]
    races = await (await db.conn.execute('''SELECT track_id,time_ms FROM race_game_scores
        WHERE telegram_id=? AND telemetry_json IS NOT NULL ORDER BY id''', (telegram_id,))).fetchall()
    best, consistent = {}, 0
    for race in races:
        track, elapsed = race['track_id'], race['time_ms']
        if track in best and elapsed * 100 <= best[track] * 105:
            consistent += 1
        best[track] = min(best.get(track, elapsed), elapsed)
    reflex = await (await db.conn.execute('SELECT mode,difficulty,score,time_ms FROM reflex_grid_scores WHERE telegram_id=?', (telegram_id,))).fetchall()
    grid = max((r['score'] for r in reflex if r['mode'] == 'timed' and r['difficulty'] == 'medium' and r['time_ms'] == 10000), default=0)
    periods = await (await db.conn.execute('SELECT start,end FROM trophy_support_periods WHERE user_id=?', (user_id,))).fetchall()
    counts = {
        'oracle': [sum(bool(r['winner']) for r in predictions)] * 3,
        'podium': [sum(bool(r['podium']) for r in predictions)] * 3,
        'rhythm': [len(scored & active)] * 3,
        'lights': [sum(0 < t <= threshold for t in reactions) for threshold in [350, 280, 220]],
        'ghost': [consistent] * 3,
        'atlas': [sum([bool(reactions), bool(races), bool(reflex)])] * 3,
        'grid': [grid] * 3,
        'heart': [support_days([tuple(r) for r in periods], now)] * 3,
    }
    targets = {key: values[2] for key, values in FAMILIES.items()}
    targets['rhythm'] = [3, (len(active) + 1) // 2, len(active)] if active else [3, None, None]
    return counts, targets, closed, bool(active)


def serialize_award(row):
    family, season, level = row['family'], row['season'], row['level']
    return {'id': award_id(family, season, level), 'family': family, 'season': season,
            'level': level, 'name': FAMILIES[family][0], 'tier': TIERS[level],
            'earned_at': row['earned_at']}


async def collection(user_id, owner=False, *, schedule=None, now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    season = datetime.fromtimestamp(now, timezone.utc).year
    counts, targets, closed, calendar_known = {}, {}, False, False
    if owner:
        schedule = await calendar_for(season) if schedule is None else schedule
        counts, targets, closed, calendar_known = await progress_for(user_id, season, schedule, now)
        async with db.write_lock:
            try:
                for family in FAMILIES:
                    for level, target in enumerate(targets[family]):
                        if target is None or counts[family][level] < target:
                            continue
                        if family == 'rhythm' and (not calendar_known or level == 2 and not closed):
                            continue
                        await db.conn.execute('''INSERT OR IGNORE INTO user_trophies(user_id,family,season,level)
                            VALUES (?,?,?,?)''', (user_id, family, season if family == 'rhythm' else 0, level))
                await db.conn.commit()
            except BaseException:
                await db.conn.rollback()
                raise
    rows = await (await db.conn.execute('SELECT * FROM user_trophies WHERE user_id=? ORDER BY earned_at,family,season,level', (user_id,))).fetchall()
    earned = {(r['family'], r['season'], r['level']): r for r in rows}
    families = []
    for family, (name, group, default_targets) in FAMILIES.items():
        family_season = season if family == 'rhythm' else 0
        levels = []
        for level in range(3):
            row = earned.get((family, family_season, level))
            if not owner and row is None:
                continue
            target = targets.get(family, default_targets)[level]
            levels.append({'id': award_id(family, family_season, level), 'level': level, 'tier': TIERS[level],
                           'season': family_season, 'earned_at': row['earned_at'] if row else None,
                           **({'target': target, 'progress': counts[family][level],
                               'condition': condition(family, target, level, season), 'rule': RULES[family]} if owner else {})})
        if levels:
            families.append({'id': family, 'name': name, 'group': group, 'levels': levels})
    badge_row = await (await db.conn.execute('''SELECT t.* FROM user_trophy_badges b JOIN user_trophies t
        USING(user_id,family,season,level) WHERE b.user_id=?''', (user_id,))).fetchone()
    return {'user_id': user_id, 'season': season, 'calendar_known': calendar_known, 'season_closed': closed,
            'families': families, 'earned': [serialize_award(r) for r in rows],
            'pending': [serialize_award(r) for r in rows if r['seen_at'] is None] if owner else [],
            'badge': serialize_award(badge_row) if badge_row else None}


async def acknowledge(user_id, ids):
    async with db.write_lock:
        try:
            for receipt in ids:
                await db.conn.execute('''UPDATE user_trophies SET seen_at=COALESCE(seen_at,CURRENT_TIMESTAMP)
                    WHERE user_id=? AND family||':'||season||':'||level=?''', (user_id, receipt))
            await db.conn.commit()
        except BaseException:
            await db.conn.rollback()
            raise


async def select_badge(user_id, receipt):
    async with db.write_lock:
        try:
            if receipt is None:
                await db.conn.execute('DELETE FROM user_trophy_badges WHERE user_id=?', (user_id,))
            else:
                row = await (await db.conn.execute('''SELECT family,season,level FROM user_trophies
                    WHERE user_id=? AND family||':'||season||':'||level=?''', (user_id, receipt))).fetchone()
                if row is None:
                    raise PermissionError('Сначала откройте этот трофей')
                await db.conn.execute('''INSERT INTO user_trophy_badges VALUES (?,?,?,?) ON CONFLICT(user_id)
                    DO UPDATE SET family=excluded.family,season=excluded.season,level=excluded.level''', (user_id, *tuple(row)))
            await db.conn.commit()
        except BaseException:
            await db.conn.rollback()
            raise


async def transfer(conn, source, target):
    await conn.execute('''INSERT INTO user_trophies(user_id,family,season,level,earned_at,seen_at)
        SELECT ?,family,season,level,earned_at,seen_at FROM user_trophies WHERE user_id=?
        ON CONFLICT(user_id,family,season,level) DO UPDATE SET
        earned_at=MIN(user_trophies.earned_at,excluded.earned_at),
        seen_at=COALESCE(user_trophies.seen_at,excluded.seen_at)''', (target, source))
    await conn.execute('''INSERT OR IGNORE INTO user_trophy_badges SELECT ?,family,season,level
        FROM user_trophy_badges WHERE user_id=?''', (target, source))
    await conn.execute('INSERT OR IGNORE INTO trophy_support_periods SELECT ?,start,end FROM trophy_support_periods WHERE user_id=?', (target, source))
    for table in ['user_trophy_badges', 'user_trophies', 'trophy_support_periods']:
        await conn.execute(f'DELETE FROM {table} WHERE user_id=?', (source,))
