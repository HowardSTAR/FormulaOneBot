"""Public racing profiles; subscription rights are always resolved server-side."""
from datetime import datetime, timezone

from app.db import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile_styles (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 frame TEXT NOT NULL DEFAULT 'classic',
 color TEXT NOT NULL DEFAULT 'white',
 background TEXT NOT NULL DEFAULT 'carbon'
);
"""
OPTIONS = {
    'frame': {'classic': 0, 'red': 2, 'silver': 2, 'gold': 3, 'neon': 3},
    'color': {'white': 0, 'red': 2, 'blue': 2, 'gold': 3, 'mint': 3},
    'background': {'carbon': 0, 'grid': 2, 'scarlet': 2, 'aurora': 3, 'champion': 3},
}
TIER_NAMES = ['Участник', 'На старт', 'Свой стиль', 'Полный газ']


async def identities(database=None):
    database = database or db
    from app.api.boosty_api import get_boosty_service
    service = get_boosty_service()
    rows = await (await database.conn.execute("""
        SELECT u.id, u.email, u.email_verified, u.telegram_id, pp.display_name AS prediction_name,
               u.display_name, bm.active, bm.level_name, po.active AS manual,
               s.frame, s.color, s.background
        FROM users u LEFT JOIN prediction_profiles pp ON pp.user_id=u.id
        LEFT JOIN boosty_memberships bm ON bm.user_id=u.id AND bm.blog=?
        LEFT JOIN premium_overrides po ON po.user_id=u.id
        LEFT JOIN user_profile_styles s ON s.user_id=u.id
        WHERE u.archived_at IS NULL
    """, (service.blog,))).fetchall()
    result = {}
    for row in rows:
        user = dict(row)
        tier = 0
        if user['manual'] is not None:
            tier = 3 if user['manual'] else 0
        elif user['active'] and user['email_verified'] and service.eligible(user):
            tier = {'на старт': 1, 'свой стиль': 2, 'полный газ': 3}.get(
                (user['level_name'] or '').strip().casefold(), 1)
        style = {key: user[key] if user[key] in options and options[user[key]] <= tier
                 else next(iter(options)) for key, options in OPTIONS.items()}
        result[user['id']] = {'user_id': user['id'],
            'display_name': user['prediction_name'] or user['display_name'] or f"Участник #{user['id']}",
            'tier': tier, 'tier_name': TIER_NAMES[tier], 'supporter': tier > 0, 'style': style}
    return result


async def profile(user_id, viewer_id, season=None):
    people = await identities()
    if user_id not in people:
        return None
    user = await (await db.conn.execute('SELECT telegram_id FROM users WHERE id=?', (user_id,))).fetchone()
    if season is None:
        season = datetime.now(timezone.utc).year
    own = user_id == viewer_id
    # Only publish scored answers. Pending predictions belong to their author.
    rows = await (await db.conn.execute("""
        SELECT p.*, r.event_name FROM race_predictions p
        LEFT JOIN prediction_round_results r ON r.season=p.season AND r.round=p.round
        WHERE p.user_id=? AND p.season=? AND (p.points IS NOT NULL OR ?)
        ORDER BY p.round DESC
    """, (user_id, season, own))).fetchall()
    predictions = [{k: v for k, v in dict(row).items() if k not in {'user_id', 'breakdown_json'}} for row in rows]
    scored = [p for p in predictions if p['points'] is not None]
    best = max(scored, key=lambda p: (p['points'], -p['round']), default=None)
    records = []
    visibility = '' if own else 'AND EXISTS (SELECT 1 FROM reaction_leaderboard_profiles WHERE telegram_id=? AND leaderboard_opt_in=1)'
    args = (user['telegram_id'],) if own else (user['telegram_id'], user['telegram_id'])
    records = [dict(row) for row in await (await db.conn.execute(f"""
        SELECT track_id, MIN(time_ms) AS best_time_ms, COUNT(*) AS attempts
        FROM race_game_scores WHERE telegram_id=? {visibility} GROUP BY track_id ORDER BY track_id
    """, args)).fetchall()]
    seasons = [r[0] for r in await (await db.conn.execute(
        'SELECT DISTINCT season FROM race_predictions WHERE user_id=? AND (points IS NOT NULL OR ?) ORDER BY season DESC',
        (user_id, own))).fetchall()]
    from app.race_rules import TRACKS
    for record in records:
        record['track_name'] = TRACKS.get(record['track_id'], {}).get('name', 'Emerald Loop' if record['track_id'] == 'emerald-loop-v1' else record['track_id'])
    return {**people[user_id], 'is_owner': own, 'season': season, 'seasons': sorted(set(seasons + [season]), reverse=True),
            'best_prediction': best, 'predictions': predictions, 'records': records,
            'total_points': sum(p['points'] for p in scored), 'scored_rounds': len(scored), 'options': OPTIONS}


async def save_style(user_id, values):
    person = (await identities())[user_id]
    for key, value in values.items():
        if value not in OPTIONS[key]:
            raise ValueError('Неизвестный вариант оформления')
        if OPTIONS[key][value] > person['tier']:
            raise PermissionError('Этот вариант недоступен на вашем уровне подписки')
    async with db.write_lock:
        await db.conn.execute('''INSERT INTO user_profile_styles(user_id,frame,color,background) VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET frame=excluded.frame,color=excluded.color,background=excluded.background''',
            (user_id, values['frame'], values['color'], values['background']))
        await db.conn.commit()


async def supporter_league(user_id, season=None):
    people = await identities()
    if not people[user_id]['supporter']:
        raise PermissionError('Лига доступна с уровня «На старт»')
    from app.services.prediction_service import get_prediction_leaderboard
    board = await get_prediction_leaderboard(season)
    entries = [e for e in board['entries'] if people.get(e['user_id'], {}).get('supporter')]
    return {'season': board['season'], 'entries': [{**e, 'place': i} for i, e in enumerate(entries, 1)]}
