"""Post-race race-control chronology: fixed rules, not journalist text or AI.

The background job shares the prediction adapter's OpenF1 request limiter. Public
readers only use SQLite. This module never changes prediction facts or scores.
"""
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

import aiosqlite

from app.services import recap_news as news
from app.services.prediction_race_facts import (
    _cached_prediction_openf1_sessions, _openf1_race_session, _prediction_openf1_get,
    OpenF1SourceUnavailable,
)

logger = logging.getLogger(__name__)
SOURCE = "openf1-control"
SC_TEXT = "Выпущена машина безопасности — гонка проходит за машиной безопасности."
LEGACY_SC_TEXT = "Выпущена машина безопасности — гонка нейтрализована."


def display_title(title, source_id=SOURCE):
    # Final snapshots are not refetched. Update their wording at read time,
    # leaving stored provenance, moderation and publisher headlines unchanged.
    return title.replace(LEGACY_SC_TEXT, SC_TEXT) if source_id == SOURCE else title


def utc(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def select_events(rows, limit=4):
    """Keep major distinct messages, then display them in time order."""
    ordered = sorted(rows, key=lambda row: (-row["score"], row["published"], row["url"]))
    unique, seen = [], set()
    for row in ordered:
        key = (row["category"], row["title"])
        if key not in seen:
            unique.append(row)
            seen.add(key)
    selected, categories = [], set()
    for row in unique:
        if row["category"] not in categories:
            selected.append(row)
            categories.add(row["category"])
            if len(selected) == limit:
                break
    for row in unique:
        if len(selected) == limit:
            break
        if row not in selected:
            selected.append(row)
    return sorted(selected, key=lambda row: (row["published"], row["url"]))


def build_chronicle(session, messages, drivers, now):
    """Return None for an unfinished/incomplete journal; [] is a valid quiet race.

    Only explicit deployments, track-wide red flags and announced time penalties
    are supported. Investigations, yellow flags and unknown wording are omitted.
    A penalty announcement is not a claim about its effect on classification.
    """
    start, end = utc(session.get("date_start")), utc(session.get("date_end"))
    key = session.get("session_key")
    if (not isinstance(key, int) or key < 1 or str(session.get("session_type", "")).lower() != "race"
            or session.get("session_name", "Race") != "Race"
            or session.get("is_cancelled") or not start or not end or end <= start
            or now < end + timedelta(minutes=5) or not isinstance(messages, list)):
        return None
    valid = []
    for row in messages:
        if not isinstance(row, dict) or row.get("session_key") != key:
            continue
        date = utc(row.get("date"))
        if date and start <= date <= min(now, end + timedelta(days=1)):
            valid.append((date, row))
    starts = [date for date, row in valid if row.get("category") == "SessionStatus"
              and str(row.get("message", "")).upper() == "SESSION STARTED"]
    finishes = [date for date, row in valid if (row.get("category") == "SessionStatus"
                and str(row.get("message", "")).upper() == "SESSION FINISHED")
                or (row.get("category") == "Flag" and row.get("flag") == "CHEQUERED")]
    if not starts or not finishes or min(finishes) <= min(starts):
        return None
    race_start, race_finish = min(starts), min(finishes)
    names = {str(row["driver_number"]): str(row.get("full_name") or row.get("name_acronym") or "").strip()[:80]
             for row in drivers or [] if isinstance(row, dict) and row.get("session_key") == key
             and row.get("driver_number") is not None}
    result = []
    for date, row in sorted(valid, key=lambda pair: pair[0]):
        if date < race_start:
            continue  # Never describe a formation-lap deployment as a race event.
        message = " ".join(str(row.get("message") or "").upper().split())
        category = row.get("category")
        title, kind, score = "", "", 0
        during_race = date <= race_finish
        if during_race and category == "SafetyCar" and message == "SAFETY CAR DEPLOYED":
            title, kind, score = SC_TEXT, "sc", 80
        elif during_race and category == "SafetyCar" and message == "VIRTUAL SAFETY CAR DEPLOYED":
            title, kind, score = "Включён VSC — пилоты обязаны соблюдать заданный темп.", "vsc", 70
        elif during_race and category == "Flag" and row.get("flag") == "RED" and row.get("scope") == "Track":
            title, kind, score = "Красный флаг — гонка остановлена.", "red_flag", 100
        elif category == "Other" and not any(word in message for word in (
                "INVESTIGATION", "NOTED", "POSSIBLE", "RESCINDED", "WITHDRAWN", "REVOKED")):
            penalty = re.fullmatch(r"(?:FIA STEWARDS:\s*)?(\d{1,3}) SECONDS? (?:TIME )?PENALTY FOR CAR (\d{1,3})(?:\s+.*)?", message)
            if penalty and 0 < int(penalty[1]) <= 120:
                name = names.get(penalty[2]) or f"Машина №{penalty[2]}"
                title, kind, score = f"{name}: объявлен временной штраф — {int(penalty[1])} сек.", "penalty", 90
        if not title:
            continue
        lap = row.get("lap_number")
        prefix = "После финиша: " if not during_race else f"Круг {lap}: " if isinstance(lap, int) and 0 < lap < 200 else ""
        token = hashlib.sha256(f"{date.isoformat()}|{message}".encode()).hexdigest()[:16]
        result.append({"title": prefix + title, "category": kind, "score": score,
                       "published": date.timestamp(), "source_id": SOURCE,
                       "url": f"https://api.openf1.org/v1/race_control?session_key={key}#event-{token}"})
    return result[:200]


async def public_chronicle(season, round_num):
    try:
        async with news.connection(readonly=True) as conn:
            rows = await (await conn.execute("""SELECT a.* FROM recap_news_articles a
                JOIN recap_news_sources s USING(source_id)
                WHERE a.source_id=? AND a.season=? AND a.round=? AND a.hidden=0 AND s.enabled=1
                ORDER BY a.score DESC,a.published LIMIT 200""", (SOURCE, season, round_num))).fetchall()
        valid = [dict(row) for row in rows if news.canonical_url(row["url"], news.FEED_BY_ID[SOURCE])]
        return [{"title": display_title(row["title"]), "url": row["url"], "publisher": "OpenF1",
                 "published_at": datetime.fromtimestamp(row["published"], timezone.utc).isoformat()}
                for row in select_events(valid)]
    except aiosqlite.Error:
        logger.warning("Race chronology unavailable; retained statistical recap")
        return []


async def refresh_recent_race_control():
    try:
        await asyncio.wait_for(_refresh_recent_race_control(), timeout=55)
    except TimeoutError:
        await news.record_failure(SOURCE, "OpenF1: превышено время ожидания", datetime.now(timezone.utc), news.INTERVAL)
    except Exception:
        logger.warning("Race-control refresh failed; retained previous events", exc_info=True)


async def _refresh_recent_race_control():
    from app.f1_data import get_season_schedule_short_async

    now = datetime.now(timezone.utc)
    async with news.connection() as conn:
        row = await (await conn.execute("SELECT * FROM recap_news_sources WHERE source_id=?", (SOURCE,))).fetchone()
        if not row or not row["enabled"] or row["next_check"] > now.timestamp():
            return
        state = dict(row)
        checks = {row["round"]: dict(row) for row in await (await conn.execute(
            "SELECT * FROM recap_control_checks WHERE season=?", (now.year,))).fetchall()}
    try:
        schedule = await asyncio.wait_for(get_season_schedule_short_async(now.year), timeout=15)
        if not schedule:
            raise ValueError("Календарь гонок временно недоступен")
        eligible = []
        for event in schedule:
            start = utc(event.get("race_start_utc"))
            checked = checks.get(event.get("round"), {})
            if (not event.get("is_cancelled") and start and start.year == now.year
                    and timedelta(hours=1) <= now - start <= timedelta(days=10)
                    and not checked.get("final") and checked.get("next_check", 0) <= now.timestamp()):
                eligible.append(event)
        if not eligible:
            return
        # At most one race per pass, and no laps/telemetry requests.
        event = max(eligible, key=lambda item: item["round"])
        sessions = await _cached_prediction_openf1_sessions(now.year)
        session = _openf1_race_session(event, [s for s in sessions or [] if s.get("session_name", "Race") == "Race"])
        if not session or not utc(session.get("date_start")) or utc(session["date_start"]).year != now.year:
            raise ValueError("OpenF1: сессия нужной гонки ещё недоступна")
        end = utc(session.get("date_end"))
        if not end or now < end + timedelta(minutes=5):
            raise ValueError("Ждём завершения гонки и публикации журнала OpenF1")
        payloads = {}
        for path in ("race_control", "drivers"):
            diagnostics = {}
            payloads[path] = await _prediction_openf1_get(path, diagnostics=diagnostics, session_key=session["session_key"])
            if not isinstance(payloads[path], list):
                code = diagnostics.get("http_status")
                raise ValueError(f"OpenF1: HTTP {code}" if code else f"OpenF1: {path} временно недоступен")
        entries = build_chronicle(session, payloads["race_control"], payloads["drivers"], now)
        if entries is None:
            raise ValueError("OpenF1: журнал пока не подтверждает старт и финиш гонки")
        async with news.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            enabled = await (await conn.execute("SELECT enabled FROM recap_news_sources WHERE source_id=?", (SOURCE,))).fetchone()
            if not enabled or not enabled[0]:
                return
            await news.save_candidates(conn, entries, event, now.year, now)
            await conn.execute("""INSERT INTO recap_control_checks(season,round,session_key,updated,next_check,final)
                VALUES(?,?,?,?,?,?) ON CONFLICT(season,round) DO UPDATE SET session_key=excluded.session_key,
                updated=excluded.updated,next_check=excluded.next_check,final=excluded.final""",
                (now.year, event["round"], session["session_key"], now.timestamp(), now.timestamp() + 3600,
                 int(now >= end + timedelta(days=1))))
            await conn.execute("""UPDATE recap_news_sources SET checked=?,successful=?,next_check=?,failures=0,error=NULL
                WHERE source_id=?""", (now.timestamp(), now.timestamp(), now.timestamp() + news.INTERVAL, SOURCE))
            await conn.commit()
    except (ValueError, TimeoutError, OpenF1SourceUnavailable) as exc:
        await news.record_failure(SOURCE, str(exc) or "OpenF1 временно недоступен", now,
                                  min(3600, news.INTERVAL * 2 ** min(state["failures"], 2)))
