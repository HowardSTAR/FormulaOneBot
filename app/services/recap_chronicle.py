"""Post-race text journal from race control, position changes and pit stops.

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
PARSER_VERSION = 4
RECHECK_WINDOW = timedelta(days=7)
LOOKBACK = timedelta(days=10)
SC_TEXT = "На трассу выпустили машину безопасности — гонка продолжилась за ней."
VSC_TEXT = "Включили VSC — пилотов обязали соблюдать заданный темп."
RED_TEXT = "Гонку остановили красным флагом."
LEGACY_SC_TEXT = "Выпущена машина безопасности — гонка нейтрализована."
PREVIOUS_SC_TEXT = "Выпущена машина безопасности — гонка проходит за машиной безопасности."

PENALTY_REASONS = {
    "CAUSING A COLLISION": "за провоцирование столкновения",
    "SPEEDING IN THE PIT LANE": "за превышение скорости на пит-лейне",
    "SPEEDING IN PIT LANE": "за превышение скорости на пит-лейне",
    "TRACK LIMITS": "за нарушение пределов трассы",
    "LEAVING THE TRACK AND GAINING AN ADVANTAGE": "за выезд за пределы трассы с получением преимущества",
    "YELLOW FLAG INFRINGEMENT": "за нарушение режима жёлтых флагов",
    "UNSAFE RELEASE": "за небезопасный выпуск из боксов",
    "FALSE START": "за фальстарт",
    "JUMP START": "за фальстарт",
    "FORCING ANOTHER DRIVER OFF THE TRACK": "за вытеснение другого пилота за пределы трассы",
    "FAILING TO FOLLOW RACE DIRECTORS INSTRUCTIONS": "за невыполнение указаний дирекции гонки",
    "OVERTAKING UNDER SAFETY CAR": "за обгон в режиме машины безопасности",
    "IGNORING BLUE FLAGS": "за игнорирование синих флагов",
}
DEPLOYMENT_REASONS = {
    "DEBRIS": "из-за обломков на трассе",
    "DEBRIS ON TRACK": "из-за обломков на трассе",
    "HEAVY RAIN": "из-за сильного дождя",
    "POOR VISIBILITY": "из-за плохой видимости",
    "CAUSING A COLLISION": "из-за столкновения",
    "COLLISION": "из-за столкновения",
    "CAR STOPPED ON TRACK": "из-за остановившейся на трассе машины",
}


def display_title(title, source_id=SOURCE):
    # Final snapshots are not refetched. Update their wording at read time,
    # leaving stored provenance, moderation and publisher headlines unchanged.
    if source_id != SOURCE:
        return title
    for old, new in ((LEGACY_SC_TEXT, SC_TEXT), (PREVIOUS_SC_TEXT, SC_TEXT),
                     ("Включён VSC — пилоты обязаны соблюдать заданный темп.", VSC_TEXT),
                     ("Красный флаг — гонка остановлена.", RED_TEXT)):
        title = title.replace(old, new)
    return re.sub(r": объявлен временной штраф — (\d+) сек\.", r" получил \1-секундный штраф.", title)


def reason_tail(message, reasons):
    # Only a cause stated in this very message is a causal claim. Strip the
    # optional stewards' incident clock; neighbouring messages are not reasons.
    tail = message.partition(" - ")[2]
    tail = re.sub(r"\s*\(\d{1,2}:\d{2}:\d{2}\)\s*$", "", tail).strip().rstrip(".")
    return reasons.get(tail.replace("'", "").replace("’", ""))


def safety_context(date, valid, race_finish):
    """Direct facts during the deployment, never an inferred crash or culprit."""
    end = min(race_finish, date + timedelta(minutes=5))
    endings = {"SAFETY CAR IN THIS LAP", "VIRTUAL SAFETY CAR ENDING",
               "SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR DEPLOYED"}
    for other_date, row in valid:
        if date < other_date <= end and str(row.get("message", "")).upper() in endings:
            end = other_date
    facts = []
    for other_date, row in valid:
        if not date <= other_date <= end or row.get("category") != "Other":
            continue
        message = " ".join(str(row.get("message", "")).upper().split())
        match = re.fullmatch(r"(RECOVERY VEHICLE|MARSHALS) ON TRACK AT TURN (\d{1,2})", message)
        if match and 0 < int(match[2]) <= 99:
            turn = int(match[2])
            if match[1] == "RECOVERY VEHICLE":
                facts.append((0, other_date, turn, f"В этот период в повороте {turn} работала эвакуационная техника."))
            else:
                facts.append((1, other_date, turn, f"В этот период в повороте {turn} работали маршалы."))
        elif message == "ALL CARS THROUGH THE PIT LANE":
            facts.append((2, other_date, None, "В этот период машины направили через пит-лейн."))
    selected, turns, texts = [], set(), set()
    for fact in sorted(facts):
        if fact[3] in texts or fact[2] is not None and fact[2] in turns:
            continue
        selected.append(fact)
        turns.add(fact[2])
        texts.add(fact[3])
        if len(selected) == 2:
            break
    return [fact[3] for fact in sorted(selected, key=lambda fact: fact[1])]


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


def collision_text(message, names):
    """Only explicit collisions/crashes; flags and retirements are not proof."""
    if any(word in message for word in ('POSSIBLE', 'NO FURTHER ACTION', 'RESCINDED', 'WITHDRAWN', 'REVOKED')):
        return None
    match = re.fullmatch(r'(?:FIA STEWARDS: )?INCIDENT INVOLVING CARS? (.+?) (?:NOTED|UNDER INVESTIGATION|WILL BE INVESTIGATED AFTER THE RACE) - (?:CAUSING A COLLISION|COLLISION)(?: \(\d{1,2}:\d{2}:\d{2}\))?', message)
    if match:
        numbers = re.findall(r'(?<![A-Z0-9])(\d{1,3})(?:\s*\([A-Z]{3}\))?(?=\s*(?:AND|,|$))', match[1])
        if numbers:
            return 'Дирекция сообщила о столкновении: ' + ', '.join(names.get(n, f'машина №{n}') for n in numbers) + '.'
    match = re.fullmatch(r'CAR (\d{1,3})(?: \([A-Z]{3}\))? (CRASHED|HIT (?:THE )?BARRIER|COLLIDED WITH CAR (\d{1,3}))(?: AT TURN (\d{1,2}))?', message)
    if match:
        name = names.get(match[1], f'Машина №{match[1]}')
        detail = (' столкнулся с ' + names.get(match[3], f'машиной №{match[3]}')) if match[3] else ' попал в аварию'
        return name + detail + (f' в повороте {match[4]}' if match[4] else '') + '.'
    return None


def build_chronicle(session, messages, drivers, now, overtakes=None, pits=None, *, positions=None, laps=None, results=None):
    """Return None for an unfinished/incomplete journal; [] is a valid quiet race.

    Explicit deployments, track-wide red flags, time penalties, position swaps
    and stationary pit-stop durations become short factual text entries.
    A position swap does not prove an on-track overtake; penalty announcements
    do not prove an effect on classification.
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
        if date and start <= date <= min(now, end + RECHECK_WINDOW):
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
    codes = {str(row['driver_number']): str(row.get('name_acronym', '')).upper()
             for row in drivers or [] if row.get('session_key') == key and row.get('driver_number') is not None}
    from app.services.race_highlights import RetainedOvertakes
    retained = RetainedOvertakes(key, race_finish, positions, laps, pits, results, messages)
    result = []
    for date, row in sorted(valid, key=lambda pair: pair[0]):
        if date < race_start:
            continue  # Never describe a formation-lap deployment as a race event.
        message = " ".join(str(row.get("message") or "").upper().split())
        category = row.get("category")
        action = message.partition(" - ")[0]
        title, kind, score = "", "", 0
        during_race = date <= race_finish
        if during_race and category == "SafetyCar" and action == "SAFETY CAR DEPLOYED":
            title, kind, score = SC_TEXT, "sc", 80
            reason = reason_tail(message, DEPLOYMENT_REASONS)
            if reason:
                title = f"На трассу выпустили машину безопасности {reason} — гонка продолжилась за ней."
        elif during_race and category == "SafetyCar" and action == "VIRTUAL SAFETY CAR DEPLOYED":
            title, kind, score = VSC_TEXT, "vsc", 70
            reason = reason_tail(message, DEPLOYMENT_REASONS)
            if reason:
                title = f"Включили VSC {reason} — пилотов обязали соблюдать заданный темп."
        elif during_race and category == "Flag" and row.get("flag") == "RED" and row.get("scope") == "Track":
            title, kind, score = RED_TEXT, "red_flag", 100
            reason = reason_tail(message, DEPLOYMENT_REASONS)
            if reason:
                title = f"Гонку остановили красным флагом {reason}."
        elif category == "Other" and not any(word in message for word in (
                "INVESTIGATION", "NOTED", "POSSIBLE", "RESCINDED", "WITHDRAWN", "REVOKED")):
            penalty = re.fullmatch(r"(?:FIA STEWARDS:\s*)?(\d{1,3}) SECONDS? (?:TIME )?PENALTY FOR CAR (\d{1,3})(?:\s+.*)?", message)
            if penalty and 0 < int(penalty[1]) <= 120:
                name = names.get(penalty[2]) or f"Машина №{penalty[2]}"
                reason = reason_tail(message, PENALTY_REASONS)
                title, kind, score = f"{name} получил {int(penalty[1])}-секундный штраф" + (f" {reason}" if reason else "") + ".", "penalty", 90
            else:
                penalty = re.fullmatch(r'(?:FIA STEWARDS:\s*)?(DRIVE THROUGH|STOP(?:/| AND | )GO|DISQUALIFICATION)(?: (\d{1,3}) SECONDS?)? (?:PENALTY )?FOR CAR (\d{1,3})(?:\s+.*)?', message)
                if penalty:
                    name = names.get(penalty[3], f'Машина №{penalty[3]}')
                    sanction = {'DRIVE THROUGH':'штраф проездом через пит-лейн', 'DISQUALIFICATION':'дисквалификацию'}.get(penalty[1], 'штраф stop-and-go' + (f' на {penalty[2]} с' if penalty[2] else ''))
                    title, kind, score = f'{name} получил {sanction}.', 'penalty', 90
        if not title and during_race and category == 'Other':
            title = collision_text(message, names)
            if title:
                kind, score = 'incident', 100
        if not title:
            continue
        if kind == 'penalty':
            car = re.search(r'\bFOR CAR (\d{1,3})\b', message)
            sanction = message.partition(' FOR CAR ')[0].removeprefix('FIA STEWARDS: ')
            if car and any(other_date > date and any(word in str(other.get('message', '')).upper() for word in ('RESCINDED', 'WITHDRAWN', 'REVOKED'))
                           and re.search(r'\bFOR CAR ' + car[1] + r'\b', str(other.get('message', '')).upper())
                           and sanction in str(other.get('message', '')).upper() for other_date, other in valid):
                continue
        lap = row.get("lap_number")
        prefix = "После финиша: " if not during_race else f"Круг {lap}: " if isinstance(lap, int) and 0 < lap < 200 else ""
        if kind in {"sc", "vsc"}:
            for detail in safety_context(date, valid, race_finish):
                if len(prefix + title + " " + detail) <= 240:
                    title += " " + detail
        token = hashlib.sha256(f"{date.isoformat()}|{message}".encode()).hexdigest()[:16]
        result.append({"title": prefix + title, "category": kind, "score": score,
                       "published": date.timestamp(), "source_id": SOURCE,
                       "url": f"https://api.openf1.org/v1/race_control?session_key={key}#event-{token}"})
    # The timing feed includes position swaps through stops and penalties too.
    # Describe the observed change; never invent an on-track pass or its cause.
    for path, records in (("overtakes", overtakes), ("pit", pits)):
        for row in records or []:
            if not isinstance(row, dict) or row.get('session_key') != key:
                continue
            date = utc(row.get('date'))
            if not date or not race_start < date < race_finish:
                continue
            if path == 'overtakes':
                number, other, position = row.get('overtaking_driver_number'), row.get('overtaken_driver_number'), row.get('position')
                if (str(number) not in names or str(other) not in names or number == other
                        or not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= 22):
                    continue
                title = f'{names[str(number)]} вышел на P{position}; {names[str(other)]} уступил позицию.'
                event_title = title  # Keep the original URL and moderation through upgrades.
                kind, score = ('lead_change', 110) if position == 1 else ('position_change', 85 if position <= 3 else 40)
                retained_lap = retained.check(row)
                if retained_lap and re.fullmatch(r'[A-Z]{3}', codes.get(str(number), '')):
                    title = f'{names[str(number)]} обогнал {names[str(other)]}, вышел на P{position} и сохранил эту позицию до финиша.'
                    kind, score = 'retained_overtake', 80
                    row = {**row, 'lap_number': retained_lap}
            else:
                number, duration = row.get('driver_number'), row.get('stop_duration')
                if str(number) not in names or not isinstance(duration, (int, float)) or not 0 < duration < 120:
                    continue
                title = f'Пит-стоп {names[str(number)]}: остановка {duration:g} с.'
                event_title = title
                kind, score = 'pit_stop', 75 if duration >= 5 else 55 if duration <= 2.5 else 20
            lap = row.get('lap_number')
            prefix = f'Круг {lap}: ' if isinstance(lap, int) and 0 < lap < 200 else date.strftime('%H:%M UTC: ')
            token = hashlib.sha256(f'{path}|{date.isoformat()}|{event_title}'.encode()).hexdigest()[:16]
            result.append({'title': prefix + title, 'category': kind, 'score': score,
                           'published': date.timestamp(), 'source_id': SOURCE,
                           'url': f'https://api.openf1.org/v1/{path}?session_key={key}#event-{token}',
                           'driver_code': codes.get(str(number), '') if kind == 'retained_overtake' else ''})
    return sorted(result, key=lambda row: (row['published'], row['url']))[:2000]


async def public_chronicle(season, round_num):
    try:
        async with news.connection(readonly=True) as conn:
            rows = await (await conn.execute("""SELECT a.* FROM recap_news_articles a
                JOIN recap_news_sources s USING(source_id)
                WHERE a.source_id=? AND a.season=? AND a.round=? AND a.hidden=0 AND s.enabled=1
                ORDER BY a.score DESC,a.published LIMIT 2000""", (SOURCE, season, round_num))).fetchall()
        valid = [dict(row) for row in rows if news.canonical_url(row["url"], news.FEED_BY_ID[SOURCE])]
        return [{"title": display_title(row["title"]), "url": row["url"], "publisher": "OpenF1",
                 "published_at": datetime.fromtimestamp(row["published"], timezone.utc).isoformat()}
                for row in select_events(valid)]
    except aiosqlite.Error:
        logger.warning("Race chronology unavailable; retained statistical recap")
        return []


async def public_highlight_candidates(season, round_num):
    """Shared public facts; preferences are applied separately per recipient."""
    try:
        async with news.connection(readonly=True) as conn:
            rows = await (await conn.execute('''SELECT a.* FROM recap_news_articles a
                JOIN recap_news_sources s USING(source_id)
                JOIN recap_control_checks c ON c.season=a.season AND c.round=a.round
                WHERE a.source_id=? AND a.season=? AND a.round=? AND a.hidden=0 AND s.enabled=1
                AND (a.category!='retained_overtake' OR c.parser_version=?) AND a.category IN ('incident','penalty','retained_overtake')
                ORDER BY a.published,a.url LIMIT 2000''', (SOURCE, season, round_num, PARSER_VERSION))).fetchall()
        return [{key: row[key] for key in ('category', 'score', 'published', 'url', 'driver_code')} | {
                 'title': display_title(row['title']), 'publisher':'OpenF1',
                 'published_at':datetime.fromtimestamp(row['published'], timezone.utc).isoformat()}
                for row in rows if news.canonical_url(row['url'], news.FEED_BY_ID[SOURCE])]
    except aiosqlite.Error:
        return []


async def public_commentary(season, round_num):
    """Read the full persisted text journal; a quiet confirmed race is ready too."""
    try:
        async with news.connection(readonly=True) as conn:
            state = await (await conn.execute('''SELECT c.parser_version FROM recap_control_checks c
                JOIN recap_news_sources s ON s.source_id=? AND s.enabled=1
                WHERE c.season=? AND c.round=?''', (SOURCE, season, round_num))).fetchone()
            rows = await (await conn.execute('''SELECT a.* FROM recap_news_articles a
                JOIN recap_news_sources s USING(source_id)
                WHERE a.source_id=? AND a.season=? AND a.round=? AND a.hidden=0 AND s.enabled=1
                ORDER BY a.published,a.url LIMIT 2000''', (SOURCE, season, round_num))).fetchall()
        return {'status': 'ready' if state and state['parser_version'] == PARSER_VERSION else 'waiting',
                'entries': [{'title': display_title(row['title']), 'url': row['url'],
                             'published_at': datetime.fromtimestamp(row['published'], timezone.utc).isoformat()}
                            for row in rows if news.canonical_url(row['url'], news.FEED_BY_ID[SOURCE])]}
    except aiosqlite.Error:
        return {'status': 'waiting', 'entries': []}


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
    seasons = [now.year]
    if now - now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0) <= LOOKBACK:
        seasons.append(now.year - 1)
    async with news.connection() as conn:
        row = await (await conn.execute("SELECT * FROM recap_news_sources WHERE source_id=?", (SOURCE,))).fetchone()
        if not row or not row["enabled"] or row["next_check"] > now.timestamp():
            return
        state = dict(row)
        checks = {(row["season"], row["round"]): dict(row) for row in await (await conn.execute(
            "SELECT * FROM recap_control_checks WHERE season IN (" + ",".join("?" for _ in seasons) + ")", seasons)).fetchall()}
    try:
        schedules = await asyncio.gather(*(asyncio.wait_for(get_season_schedule_short_async(season), timeout=15)
                                           for season in seasons), return_exceptions=True)
        if not any(isinstance(schedule, list) and schedule for schedule in schedules):
            raise ValueError("Календарь гонок временно недоступен")
        eligible = []
        for season, schedule in zip(seasons, schedules):
            if not isinstance(schedule, list):
                continue
            for event in schedule:
                start = utc(event.get("race_start_utc"))
                checked = checks.get((season, event.get("round")), {})
                upgrade = bool(checked) and checked.get("parser_version", 0) != PARSER_VERSION
                if (not event.get("is_cancelled") and start and start.year == season
                        and timedelta(hours=1) <= now - start <= LOOKBACK
                        and (not checked.get("final") or upgrade)
                        and (checked.get("next_check", 0) <= now.timestamp() or upgrade)):
                    eligible.append((season, event, start))
        if not eligible:
            return
        # At most one race per pass; timing is needed to verify retained passes.
        season, event, _ = max(eligible, key=lambda item: item[2])
        sessions = await _cached_prediction_openf1_sessions(season)
        session = _openf1_race_session(event, [s for s in sessions or [] if s.get("session_name", "Race") == "Race"])
        if not session or not utc(session.get("date_start")) or utc(session["date_start"]).year != season:
            raise ValueError("OpenF1: сессия нужной гонки ещё недоступна")
        end = utc(session.get("date_end"))
        if not end or now < end + timedelta(minutes=5):
            raise ValueError("Ждём завершения гонки и публикации журнала OpenF1")
        payloads = {}
        supplementary_ready = True
        for path in ("race_control", "drivers", "overtakes", "pit", "position", "laps", "session_result"):
            diagnostics = {}
            payloads[path] = await _prediction_openf1_get(path, diagnostics=diagnostics, session_key=session["session_key"])
            if not isinstance(payloads[path], list):
                code = diagnostics.get("http_status")
                if path in {'overtakes', 'pit', 'position', 'laps', 'session_result'}:
                    supplementary_ready = False
                    payloads[path] = []
                    continue
                raise ValueError(f"OpenF1: HTTP {code}" if code else f"OpenF1: {path} временно недоступен")
        entries = build_chronicle(session, payloads["race_control"], payloads["drivers"], now,
                                  payloads["overtakes"], payloads["pit"], positions=payloads['position'],
                                  laps=payloads['laps'], results=payloads['session_result'])
        if entries is None:
            raise ValueError("OpenF1: журнал пока не подтверждает старт и финиш гонки")
        async with news.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            enabled = await (await conn.execute("SELECT enabled FROM recap_news_sources WHERE source_id=?", (SOURCE,))).fetchone()
            if not enabled or not enabled[0]:
                return
            # A complete refreshed snapshot replaces obsolete generated facts,
            # while existing URLs keep their moderation state on upsert.
            if supplementary_ready:
                urls = {entry['url'] for entry in entries}
                old = await (await conn.execute('SELECT id,url FROM recap_news_articles WHERE source_id=? AND season=? AND round=?',
                                               (SOURCE, season, event['round']))).fetchall()
                await conn.executemany('DELETE FROM recap_news_articles WHERE id=?', [(row['id'],) for row in old if row['url'] not in urls])
            await news.save_candidates(conn, entries, event, season, now)
            delay = 3600 if now < end + timedelta(days=1) else 6 * 3600
            previous_version = checks.get((season, event['round']), {}).get('parser_version', 0)
            version = PARSER_VERSION if supplementary_ready or previous_version == PARSER_VERSION else PARSER_VERSION - 1
            await conn.execute("""INSERT INTO recap_control_checks(season,round,session_key,updated,next_check,final,parser_version)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(season,round) DO UPDATE SET session_key=excluded.session_key,
                updated=excluded.updated,next_check=excluded.next_check,final=excluded.final,parser_version=excluded.parser_version""",
                (season, event["round"], session["session_key"], now.timestamp(), now.timestamp() + delay,
                 int(supplementary_ready and now >= end + RECHECK_WINDOW), version))
            await conn.execute("""UPDATE recap_news_sources SET checked=?,successful=?,next_check=?,failures=0,error=?
                WHERE source_id=?""", (now.timestamp(), now.timestamp(), now.timestamp() + news.INTERVAL,
                                      None if supplementary_ready else 'Ожидаем полные данные позиций, кругов, пит-стопов и финиша OpenF1', SOURCE))
            await conn.commit()
    except (ValueError, TimeoutError, OpenF1SourceUnavailable) as exc:
        await news.record_failure(SOURCE, str(exc) or "OpenF1 временно недоступен", now,
                                  min(3600, news.INTERVAL * 2 ** min(state["failures"], 2)))
