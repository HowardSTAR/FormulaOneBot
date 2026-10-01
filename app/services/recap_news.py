"""Headline-only race news. No article scraping, AI, scoring or Telegram sends.

Only the background job fetches feeds. Readers use persisted candidates; moderation
is applied at read time, outside the statistical recap cache.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import unquote, urlsplit, urlunsplit
from xml.etree import ElementTree

import aiosqlite
import httpx

from app.db import db

logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 1_000_000
INTERVAL = 900


@dataclass(frozen=True)
class Feed:
    id: str
    publisher: str
    url: str
    hosts: tuple[str, ...]
    terms_url: str
    permission_note: str
    enabled_by_default: bool = False
    permission_required: bool = True
    kind: str = "rss"


FEEDS = (
    Feed("bbc", "BBC Sport", "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
         ("www.bbc.com", "www.bbc.co.uk", "bbc.com", "bbc.co.uk"),
         "https://www.bbc.co.uk/usingthebbc/terms/",
         "Проверьте условия RSS BBC для вашего сайта и бота. Для коммерческого использования требуется разрешение."),
    Feed("autosport", "Autosport.com.ru", "https://autosport.com.ru/rss/f1.xml",
         ("autosport.com.ru", "www.autosport.com.ru"), "https://autosport.com.ru/rss",
         "RSS разрешает исходные заголовки с названием источника и прямой ссылкой. Тексты статей не скачиваются и не переписываются.",
         enabled_by_default=True, permission_required=False),
    Feed("openf1-control", "OpenF1", "https://api.openf1.org/v1/race_control",
         ("api.openf1.org",), "https://openf1.org/docs/#race-control",
         "Сообщения дирекции гонки преобразуются в короткие фразы по шаблонам. Используется бесплатный архив после гонки, не платный live-доступ.",
         enabled_by_default=True, permission_required=False, kind="race_control"),
)
FEED_BY_ID = {feed.id: feed for feed in FEEDS}

SCHEMA = """
CREATE TABLE IF NOT EXISTS recap_news_sources (
 source_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
 checked REAL, successful REAL, next_check REAL NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0, error TEXT,
 etag TEXT, last_modified TEXT
);
CREATE TABLE IF NOT EXISTS recap_news_articles (
 id INTEGER PRIMARY KEY AUTOINCREMENT, season INTEGER NOT NULL, round INTEGER NOT NULL,
 event_name TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES recap_news_sources(source_id),
 title TEXT NOT NULL, url TEXT NOT NULL, published REAL NOT NULL,
 category TEXT NOT NULL, score INTEGER NOT NULL, hidden INTEGER NOT NULL DEFAULT 0,
 added REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(season,round,url)
);
CREATE INDEX IF NOT EXISTS idx_recap_news_round ON recap_news_articles(season,round,hidden,score);
CREATE TABLE IF NOT EXISTS recap_control_checks (
 season INTEGER NOT NULL, round INTEGER NOT NULL, session_key INTEGER NOT NULL,
 updated REAL NOT NULL, next_check REAL NOT NULL, final INTEGER NOT NULL DEFAULT 0,
 parser_version INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(season,round)
);
"""


async def ensure_schema(conn):
    await conn.executescript(SCHEMA)
    columns = {row[1] for row in await (await conn.execute("PRAGMA table_info(recap_control_checks)")).fetchall()}
    if "parser_version" not in columns:
        try:
            await conn.execute("ALTER TABLE recap_control_checks ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 0")
        except aiosqlite.OperationalError:
            # Bot and web can migrate the shared database at the same startup.
            columns = {row[1] for row in await (await conn.execute("PRAGMA table_info(recap_control_checks)")).fetchall()}
            if "parser_version" not in columns:
                raise
    await conn.executemany("INSERT OR IGNORE INTO recap_news_sources(source_id,enabled) VALUES(?,?)",
                           [(feed.id, int(feed.enabled_by_default)) for feed in FEEDS])
    # Retire the permission-dependent publisher without deleting its archive.
    await conn.execute("UPDATE recap_news_sources SET enabled=0 WHERE source_id IN ('championat-news','championat-articles')")


@asynccontextmanager
async def connection(*, readonly=False):
    # A public request must not create a database or perform schema migrations.
    path = db.db_path.as_uri() + "?mode=ro" if readonly else str(db.db_path)
    async with aiosqlite.connect(path, uri=readonly, timeout=2 if readonly else 10) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


def normalize(text):
    value = unicodedata.normalize("NFKD", str(text)).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c))))


def contains(text, terms):
    return any(re.search(r"(?<!\w)" + re.escape(term), text) for term in terms)


EVENT_ALIASES = {
    "azerbaijan": ("азербайджан", "баку", "azerbaijan", "baku"),
    "australian": ("австрали", "мельбурн", "australia", "melbourne"),
    "chinese": ("кита", "шанха", "china", "chinese", "shanghai"),
    "japanese": ("япони", "сузук", "japan", "suzuka"),
    "bahrain": ("бахрейн", "bahrain", "сахир", "sakhir"),
    "saudi arabian": ("саудовск", "джидд", "saudi", "jeddah"),
    "miami": ("майами", "miami"),
    "canadian": ("канад", "монреал", "canada", "canadian", "montreal"),
    "monaco": ("монако", "monaco"),
    "barcelona": ("барселон", "каталон", "barcelona", "catalunya"),
    "spanish": ("испан", "мадрид", "мадринг", "spanish", "spain", "madrid", "madring"),
    "austrian": ("австри", "шпильберг", "austria", "spielberg"),
    "british": ("британи", "сильверстоун", "british", "silverstone"),
    "belgian": ("бельги", "belgian", "belgium", "spa francorchamps", "спа франкоршам"),
    "hungarian": ("венгри", "хунгароринг", "hungarian", "hungary", "hungaroring"),
    "dutch": ("нидерланд", "голланди", "зандворт", "dutch", "zandvoort"),
    "italian": ("гран при италии", "монц", "italian grand prix", "monza"),
    "emilia romagna": ("эмильи романьи", "имол", "emilia romagna", "imola"),
    "singapore": ("сингапур", "singapore"),
    "united states": ("остин", "austin", "united states grand prix", "гран при сша"),
    "mexico": ("мексик", "mexic"),
    "sao paulo": ("бразили", "сан паулу", "интерлагос", "brazil", "sao paulo", "interlagos"),
    "las vegas": ("лас вегас", "las vegas"),
    "qatar": ("катар", "лусаил", "qatar", "lusail"),
    "abu dhabi": ("абу даби", "abu dhabi", "yas marina", "яс марин"),
}

EXCLUDED = (
    "квалификац", "свободн", "тренировк", "спринт", "qualif", "practice", "sprint",
    "превью", "прогноз", "предстоящ", "ожидан", "расписан", "трансляци", "preview",
    "prediction", "schedule", "how to watch", "live stream", "ahead of", "before the race",
    "контракт", "трансфер", "зарплат", "слух", "rumour", "rumor", "contract", "salary",
    "вспомин", "лет назад", "историческ", "ретро", "anniversary", "years ago", "remember",
    "опрос", "голосован", "рейтинг", "quiz", "vote", "теннис", "футбол", "хоккей",
)
TOPICS = (
    ("incident", 100, ("авари", "столкнов", "сход", "вылет", "завал", "прокол", "полом", "отказ", "crash", "collision", "retire", "puncture", "failure")),
    ("penalty", 90, ("штраф", "дисквалиф", "стюард", "penalt", "disqualif", "steward")),
    ("strategy", 80, ("пит стоп", "тактик", "стратег", "шин", "pit stop", "strategy", "tyre", "tire")),
    ("battle", 75, ("дуэль", "борьб", "обгон", "рестарт", "финиш", "battle", "overtak", "restart", "finish")),
    ("race", 50, ("гонк", "итоги", "побед", "подиум", "race", "victory", "win", "podium")),
)


def canonical_url(value, feed):
    try:
        value = unescape(value.strip())
        parts = urlsplit(value)
        if (len(value) > 1000 or any(c.isspace() or ord(c) < 32 for c in value)
                or "\\" in value or parts.scheme != "https" or parts.hostname not in feed.hosts
                or parts.username or parts.password or parts.port not in (None, 443)):
            return None
        if feed.kind == "race_control":
            if (parts.path != "/v1/race_control" or not re.fullmatch(r"session_key=[1-9]\d{0,9}", parts.query)
                    or not re.fullmatch(r"event-[0-9a-f]{16}", parts.fragment)):
                return None
            return urlunsplit(("https", parts.hostname, parts.path, parts.query, parts.fragment))
        if not parts.path.startswith("/f1/" if feed.id == "autosport" else "/sport/"):
            return None
        # Publishers use path-based article IDs; drop tracking parameters/fragments.
        return urlunsplit(("https", parts.hostname, parts.path, "", ""))
    except ValueError:
        return None


def parse_feed(content: bytes, feed: Feed) -> list[dict]:
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("unsafe_feed")
    # All configured feeds use UTF-8. Decode before the DTD guard so a UTF-16
    # declaration cannot evade it with NUL-separated bytes.
    xml = content.decode("utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml, re.I):
        raise ValueError("unsafe_feed")
    root = ElementTree.fromstring(xml)
    if root.tag != "rss":
        raise ValueError("invalid_feed")
    entries = []
    for item in root.findall("./channel/item")[:200]:
        title = " ".join(unescape(re.sub(r"<[^>]*>", "", item.findtext("title") or "")).split())
        url = canonical_url(item.findtext("link") or "", feed)
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            if not published.tzinfo:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        if not url or not 5 <= len(title) <= 240:
            continue
        # Description is only transient filtering evidence, never copied or stored.
        context = " ".join(unescape(re.sub(r"<[^>]*>", "", item.findtext("description") or "")).split())[:2000]
        entries.append({"title": title, "url": url, "published": published.timestamp(),
                        "source_id": feed.id, "context": context})
    return entries


def candidates(entries, event, season, now):
    name = normalize(event.get("event_name", ""))
    aliases = next((terms for key, terms in EVENT_ALIASES.items() if contains(name, (key,))), ())
    # Unknown circuits fail closed: a driver name alone cannot identify a race.
    if not aliases:
        return []
    try:
        start = datetime.fromisoformat(event["race_start_utc"].replace("Z", "+00:00"))
        if not start.tzinfo:
            return []
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    result = []
    for entry in entries:
        if not start.timestamp() <= entry["published"] <= min(now.timestamp(), (start + timedelta(days=4)).timestamp()):
            continue
        headline = normalize(entry["title"])
        attribution = normalize(entry["title"] + " " + unquote(urlsplit(entry["url"]).path))
        context = normalize(entry["title"] + " " + entry.get("context", ""))
        if (not contains(attribution, aliases) or contains(context, EXCLUDED)
                or any(int(y) != season for y in re.findall(r"\b(?:19|20)\d{2}\b", context))):
            continue
        topic = next(((category, score) for category, score, terms in TOPICS if contains(headline, terms)), None)
        if topic:
            result.append({**entry, "category": topic[0], "score": topic[1]})
    return result[:200]


def select_news(rows, limit=3):
    ordered = sorted(rows, key=lambda row: (-row["score"], -row["published"], row["url"]))
    unique = []
    for row in ordered:
        title = normalize(row["title"])
        words = set(title.split())
        if any(row["url"] == old["url"] or title == normalize(old["title"])
               or SequenceMatcher(None, title, normalize(old["title"])).ratio() >= .86
               or len(words & set(normalize(old["title"]).split())) / max(1, len(words | set(normalize(old["title"]).split()))) >= .8
               for old in unique):
            continue
        unique.append(row)
    # Prefer different kinds of events before filling remaining slots.
    selected, categories = [], set()
    for row in unique:
        if row["category"] not in categories:
            selected.append(row)
            categories.add(row["category"])
            if len(selected) == limit:
                break
    for row in unique:
        if len(selected) >= limit:
            break
        if row not in selected:
            selected.append(row)
    return selected


async def public_news(season, round_num):
    try:
        async with connection(readonly=True) as conn:
            rows = await (await conn.execute("""SELECT a.* FROM recap_news_articles a
                JOIN recap_news_sources s ON s.source_id=a.source_id
                WHERE a.season=? AND a.round=? AND a.hidden=0 AND s.enabled=1
                ORDER BY a.score DESC,a.published DESC LIMIT 200""", (season, round_num))).fetchall()
        valid = [dict(row) for row in rows if row["source_id"] in FEED_BY_ID
                 and FEED_BY_ID[row["source_id"]].kind == "rss"
                 and canonical_url(row["url"], FEED_BY_ID[row["source_id"]])]
        return [{"title": row["title"], "url": row["url"],
                 "publisher": FEED_BY_ID[row["source_id"]].publisher,
                 "published_at": datetime.fromtimestamp(row["published"], timezone.utc).isoformat()}
                for row in select_news(valid)]
    except aiosqlite.Error:
        logger.warning("Recap news storage unavailable; statistical recap is unchanged")
        return []


async def save_candidates(conn, entries, event, season, now):
    for entry in entries:
        await conn.execute("""INSERT INTO recap_news_articles
            (season,round,event_name,source_id,title,url,published,category,score,added,updated)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(season,round,url) DO UPDATE SET
            title=excluded.title,category=excluded.category,score=excluded.score,updated=excluded.updated""",
            (season, event["round"], event["event_name"], entry["source_id"], entry["title"],
             entry["url"], entry["published"], entry["category"], entry["score"], now.timestamp(), now.timestamp()))


async def fetch_feed(client, feed, state):
    headers = {"User-Agent": "F1Hub-RaceRecap/1.0", "Accept": "application/rss+xml, application/xml, text/xml"}
    for key, column in (("If-None-Match", "etag"), ("If-Modified-Since", "last_modified")):
        if state.get(column):
            headers[key] = state[column]
    async with client.stream("GET", feed.url, headers=headers) as response:
        if response.status_code == 304:
            return None, {}
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_FEED_BYTES:
                raise ValueError("oversized_feed")
        # Never follow redirects or download linked articles.
        return parse_feed(bytes(content), feed), {key: response.headers.get(key, "")[:500]
                                                   for key in ("etag", "last-modified")}


async def refresh_recent_news():
    """One bounded background pass. No network on public reads."""
    try:
        await asyncio.wait_for(_refresh_recent_news(), timeout=55)
    except Exception:
        logger.warning("Race news refresh failed; retained previous headlines", exc_info=True)


def retry_delay(exc, failures, now):
    delay = min(3600, INTERVAL * 2 ** min(failures, 2))
    if isinstance(exc, httpx.HTTPStatusError):
        value = exc.response.headers.get("Retry-After", "")
        try:
            requested = float(value) if value.isdigit() else (parsedate_to_datetime(value) - now).total_seconds()
            delay = max(delay, min(86400, requested))
        except (ValueError, TypeError, OverflowError):
            pass
    return delay


async def record_failure(source_id, error, now, delay):
    async with connection() as conn:
        await conn.execute("""UPDATE recap_news_sources SET checked=?,next_check=?,failures=failures+1,error=?
            WHERE source_id=? AND enabled=1""", (now.timestamp(), now.timestamp() + delay, error, source_id))
        await conn.commit()


async def _refresh_recent_news():
    from app.f1_data import get_season_schedule_short_async

    now = datetime.now(timezone.utc)
    async with connection() as conn:
        states = [dict(row) for row in await (await conn.execute(
            "SELECT * FROM recap_news_sources WHERE enabled=1 AND next_check<=?", (now.timestamp(),))).fetchall()
                  if row["source_id"] in FEED_BY_ID and FEED_BY_ID[row["source_id"]].kind == "rss"]
    if not states:
        return
    try:
        schedule = await asyncio.wait_for(get_season_schedule_short_async(now.year), timeout=15)
        if not schedule:
            raise ValueError("missing_schedule")
    except Exception:
        for state in states:
            await record_failure(state["source_id"], "Календарь гонок временно недоступен; новости не проверены", now, INTERVAL)
        return
    events = []
    for event in schedule or []:
        try:
            start = datetime.fromisoformat(event["race_start_utc"].replace("Z", "+00:00"))
            if not event.get("is_cancelled") and start.tzinfo and timedelta(hours=1) <= now - start <= timedelta(days=10):
                events.append(event)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if not events:
        return
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for state in states:
            feed = FEED_BY_ID.get(state["source_id"])
            if not feed:
                continue
            try:
                entries, validators = await asyncio.wait_for(fetch_feed(client, feed, state), timeout=12)
                async with connection() as conn:
                    await conn.execute("BEGIN IMMEDIATE")
                    enabled = await (await conn.execute("SELECT enabled FROM recap_news_sources WHERE source_id=?", (feed.id,))).fetchone()
                    if not enabled or not enabled[0]:
                        continue  # permission revoked while the request was in flight
                    if entries is not None:
                        for event in events:
                            await save_candidates(conn, candidates(entries, event, now.year, now), event, now.year, now)
                    await conn.execute("""UPDATE recap_news_sources SET checked=?,successful=?,next_check=?,
                        failures=0,error=NULL,etag=COALESCE(?,etag),last_modified=COALESCE(?,last_modified) WHERE source_id=?""",
                        (now.timestamp(), now.timestamp(), now.timestamp() + INTERVAL,
                         validators.get("etag"), validators.get("last-modified"), feed.id))
                    await conn.commit()
            except (httpx.HTTPError, TimeoutError, ValueError, ElementTree.ParseError) as exc:
                error = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else "Лента временно недоступна или имеет неверный формат"
                await record_failure(feed.id, error, now, retry_delay(exc, state["failures"], now))
