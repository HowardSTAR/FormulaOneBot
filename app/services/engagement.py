"""Opt-in public score cards, verified racing challenges and first-touch referrals.

Public payloads are curated on the server. Neither prediction choices, account IDs,
emails nor invitation credentials are included in a card's public JSON.
"""
import asyncio
import io
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from PIL import Image, ImageDraw, ImageFont
import aiohttp

from app.db import db
from app.race_rules import TRACKS

SCHEMA = """
CREATE TABLE IF NOT EXISTS engagement_shares (
    token TEXT PRIMARY KEY, owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, payload TEXT NOT NULL, target TEXT NOT NULL,
    created REAL NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
    score_id INTEGER REFERENCES race_game_scores(id) ON DELETE CASCADE,
    league_id INTEGER REFERENCES prediction_leagues(id) ON DELETE CASCADE,
    invite_token TEXT
);
CREATE INDEX IF NOT EXISTS engagement_shares_owner ON engagement_shares(owner_id,created);
CREATE TABLE IF NOT EXISTS engagement_referrals (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    referrer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL REFERENCES engagement_shares(token) ON DELETE CASCADE,
    created REAL NOT NULL, activated REAL, activity TEXT,
    season INTEGER, round INTEGER, returned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS race_challenge_entries (
    token TEXT NOT NULL REFERENCES engagement_shares(token) ON DELETE CASCADE,
    score_id INTEGER NOT NULL REFERENCES race_game_scores(id) ON DELETE CASCADE,
    telegram_id INTEGER NOT NULL, PRIMARY KEY(token,telegram_id)
);
CREATE TABLE IF NOT EXISTS engagement_events (
    token TEXT NOT NULL REFERENCES engagement_shares(token) ON DELETE CASCADE,
    visitor TEXT NOT NULL, event TEXT NOT NULL, bucket INTEGER NOT NULL,
    created REAL NOT NULL, PRIMARY KEY(token,visitor,event,bucket)
);
CREATE INDEX IF NOT EXISTS engagement_events_created ON engagement_events(created);
"""
TOKEN_PATTERN = r"[A-Za-z0-9_-]{32}"
logger = logging.getLogger(__name__)
_username_lock = asyncio.Lock()
_username_cache = (None, None, 0)


def public_origin():
    base = next((os.getenv(k, "").strip() for k in ("PUBLIC_WEB_URL", "MINI_APP_URL", "FRONTEND_URL") if os.getenv(k, "").strip()), "")
    try:
        parts = urlsplit(base)
        parts.port
    except ValueError:
        return None
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def bot_username():
    """Resolve a public bot name once; never expose its credential on failure."""
    global _username_cache
    configured = (os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME') or '').lstrip('@')
    if re.fullmatch(r'[A-Za-z0-9_]{5,32}', configured):
        return configured
    credential = os.getenv('BOT_TOKEN')
    origin = public_origin()
    # Local previews and tests do not need to contact Telegram.
    if not credential or not origin or not origin.startswith('https://'):
        return None
    async with _username_lock:
        if _username_cache[0] == credential and _username_cache[2] > time.time():
            return _username_cache[1]
        username = None
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get(f'https://api.telegram.org/bot{credential}/getMe') as response:
                    data = await response.json()
            candidate = data.get('result', {}).get('username') if data.get('ok') else None
            if isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9_]{5,32}', candidate):
                username = candidate
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, AttributeError):
            logger.warning('Bot public name unavailable; sharing keeps its website fallback')
        _username_cache = (credential, username, time.time() + (3600 if username else 600))
        return username


def links(token, origin=None, username=None):
    origin = public_origin() or origin
    web = f"{origin}/share/{token}" if origin else f"/share/{token}"
    username = username or (os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "").lstrip("@")
    mini = f"https://t.me/{username}?startapp=share_{token}" if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) else None
    return {"web_url": web, "mini_app_url": mini, "share_url": mini or web,
            "image_url": f"{origin}/api/engagement/shares/{token}/image.jpg" if origin else f"/api/engagement/shares/{token}/image.jpg"}


async def row(token):
    if not re.fullmatch(TOKEN_PATTERN, token):
        raise ValueError("Карточка не найдена")
    result = await (await db.conn.execute("SELECT * FROM engagement_shares WHERE token=? AND revoked=0 AND expires>?", (token, time.time()))).fetchone()
    if result is None:
        raise ValueError("Ссылка истекла или отозвана")
    result = dict(result)
    if result["league_id"]:
        invite = await (await db.conn.execute("SELECT invite_token,invite_expires FROM prediction_leagues WHERE id=?", (result["league_id"],))).fetchone()
        if not invite or invite["invite_token"] != result["invite_token"] or invite["invite_expires"] <= datetime.now(timezone.utc).isoformat():
            raise ValueError("Приглашение истекло или заменено")
    if result["score_id"]:
        profile = await (await db.conn.execute("SELECT p.leaderboard_opt_in FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id) WHERE s.id=?", (result["score_id"],))).fetchone()
        if not profile or not profile[0]:
            raise ValueError("Участник отключил публикацию игровых результатов")
    return result


async def public_share(token, origin=None):
    result = await row(token)
    return {"token": token, "kind": result["kind"], **json.loads(result["payload"]),
            "created": result["created"], "expires": result["expires"], **links(token, origin, await bot_username())}


def time_label(milliseconds):
    return f"{milliseconds // 60000:02}:{milliseconds // 1000 % 60:02}.{milliseconds % 1000:03}"


async def create_share(user_id, kind, options):
    from app.services import prediction_service as predictions
    payload, target, score_id, league_id, invite = {}, "", None, None, None
    now = time.time()
    if kind in {"prediction", "race", "league"} and user_id is None:
        raise PermissionError("Войдите, чтобы поделиться личным результатом")
    if kind == "prediction":
        review = await predictions.get_personal_prediction_review(user_id, options["season"], options["round"])
        if not review or review["points"] is None:
            raise ValueError("Прогноз ещё не рассчитан")
        profile = await predictions.get_prediction_profile(user_id)
        provisional = any(i["status"] == "unavailable" for i in review["items"])
        exact = [i["label"] for i in review["items"] if i["status"] == "exact"]
        payload = {"title": f"Мой прогноз · {review['event_name']}", "subtitle": profile["display_name"],
                   "headline": f"{review['points']} / {review['max_points']} очков", "provisional": provisional,
                   "lines": (["Предварительный результат: часть данных ещё ожидается."] if provisional else [])
                   + (["Точно угадано: " + ", ".join(exact[:4])] if exact else ["Каждый этап — новая возможность!"]),
                   "cta": "Попробовать прогноз", "season": options["season"], "round": options["round"]}
        history = await (await db.conn.execute("SELECT MAX(points) FROM race_predictions WHERE user_id=? AND season=? AND round<?", (user_id, options["season"], options["round"]))).fetchone()
        if not provisional and history[0] is not None and review["points"] > history[0]:
            payload["lines"].append("Мой лучший результат сезона по очкам!")
        payload['exact_count'] = len(exact)
        if not provisional:
            from app.services.prediction_social import previous_places
            board = await predictions.get_prediction_leaderboard(options['season'])
            before = previous_places(board['entries'], options['round'])
            after = previous_places(board['entries'], options['round'] + 1)
            if user_id in after:
                payload['rank_text'] = f"Позиция после этапа: #{after[user_id]}"
                if user_id in before:
                    change = before[user_id] - after[user_id]
                    payload['rank_text'] += f" · {'+' if change > 0 else ''}{change}"
                payload['rank_text'] += ' · по текущему пересчитанному зачёту'
        target = "/predictions"
    elif kind == "race":
        account = await (await db.conn.execute("SELECT telegram_id FROM users WHERE id=?", (user_id,))).fetchone()
        if not account or not account[0]:
            raise ValueError("Привяжите Telegram, чтобы отправить игровой вызов")
        score = await (await db.conn.execute("SELECT s.*,p.display_name FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id) WHERE s.telegram_id=? AND s.track_id=? AND p.leaderboard_opt_in=1 AND s.telemetry_json IS NOT NULL ORDER BY s.time_ms,s.id LIMIT 1", (account[0], options["track_id"]))).fetchone()
        if not score or score["track_id"] not in TRACKS:
            raise ValueError("Сначала завершите и сохраните заезд на этой трассе")
        score_id = score["id"]
        payload = {"title": "Побей моё время", "subtitle": score["display_name"],
                   "headline": time_label(score["time_ms"]), "lines": [TRACKS[score["track_id"]]["name"], "Три круга · со столкновениями · без возврата на трассу"],
                   "cta": "Принять вызов", "track_id": score["track_id"], "time_ms": score["time_ms"], "provisional": False}
        target = "/race-game"
    elif kind == "league":
        league = await (await db.conn.execute("SELECT * FROM prediction_leagues WHERE id=? AND owner_id=?", (options["league_id"], user_id))).fetchone()
        if not league:
            raise PermissionError("Приглашать может создатель лиги")
        league_id, invite = league["id"], league["invite_token"]
        payload = {"title": "Кто лучше разбирается в F1?", "subtitle": league["name"], "headline": "Присоединяйся к нашей лиге",
                   "lines": ["Сравниваем очки, не раскрываем ответы.", "Мини-чемпионат на 3 этапа" if league["mode"] == "cup" else "Сезонный зачёт"], "cta": "Посмотреть приглашение", "provisional": False}
        target = "/predictions?tab=leagues"
    elif kind == "recap":
        from app.services.race_recap import get_race_recap
        recap = await get_race_recap(options["season"], options["round"])
        if not recap.get("items") or recap["status"] == "waiting":
            raise ValueError("Рекап пока не готов")
        payload = {"title": "Главное после гонки", "subtitle": f"{options['season']} · этап {options['round']}",
                   "headline": recap["items"][0]["title"], "lines": [i["text"] for i in recap["items"][:3]],
                   "cta": "Посмотреть результаты", "provisional": recap["status"] != "ready", "season": options["season"], "round": options["round"]}
        target = "/race-results?" + urlencode({"season": options["season"], "round": options["round"], "mode": "archive"})
    elif kind == "history":
        from app.services.standings_history import get_standings_history
        history = await get_standings_history(options["history_kind"], options["ids"], options["start_year"], options["end_year"])
        if not history.get("series") or not any(y.get("standing") for s in history["series"] for y in s["seasons"]):
            raise ValueError("Нет подтверждённых данных для сравнения")
        provisional = any(y.get('current') or y.get('status') == 'unavailable' for s in history['series'] for y in s['seasons'])
        payload = {"title": "История чемпионата", "subtitle": f"{options['start_year']}–{options['end_year']}",
                   "headline": " / ".join(s["name"] for s in history["series"]),
                   "lines": ["Места в зачёте по сезонам. Очки разных эпох напрямую несопоставимы."] + (["Текущий сезон — промежуточный; недоступные данные не заменяются нулями."] if provisional else []), "cta": "Открыть сравнение", "provisional": provisional,
                   "chart": [{"name": s["name"], "values": [{"year": y["season"], "position": (y.get("standing") or {}).get("position")} for y in s["seasons"]]} for s in history["series"]]}
        target = "/history?" + urlencode({"kind": options["history_kind"], "ids": ",".join(options["ids"]), "from": options["start_year"], "to": options["end_year"]})
    else:
        raise ValueError("Неизвестный тип карточки")
    token = secrets.token_urlsafe(24)
    async with db.write_lock:
        count = await (await db.conn.execute("SELECT COUNT(*) FROM engagement_shares WHERE owner_id IS ? AND created>?", (user_id, now - 3600))).fetchone()
        if count[0] >= (30 if user_id else 100):
            raise ValueError("Слишком много карточек. Попробуйте позже.")
        await db.conn.execute("INSERT INTO engagement_shares(token,owner_id,kind,payload,target,created,expires,score_id,league_id,invite_token) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (token, user_id, kind, json.dumps(payload, ensure_ascii=False), target, now, now + 30 * 86400, score_id, league_id, invite))
        await db.conn.commit()
    return token


async def share_target(token):
    item = await row(token)
    if item["kind"] == "race":
        return f"/race-game?challenge={token}"
    if item["kind"] == "league":
        return item["target"] + "#invite=" + item["invite_token"]
    joiner = "&" if "?" in item["target"] else "?"
    return item["target"] + joiner + "via=" + token


async def arrival(user_id, token):
    item = await row(token)
    if user_id is None or item["owner_id"] is None or user_id == item["owner_id"]:
        return
    # Existing participants may accept challenges, but aren't acquired newcomers.
    old = await (await db.conn.execute("SELECT EXISTS(SELECT 1 FROM race_predictions WHERE user_id=?) OR EXISTS(SELECT 1 FROM race_game_scores WHERE telegram_id=(SELECT telegram_id FROM users WHERE id=?))", (user_id, user_id))).fetchone()
    async with db.write_lock:
        if not old[0]:
            await db.conn.execute("INSERT OR IGNORE INTO engagement_referrals(user_id,referrer_id,token,created) VALUES(?,?,?,?)", (user_id, item["owner_id"], token, time.time()))
        await db.conn.commit()


async def activate(user_id, activity, season=None, round_num=None, database=None):
    """Called ONLY after a real saved prediction or accepted game score."""
    now = time.time()
    storage = database or db
    async with storage.write_lock:
        try:
            await storage.conn.execute("UPDATE engagement_referrals SET activated=?,activity=?,season=?,round=? WHERE user_id=? AND activated IS NULL AND created>?", (now, activity, season, round_num, user_id, now - 30 * 86400))
            if activity == "prediction":
                await storage.conn.execute("UPDATE engagement_referrals SET season=?,round=? WHERE user_id=? AND activated IS NOT NULL AND season IS NULL", (season, round_num, user_id))
                await storage.conn.execute("UPDATE engagement_referrals SET returned=1 WHERE user_id=? AND (season<? OR (season=? AND round<?)) AND activated IS NOT NULL", (user_id, season, season, round_num))
            await storage.conn.commit()
        except Exception:
            await storage.conn.rollback()
            raise


async def activate_saved(*args, **kwargs):
    """Referral bookkeeping must never invalidate an already committed result."""
    try:
        await activate(*args, **kwargs)
    except Exception:
        logger.exception('Referral activation failed; the participant result remains saved')


async def challenge(token):
    item = await row(token)
    if item["kind"] != "race":
        raise ValueError("Это не игровой вызов")
    source = await (await db.conn.execute("SELECT s.*,p.display_name FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id) WHERE s.id=?", (item["score_id"],))).fetchone()
    entries = await (await db.conn.execute("SELECT p.display_name name,MIN(s.time_ms) time_ms FROM race_challenge_entries e JOIN race_game_scores s ON s.id=e.score_id JOIN reaction_leaderboard_profiles p ON p.telegram_id=e.telegram_id WHERE e.token=? AND p.leaderboard_opt_in=1 GROUP BY e.telegram_id,p.display_name ORDER BY time_ms LIMIT 100", (token,))).fetchall()
    return {"track_id": source["track_id"], "time_ms": source["time_ms"], "name": source["display_name"],
            "ghost": {"name": source["display_name"], "time_ms": source["time_ms"], "samples": json.loads(source["telemetry_json"]), "is_challenge": True},
            "entries": [dict(r) for r in entries]}


async def record_challenge(token, telegram_id, score_id):
    item = await row(token)
    if item["kind"] != "race":
        raise ValueError("Это не игровой вызов")
    score = await (await db.conn.execute("SELECT * FROM race_game_scores WHERE id=? AND telegram_id=?", (score_id, telegram_id))).fetchone()
    source = await (await db.conn.execute("SELECT track_id,time_ms FROM race_game_scores WHERE id=?", (item["score_id"],))).fetchone()
    if not score or score["track_id"] != source["track_id"] or not score["telemetry_json"]:
        raise ValueError("Трасса вызова не совпадает с заездом")
    async with db.write_lock:
        try:
            await db.conn.execute("INSERT INTO race_challenge_entries(token,telegram_id,score_id) VALUES(?,?,?) ON CONFLICT(token,telegram_id) DO UPDATE SET score_id=excluded.score_id WHERE (SELECT time_ms FROM race_game_scores WHERE id=excluded.score_id)<(SELECT time_ms FROM race_game_scores WHERE id=race_challenge_entries.score_id)", (token, telegram_id, score_id))
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise
    return {"difference_ms": score["time_ms"] - source["time_ms"], "beaten": score["time_ms"] < source["time_ms"]}


def weekly_period(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    tracks = list(TRACKS.values())
    # Stable absolute week rotation across New Year; server clock is authoritative.
    track = tracks[(start.date() - datetime(2026, 1, 5).date()).days // 7 % len(tracks)]
    return track, start, start + timedelta(days=7)


async def weekly(now=None):
    track, start, end = weekly_period(now)
    scores = await (await db.conn.execute("SELECT p.display_name name,MIN(s.time_ms) time_ms FROM race_game_scores s JOIN reaction_leaderboard_profiles p USING(telegram_id) WHERE s.track_id=? AND p.leaderboard_opt_in=1 AND datetime(s.created_at)>=datetime(?) AND datetime(s.created_at)<datetime(?) GROUP BY s.telegram_id,p.display_name ORDER BY time_ms,s.telegram_id LIMIT 50", (track["id"], start.isoformat(), end.isoformat()))).fetchall()
    return {"track_id": track["id"], "name": track["name"], "start": start.isoformat(), "end": end.isoformat(), "entries": [dict(r) for r in scores]}


async def personal_engagement(user_id):
    referrals = await (await db.conn.execute("SELECT COUNT(*) arrived,COUNT(activated) activated,COALESCE(SUM(returned),0) returned FROM engagement_referrals WHERE referrer_id=?", (user_id,))).fetchone()
    leagues = await (await db.conn.execute("SELECT COUNT(*) FROM prediction_leagues l WHERE owner_id=? AND (SELECT COUNT(*) FROM prediction_league_members m WHERE m.league_id=l.id)>1", (user_id,))).fetchone()
    accepted = await (await db.conn.execute("SELECT COUNT(DISTINCT e.telegram_id) FROM race_challenge_entries e JOIN engagement_shares s ON s.token=e.token JOIN users u ON u.id=s.owner_id WHERE s.owner_id=? AND e.telegram_id<>COALESCE(u.telegram_id,0)", (user_id,))).fetchone()
    badges = []
    if leagues[0]: badges.append("Собрал первую лигу")
    if accepted[0]: badges.append("Друг принял вызов")
    if referrals["activated"] >= 3: badges.append("Привёл трёх участников")
    shares = await (await db.conn.execute("SELECT token,kind,created,expires,revoked,payload FROM engagement_shares WHERE owner_id=? ORDER BY created DESC LIMIT 30", (user_id,))).fetchall()
    cards = []
    for item in shares:
        active = not item['revoked'] and item['expires'] > time.time()
        if active:
            try:
                await row(item['token'])
            except ValueError:
                active = False
        cards.append({'token': item['token'], 'kind': item['kind'], 'title': json.loads(item['payload'])['title'], 'active': active})
    return {"referrals": dict(referrals), "badges": badges, "shares": cards}


async def record_event(token, visitor, event):
    await row(token)
    async with db.write_lock:
        now = time.time()
        await db.conn.execute("INSERT OR IGNORE INTO engagement_events VALUES(?,?,?,?,?)", (token, visitor, event, int(now) // 300, now))
        await db.conn.execute("DELETE FROM engagement_events WHERE created<?", (now - 366 * 86400,))
        await db.conn.commit()


def card_image(payload):
    """Portable JPG (Telegram inline photos require JPEG), no external assets."""
    root = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    font = lambda size, bold=False: ImageFont.truetype(str(root / ("Jost-Bold.ttf" if bold else "Jost-Regular.ttf")), size)
    image = Image.new("RGB", (1200, 630), "#0d1219")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((26, 26, 1174, 604), 24, fill="#151c27", outline="#354153", width=2)
    draw.polygon(((780, 28), (940, 28), (620, 602), (460, 602)), fill='#1c2735')
    draw.polygon(((965, 28), (995, 28), (675, 602), (645, 602)), fill='#1c2735')
    draw.rectangle((52, 60, 60, 545), fill="#ff4e46")
    draw.text((90, 53), "F1Hub", font=font(36, True), fill="#ff6259")
    draw.text((1090, 65), "ПРЕДВАРИТЕЛЬНО" if payload.get('provisional') else "FANS", anchor="ra", font=font(18), fill="#e8c971" if payload.get('provisional') else "#a8b5c9")
    def fit(text, face, width):
        if draw.textlength(text, font=face) <= width:
            return text
        while text and draw.textlength(text + '…', font=face) > width:
            text = text[:-1]
        return text.rstrip() + '…'
    def wrapped(text, y, size, color, max_lines=3, bold=False):
        face, line, lines = font(size, bold), "", []
        for word in text.split():
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=face) > 990 and line:
                lines.append(line); line = word
            else: line = candidate
        if line: lines.append(line)
        max_lines = min(max_lines, max(0, (526 - y) // (size + 7)))
        for index, line in enumerate(lines[:max_lines]):
            if index == max_lines - 1 and len(lines) > max_lines: line += "…"
            line = fit(line, face, 990)
            draw.text((90, y), line, font=face, fill=color); y += size + 7
        return y
    chart = payload.get("chart")
    y = wrapped(payload["title"], 115, 29, "#c6d1df", 1 if chart else 2)
    y = wrapped(payload["headline"], y + 8, 32 if chart else 72 if payload.get('kind') in {'prediction', 'race'} else 46, "#ffffff", 2, True)
    y = wrapped(payload.get("subtitle", ""), y + 4, 24, "#a7b7c8", 1)
    if chart:
        values = [v["position"] for s in chart for v in s["values"] if v["position"]]
        maximum = max(10, *values)
        colors = ["#ff6259", "#53d2cd", "#e8c971"]
        top = 335
        for i, series in enumerate(chart):
            draw.text((90 + i * 340, 296), fit(series['name'], font(18), 315), font=font(18), fill=colors[i])
        draw.line((100, top, 1070, top), fill='#354153', width=1)
        draw.line((100, top + 135, 1070, top + 135), fill='#354153', width=1)
        for i, series in enumerate(chart):
            previous = None
            for j, value in enumerate(series["values"]):
                x = 100 + j * 970 / max(1, len(series["values"]) - 1)
                if not value["position"]: previous = None; continue
                point = (x, top + (value["position"] - 1) * 135 / max(1, maximum - 1))
                if previous: draw.line((previous, point), fill=colors[i], width=4)
                draw.ellipse((point[0]-5,point[1]-5,point[0]+5,point[1]+5),fill=colors[i]); previous=point
        years = [value['year'] for series in chart for value in series['values']]
        draw.text((100, 477), str(min(years)), font=font(18), fill='#a7b7c8')
        draw.text((1070, 477), str(max(years)), anchor='ra', font=font(18), fill='#a7b7c8')
        draw.text((90, 513), "P1 сверху · пропуски данных не соединяются · очки разных эпох несопоставимы", font=font(17), fill="#a7b7c8")
    else:
        for line in payload["lines"][:3]:
            if y > 470: break
            y = wrapped(line, y + 13, 25, "#d2dce7", 2)
        if payload.get('kind') == 'prediction':
            y = wrapped(payload.get('rank_text', ''), y + 12, 22, '#a7b7c8', 2)
            if y < 425:
                draw.rounded_rectangle((90, 437, 535, 517), 12, fill='#202f3d')
                draw.text((110, 451), str(payload.get('exact_count', 0)), font=font(36, True), fill='#64d8c3')
                draw.text((180, 461), 'ТОЧНЫХ ПОПАДАНИЙ', font=font(21, True), fill='#c6d1df')
        elif payload.get('kind') == 'race' and payload.get('track_id') in TRACKS:
            points = TRACKS[payload['track_id']]['centerLine']
            min_x, min_y = min(p[0] for p in points), min(p[1] for p in points)
            scale = min(310 / (max(p[0] for p in points) - min_x), 120 / (max(p[1] for p in points) - min_y))
            draw.line([(755 + (x-min_x)*scale, 392 + (y-min_y)*scale) for x,y in [*points, points[0]]], fill='#64d8c3', width=5, joint='curve')
    draw.text((90, 548), payload["cta"] + " →", font=font(26, True), fill="#64d8c3")
    draw.text((1110, 553), "f1hub.ru", anchor="ra", font=font(22), fill="#a7b7c8")
    output = io.BytesIO(); image.save(output, "JPEG", quality=90)
    return output.getvalue()
