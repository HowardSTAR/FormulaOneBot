"""Admin research forecasts: bounded data acquisition, immutable snapshots, no messages."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.db import db
from app.f1_data import get_season_schedule_short_async, get_practice_results_async
from app.services.prediction_model import simulate, evaluate
from app.services.prediction_history import load_history

logger = logging.getLogger(__name__)
RESULTS_URL = "https://api.jolpi.ca/ergast/f1"
# Venue locations, not user geolocation.
COORDS = {"Melbourne": (-37.8497, 144.968), "Shanghai": (31.3389, 121.220),
          "Suzuka": (34.8431, 136.541), "Sakhir": (26.0325, 50.5106), "Jeddah": (21.632, 39.104),
          "Miami": (25.958, -80.239), "Imola": (44.3439, 11.7167), "Monte Carlo": (43.7347, 7.4206),
          "Monaco": (43.7347, 7.4206), "Barcelona": (41.57, 2.261), "Madrid": (40.467, -3.615),
          "Montréal": (45.50, -73.5228), "Montreal": (45.50, -73.5228), "Spielberg": (47.2197, 14.7647),
          "Silverstone": (52.0786, -1.0169), "Spa-Francorchamps": (50.4372, 5.9714),
          "Budapest": (47.5789, 19.2486), "Zandvoort": (52.3888, 4.5409), "Monza": (45.6156, 9.2811),
          "Baku": (40.3725, 49.8533), "Singapore": (1.2914, 103.864), "Austin": (30.1328, -97.6411),
          "Mexico City": (19.4042, -99.0907), "São Paulo": (-23.7036, -46.6997),
          "Las Vegas": (36.1147, -115.173), "Lusail": (25.49, 51.454), "Yas Island": (24.4672, 54.6031),
          "Abu Dhabi": (24.4672, 54.6031)}


def timestamp(value) -> float:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
    except (TypeError, ValueError):
        return 0


async def ensure_schema(conn):
    await conn.execute("CREATE TABLE IF NOT EXISTS prediction_history_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL)")
    await conn.execute("""CREATE TABLE IF NOT EXISTS prediction_analytics (
        id TEXT PRIMARY KEY, season INTEGER NOT NULL, round INTEGER NOT NULL,
        session TEXT NOT NULL, created_at REAL NOT NULL, created_by INTEGER NOT NULL,
        start_at REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
        payload TEXT, error TEXT, actual TEXT, settled_at REAL
    )""")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_prediction_analytics_status ON prediction_analytics(status, start_at)")


async def classification(client, season, round_number, session):
    kind = "results" if session == "race" else "qualifying"
    response = await client.get(f"{RESULTS_URL}/{season}/{round_number}/{kind}/", params={"limit": 100})
    response.raise_for_status()
    races = response.json().get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    race = races[0]
    if int(race.get("season", 0)) != season or int(race.get("round", 0)) != round_number:
        return []
    return normalize_classification(race, session)


def normalize_classification(race, session):
    rows = []
    for r in race.get("Results" if session == "race" else "QualifyingResults", []):
        driver = r.get("Driver", {})
        code = driver.get("code") or driver.get("driverId")
        status = str(r.get("status", ""))
        try:
            position = int(r["position"])
        except (KeyError, ValueError, TypeError):
            return []
        if not code or (session == "race" and not status):
            return []
        rows.append({"code": code, "name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip(),
                     "team": r.get("Constructor", {}).get("name", ""), "position": position,
                     "dnf": session == "race" and status != "Finished" and not status.startswith("+"),
                     "status": status, "grid": int(r.get("grid") or 0),
                     "driver_id": driver.get("driverId"), "team_id": r.get("Constructor", {}).get("constructorId")})
    # Never settle a live/partial top-ten table.
    if len(rows) < 18 or len({r["code"] for r in rows}) != len(rows):
        return []
    if sorted(r["position"] for r in rows) != list(range(1, len(rows) + 1)):
        return []
    return rows


async def context_data(client, event, start, cutoff):
    weather = {"available": False, "source": "https://open-meteo.com/", "reason": "Нет прогноза для даты или трассы"}
    coords = COORDS.get(event.get("location", ""))
    if coords and 0 < start - cutoff < 15 * 86400:
        try:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": coords[0], "longitude": coords[1], "forecast_days": 16, "timezone": "UTC",
                "hourly": "precipitation_probability,temperature_2m,wind_speed_10m"})
            response.raise_for_status()
            hourly = response.json()["hourly"]
            index = min(range(len(hourly["time"])), key=lambda i: abs(timestamp(hourly["time"][i]) - start))
            probability = hourly["precipitation_probability"][index]
            if probability is not None and abs(timestamp(hourly["time"][index]) - start) <= 3600:
                weather = {"available": True, "source": "https://open-meteo.com/", "rain": probability / 100,
                           "temperature": hourly["temperature_2m"][index], "wind": hourly["wind_speed_10m"][index],
                           "hour": hourly["time"][index], "fetched_at": time.time()}
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            weather["reason"] = "Погодный сервис недоступен"
    news = []
    news_available = False
    try:
        response = await client.get("https://feeds.bbci.co.uk/sport/formula1/rss.xml")
        response.raise_for_status()
        if len(response.content) <= 512000:
            root = ElementTree.fromstring(response.content)
            news_available = True
            for item in root.findall(".//item"):
                try:
                    published = parsedate_to_datetime(item.findtext("pubDate", "")).timestamp()
                except (TypeError, ValueError):
                    continue
                url = item.findtext("link", "")
                if cutoff - 7 * 86400 <= published <= cutoff and url.startswith("https://www.bbc."):
                    news.append({"title": item.findtext("title", "")[:240], "url": url, "published_at": published})
    except (httpx.HTTPError, ElementTree.ParseError):
        pass
    return {"weather": weather, "news": news[:6], "news_available": news_available}


class ForecastClosed(ValueError):
    """A forecast cannot be created once its target session has started."""


async def prepare_forecast(season, round_number, session, *, cutoff=None):
    cutoff = time.time() if cutoff is None else cutoff
    schedule = await get_season_schedule_short_async(season)
    event = next((e for e in schedule if int(e["round"]) == round_number and not e.get("is_cancelled")), None)
    if not event:
        raise ValueError("Этап отсутствует в расписании")
    start = timestamp(event.get("race_start_utc" if session == "race" else "quali_start_utc"))
    if start <= max(cutoff, time.time()):
        raise ForecastClosed("Сессия началась или время старта неизвестно. Новый прогноз запрещён")
    warnings, history = [], []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        history, coverage = await load_history(client, season, event, cutoff, normalize_classification, timestamp)
        if coverage["unavailable"]:
            warnings.append("Часть архива недоступна. Фактическое покрытие показано ниже; отсутствующие данные не выдумываются")
        if sum(h["session"] == session for h in history) < 3:
            raise ValueError("Нужно хотя бы 3 полные прошлые классификации. Источник пока не вернул достаточно данных")
        # Roster from an explicitly current-year entry list, never previous year's finishers.
        response = await client.get(f"{RESULTS_URL}/{season}/{round_number}/drivers/", params={"limit": 100})
        response.raise_for_status()
        entrants = response.json().get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
        if len(entrants) < 18:
            # An upcoming round may not have an entry list yet. Use latest current-season classification, disclosed below.
            recent = next((h for h in history if h["season"] == season), None)
            if not recent:
                raise ValueError("Нет подтверждённого состава текущего сезона; прогноз пока недоступен")
            roster = [{k: r.get(k) for k in ("code", "name", "team", "driver_id", "team_id")} for r in recent["rows"]]
            warnings.append("Состав взят из последней сессии сезона: возможные замены пилотов ещё не учтены")
        else:
            teams = {r["code"]: r for h in reversed(history) for r in h["rows"]}
            roster = [{"code": d.get("code") or d["driverId"], "name": f"{d['givenName']} {d['familyName']}",
                       "driver_id": d["driverId"],
                       "team": teams.get(d.get("code") or d["driverId"], {}).get("team", "Неизвестно"),
                       "team_id": teams.get(d.get("code") or d["driverId"], {}).get("team_id")} for d in entrants]
        current, current_label = [], "Недоступна"
        if session == "race" and 0 < timestamp(event.get("quali_start_utc")) < cutoff - 2 * 3600:
            try:
                current = await classification(client, season, round_number, "qualifying")
                current_label = "Квалификация (не стартовая решётка; штрафы не учтены)"
            except (httpx.HTTPError, ValueError):
                pass
        if session == "qualifying":
            for number in (3, 2, 1):
                if 0 < timestamp(event.get(f"practice{number}_start_utc")) < cutoff - 90 * 60:
                    try:
                        practice = await asyncio.wait_for(get_practice_results_async(season, round_number, number), 18)
                        current = [{"code": r["driver"], "position": int(r["position"])} for r in practice if r.get("position")]
                        current_label = f"Практика {number} (топливо и программы неизвестны)"
                    except Exception:
                        current = []
                    if current:
                        break
        context = await context_data(client, event, start, cutoff)
    if time.time() >= start:
        raise ForecastClosed("Во время расчёта сессия началась. Прогноз не сохранён")
    inputs = {"roster": roster, "history": history, "current": current, "coverage": coverage, **context}
    return {"event": event, "season": season, "session": session, "start_at": start, "cutoff": cutoff, "acquired_at": time.time(),
            "inputs": inputs, "warnings": warnings, "current_label": current_label,
            "news_policy": "Упоминание фамилии и слов о риске (авария, штраф, травма, надёжность) в английском заголовке увеличивает разброс на 5%, максимум 15%. Это экспериментальный сигнал неопределённости, не подтверждение события; скорость и штрафы по заголовкам не назначаются.",
            "source": "https://jolpi.ca/ergast/"}


def finish_forecast(snapshot):
    inputs = snapshot['inputs']
    seed = int(hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:8], 16)
    model = simulate(inputs['roster'], inputs['history'], snapshot['session'], inputs['current'],
                     inputs['weather'].get('rain'), seed, news=inputs['news'])
    return {**snapshot, 'model': model}


async def build_forecast(season, round_number, session, *, snapshot=None, cutoff=None, save_snapshot=None):
    if snapshot is None:
        snapshot = await prepare_forecast(season, round_number, session, cutoff=cutoff)
        if save_snapshot is not None:
            await save_snapshot(snapshot)
    if time.time() >= snapshot['start_at']:
        raise ForecastClosed('Сессия началась. Расчёт закрыт без использования поздних данных')
    return await asyncio.to_thread(finish_forecast, snapshot)


async def run_job(job_id=None):
    """Atomically claim, retry and fence one durable calculation after a crash."""
    from app.services.operations import connection
    now, token = time.time(), uuid.uuid4().hex
    async with connection(db) as conn:
        await conn.execute('BEGIN IMMEDIATE')
        row = await (await conn.execute(
            "SELECT * FROM prediction_analytics WHERE status='pending' AND next_attempt<=? AND lease_until<=? AND (? IS NULL OR id=?) ORDER BY created_at LIMIT 1",
            (now, now, job_id, job_id))).fetchone()
        if row is None:
            await conn.commit()
            return False
        await conn.execute('UPDATE prediction_analytics SET lease_token=?,lease_until=?,attempts=attempts+1 WHERE id=?',
                           (token, now+240, row['id']))
        await conn.commit()

    async def save_snapshot(snapshot):
        async with connection(db) as conn:
            cursor = await conn.execute("UPDATE prediction_analytics SET snapshot=?,start_at=? WHERE id=? AND lease_token=? AND status='pending'",
                (json.dumps(snapshot, ensure_ascii=False, allow_nan=False), snapshot['start_at'], row['id'], token))
            await conn.commit()
            if not cursor.rowcount:
                raise RuntimeError('Forecast lease lost')

    try:
        if now-row['created_at'] > 86400:
            raise ForecastClosed('Истёк срок ожидания исходных данных (24 часа)')
        snapshot = json.loads(row['snapshot']) if row['snapshot'] else None
        payload = await asyncio.wait_for(build_forecast(row['season'], row['round'], row['session'],
            snapshot=snapshot, cutoff=row['created_at'], save_snapshot=save_snapshot), 180)
        if time.time() >= payload['start_at']:
            raise ForecastClosed('Сессия началась до сохранения расчёта. Прогноз не сохранён')
        async with connection(db) as conn:
            await conn.execute("UPDATE prediction_analytics SET status='ready',payload=?,start_at=?,error=NULL,lease_token=NULL,lease_until=0 WHERE id=? AND lease_token=? AND status='pending'",
                (json.dumps(payload, ensure_ascii=False, allow_nan=False), payload['start_at'], row['id'], token))
            await conn.commit()
    except asyncio.CancelledError:
        # Worker shutdown releases the claim; an abrupt kill is recovered by lease expiry.
        async with connection(db) as conn:
            await conn.execute('UPDATE prediction_analytics SET lease_token=NULL,lease_until=0 WHERE id=? AND lease_token=?', (row['id'],token))
            await conn.commit()
        raise
    except Exception as exc:
        closed = isinstance(exc, ForecastClosed)
        message = str(exc) if closed else 'Данные временно недоступны. Расчёт будет повторён автоматически'
        delay = min(300, 15 * 2**min(row['attempts'], 5))
        async with connection(db) as conn:
            await conn.execute('UPDATE prediction_analytics SET status=?,error=?,next_attempt=?,lease_token=NULL,lease_until=0 WHERE id=? AND lease_token=?',
                ('error' if closed else 'pending', message, time.time()+delay, row['id'], token))
            await conn.commit()
        logger.warning('Forecast %s %s: %s', row['id'], 'closed' if closed else 'will retry', type(exc).__name__)
    return True


async def settle_forecasts():
    """Only stored forecasts are inspected. No historical broadcasts or Telegram calls."""
    now = time.time()
    rows = await (await db.conn.execute("SELECT * FROM prediction_analytics WHERE status='ready' AND actual IS NULL AND start_at<? ORDER BY start_at DESC LIMIT 50", (now - 4 * 3600,))).fetchall()
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        cache = {}
        for row in rows:
            key = (row["season"], row["round"], row["session"])
            try:
                if key not in cache:
                    cache[key] = await classification(client, *key)
                actual = cache[key]
                if not actual:
                    continue
                payload = json.loads(row["payload"])
                if len(actual) < len(payload["model"]["drivers"]):
                    continue
                result = {"rows": actual, "metrics": evaluate(payload["model"], actual),
                          "source": f"{RESULTS_URL}/{row['season']}/{row['round']}/{'results' if row['session'] == 'race' else 'qualifying'}/"}
                async with db.write_lock:
                    await db.conn.execute("UPDATE prediction_analytics SET actual=?,settled_at=? WHERE id=? AND actual IS NULL", (json.dumps(result), now, row["id"]))
                    await db.conn.commit()
            except Exception:
                logger.exception("Prediction settlement unavailable: %s", key)
