"""Private season summaries and opt-in score-only leagues."""
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from app.services import prediction_service as predictions


def previous_places(entries, before_round):
    """Reconstruct the same points/wins/best/name tie-break before a round."""
    rows = [{**e, "history": [h for h in e["history"] if h["round"] < before_round]} for e in entries]
    best = {}
    for e in rows:
        for h in e["history"]:
            best[h["round"]] = max(best.get(h["round"], 0), h["points"])
    def key(e):
        points = [h["points"] for h in e["history"]]
        wins = sum(h["points"] > 0 and h["points"] == best[h["round"]] for h in e["history"])
        return (-sum(points), -wins, -max(points, default=0), e["display_name"].casefold())
    return {e["user_id"]: i for i, e in enumerate(sorted(rows, key=key), 1) if e["history"]}


async def personal_season(user_id: int):
    board = await predictions.get_prediction_leaderboard()
    own = next((e for e in board["entries"] if e["user_id"] == user_id), None)
    history = own["history"] if own else []
    reviews = [await predictions.get_personal_prediction_review(user_id, r["season"], r["round"]) for r in history]
    categories = {}
    for review in reviews:
        for item in (review or {}).get("items", []):
            if item["status"] not in {"exact", "partial", "miss"}:
                continue
            category = categories.setdefault(item["key"], {"label": item["label"], "exact": 0, "known": 0})
            category["known"] += 1
            category["exact"] += int(item["status"] == "exact")
    achievements = []
    db = predictions.db
    saved = await (await db.conn.execute("SELECT 1 FROM race_predictions WHERE user_id=? LIMIT 1", (user_id,))).fetchone()
    if saved:
        achievements.append("Первый сохранённый прогноз")
    if any(all(any(i["key"] == k and i["status"] == "exact" for i in (r or {}).get("items", [])) for k in ("winner_driver", "second_driver", "third_driver")) for r in reviews):
        achievements.append("Точно угаданный подиум")
    last_round = max((r["round"] for r in board["rounds"]), default=None)
    previous = previous_places(board["entries"], last_round) if last_round else {}
    higher = [e["total_points"] - own["total_points"] for e in board["entries"] if own and e["total_points"] > own["total_points"]]
    return {"season": board["season"], "history": history, "best_points": own["best_points"] if own else None,
            "average_points": own["average_points"] if history else None, "place": own["place"] if own and history else None,
            "categories": list(categories.values()), "achievements": achievements,
            "latest": reviews[-1] if reviews else None,
            "place_change": previous[user_id] - own["place"] if own and user_id in previous else None,
            "gap_to_higher": min(higher) if higher else None,
            "previous_points": history[-2]["points"] if len(history) > 1 else None}


async def _connection():
    db = predictions.db
    if not db.conn:
        await db.connect()
    return db


async def list_leagues(user_id: int):
    db = await _connection()
    rows = await (await db.conn.execute(
        "SELECT l.id,l.name,l.owner_id,l.invite_token,l.invite_expires FROM prediction_leagues l "
        "JOIN prediction_league_members m ON m.league_id=l.id WHERE m.user_id=? ORDER BY l.id DESC", (user_id,)
    )).fetchall()
    return [{"id": r["id"], "name": r["name"], "owner": r["owner_id"] == user_id,
             "invite_token": r["invite_token"] if r["owner_id"] == user_id else None,
             "invite_expires": r["invite_expires"] if r["owner_id"] == user_id else None} for r in rows]


async def create_league(user_id: int, name: str):
    name = " ".join(name.split())
    if not 2 <= len(name) <= 50:
        raise ValueError("Название должно содержать от 2 до 50 символов")
    if not (await predictions.get_prediction_profile(user_id))["completed"]:
        raise ValueError("Сначала задайте имя участника в прогнозах")
    db = await _connection()
    async with db.write_lock:
        try:
            count = await (await db.conn.execute("SELECT COUNT(*) FROM prediction_leagues WHERE owner_id=?", (user_id,))).fetchone()
            if count[0] >= 10:
                raise ValueError("Можно создать не более 10 лиг")
            cursor = await db.conn.execute(
                "INSERT INTO prediction_leagues(name,owner_id,invite_token,invite_expires) VALUES(?,?,?,?)",
                (name, user_id, secrets.token_urlsafe(32), (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()))
            league_id = cursor.lastrowid
            await db.conn.execute("INSERT INTO prediction_league_members(league_id,user_id) VALUES(?,?)", (league_id, user_id))
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise
    return {"id": league_id}


async def join_league(user_id: int, token: str):
    if not (await predictions.get_prediction_profile(user_id))["completed"]:
        raise ValueError("Сначала задайте имя участника в прогнозах")
    db = await _connection()
    async with db.write_lock:
        try:
            league = await (await db.conn.execute("SELECT id FROM prediction_leagues WHERE invite_token=? AND invite_expires>?", (token, datetime.now(timezone.utc).isoformat()))).fetchone()
            if not league:
                raise ValueError("Приглашение недействительно или истекло")
            existing = await (await db.conn.execute("SELECT 1 FROM prediction_league_members WHERE league_id=? AND user_id=?", (league["id"], user_id))).fetchone()
            if not existing:
                count = await (await db.conn.execute("SELECT COUNT(*) FROM prediction_league_members WHERE league_id=?", (league["id"],))).fetchone()
                if count[0] >= 100:
                    raise ValueError("В лиге уже 100 участников")
                await db.conn.execute("INSERT INTO prediction_league_members(league_id,user_id) VALUES(?,?)", (league["id"], user_id))
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise
    return {"id": league["id"]}


async def league_scores(user_id: int, league_id: int):
    db = await _connection()
    member = await (await db.conn.execute("SELECT 1 FROM prediction_league_members WHERE league_id=? AND user_id=?", (league_id, user_id))).fetchone()
    if not member:
        raise PermissionError("Лига доступна только её участникам")
    members = {r[0] for r in await (await db.conn.execute("SELECT user_id FROM prediction_league_members WHERE league_id=?", (league_id,))).fetchall()}
    board = deepcopy(await predictions.get_prediction_leaderboard())
    board["entries"] = [e for e in board["entries"] if e["user_id"] in members]
    latest = max((h["round"] for e in board["entries"] for h in e["history"]), default=None)
    current_places = previous_places(board["entries"], latest + 1) if latest else {}
    board["entries"].sort(key=lambda e: (current_places.get(e["user_id"], float('inf')), e["display_name"].casefold()))
    for place, entry in enumerate(board["entries"], 1):
        entry["place"] = place
    previous = previous_places(board["entries"], latest) if latest else {}
    for entry in board["entries"]:
        entry["place_change"] = previous[entry["user_id"]] - entry["place"] if entry["user_id"] in previous else None
    # Leaderboard contains scores only; never serialize race_predictions rows here.
    return board


async def manage_league(user_id: int, league_id: int, action: str):
    db = await _connection()
    async with db.write_lock:
        try:
            league = await (await db.conn.execute("SELECT owner_id FROM prediction_leagues WHERE id=?", (league_id,))).fetchone()
            if not league:
                raise PermissionError("Лига недоступна")
            if action == "rotate":
                if league[0] != user_id:
                    raise PermissionError("Только создатель может обновить приглашение")
                await db.conn.execute("UPDATE prediction_leagues SET invite_token=?,invite_expires=? WHERE id=?", (secrets.token_urlsafe(32), (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(), league_id))
            elif action == "leave":
                if league[0] == user_id:
                    raise ValueError("Создатель не может покинуть собственную лигу")
                await db.conn.execute("DELETE FROM prediction_league_members WHERE league_id=? AND user_id=?", (league_id, user_id))
            await db.conn.commit()
        except Exception:
            await db.conn.rollback()
            raise
    return {"status": "ok"}
