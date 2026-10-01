"""News tests use invented headlines, local SQLite and mock RSS transports only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api import admin_tools_api as admin, f1_insights_api as api
from app.db import Database
from app.services import recap_news as news, race_recap as recap
from app.utils.telegram_presentation import race_card, race_fallback

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
EVENT = {"round": 15, "event_name": "Azerbaijan Grand Prix", "race_start_utc": "2026-09-26T11:00:00Z"}
FEED = news.FEED_BY_ID["bbc"]


def article(title="Baku race: collision and retirement", path="baku-race-1", **extra):
    return {"title": title, "url": f"https://www.bbc.com/sport/formula1/{path}",
            "published": NOW.timestamp() - 3600, "source_id": FEED.id, "context": "", **extra}


def rss(title="Baku race: collision and retirement", *, url="https://www.bbc.com/sport/formula1/baku-race-1", date="Sun, 27 Sep 2026 11:00:00 GMT", description=""):
    return (f'<rss version="2.0"><channel><item><title><![CDATA[{title}]]></title><link>{url}</link>'
            f'<pubDate>{date}</pubDate><description><![CDATA[{description}]]></description></item></channel></rss>').encode()


@pytest_asyncio.fixture
async def workspace(temp_db_path, monkeypatch):
    database = Database(temp_db_path)
    await database.connect()
    try:
        await database.init_tables()
        # Existing opt-in cases isolate BBC from the two newly enabled sources.
        await database.conn.execute("UPDATE recap_news_sources SET enabled=0")
        await database.conn.execute("INSERT INTO users(id,role,telegram_id) VALUES(1,'admin',900001)")
        await database.conn.commit()
        monkeypatch.setattr(news, "db", database)
        monkeypatch.setattr(admin, "db", database)
        application = FastAPI()
        application.include_router(admin.router)
        application.include_router(api.router)
        application.dependency_overrides[admin.require_admin_session] = lambda: admin.AdminContext(id=1, role="admin")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            yield database, application, client
    finally:
        await database.close()


def test_parse_preserves_original_title_and_discards_html_tracking():
    rows = news.parse_feed(rss('Baku: <b>collision</b> &amp; restart', url="https://www.bbc.com/sport/formula1/a?utm_source=test#part"), FEED)
    assert rows[0]["title"] == "Baku: collision & restart"
    assert rows[0]["url"] == "https://www.bbc.com/sport/formula1/a"
    assert rows[0]["source_id"] == "bbc"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://www.bbc.com.evil.test/sport/a", "https://www.bbc.com@evil.test/sport/a",
                                    "https://user:pass@www.bbc.com/sport/a", "https://www.bbc.com:8080/sport/a", "http://www.bbc.com/sport/a",
                                    "https://www.bbc.com\\evil.test/sport/a", "https://127.0.0.1/sport/a", "https://www.bbc.com/news/a"])
def test_untrusted_urls_are_rejected(url):
    assert news.parse_feed(rss(url=url), FEED) == []


@pytest.mark.parametrize("date", ["", "garbage", "Sun, 27 Sep 2026 11:00:00"])
def test_undated_or_timezone_ambiguous_items_are_rejected(date):
    assert news.parse_feed(rss(date=date), FEED) == []


@pytest.mark.parametrize("content", [b'<!DOCTYPE rss [<!ENTITY foo "bar">]><rss/>', b"x" * (news.MAX_FEED_BYTES + 1), b"<html>blocked</html>",
                                    '<!DOCTYPE rss [<!ENTITY foo "bar">]><rss/>'.encode('utf-16')], ids=["doctype", "oversized", "html", "utf16-doctype"])
def test_unsafe_or_wrong_feed_is_rejected(content):
    with pytest.raises(ValueError):
        news.parse_feed(content, FEED)


def test_filters_event_date_topic_and_retrospective_context():
    entries = [article(), article("Baku race strategy: a late pit stop", "strategy"),
               article("Baku race: qualifying crash", "quali"), article("Baku race preview: who will win?", "preview"),
               article("Baku collision: rumours about a new contract", "contract"),
               article("Baku crash recalled", "retro", context="The 2018 race was memorable."),
               article("Monza race: a collision", "other"), article("Driver wins after a collision", "no-race"),
               article("Baku: new helmet design", "not-topic"),
               article("Baku race: collision before start", "early", published=NOW.timestamp() - 100000),
               article("Baku race: finish battle", "future", published=NOW.timestamp() + 1),
               article("Baku race: finish battle", "too-late", published=(NOW + timedelta(days=5)).timestamp())]
    result = news.candidates(entries, EVENT, 2026, NOW)
    assert [entry["category"] for entry in result] == ["incident", "strategy"]
    assert news.candidates(entries, {**EVENT, "event_name": "Unknown Grand Prix"}, 2026, NOW) == []


def test_russian_stems_and_event_aliases_are_supported():
    result = news.candidates([article("Гонка в Баку: штраф за столкновение", context="Объяснение инцидента на Гран-при Азербайджана")], EVENT, 2026, NOW)
    assert len(result) == 1
    assert result[0]["title"] == "Гонка в Баку: штраф за столкновение"


def test_autosport_rss_uses_original_titles_and_direct_f1_links():
    feed = news.FEED_BY_ID['autosport']
    title = 'Гонка в Баку: штраф изменил результат'
    rows = news.parse_feed(rss(title, url='https://autosport.com.ru/f1/123-test'), feed)
    assert len(rows) == 1 and rows[0]['title'] == title
    assert news.candidates(rows, EVENT, 2026, NOW)
    assert news.parse_feed(rss(url='https://autosport.com.ru/news/123'), feed) == []
    assert news.parse_feed(rss(url='https://autosport.com.ru.evil.test/f1/123'), feed) == []


async def test_new_sources_default_on_retired_sources_off_and_disabled_choice_persists(workspace):
    database, _, client = workspace
    await database.conn.execute("DELETE FROM recap_news_sources")
    await database.conn.execute("INSERT INTO recap_news_sources(source_id,enabled) VALUES('championat-news',1)")
    await news.ensure_schema(database.conn)
    await database.conn.commit()
    sources = (await client.get('/api/admin/tools/recap-news?season=2026')).json()['sources']
    assert {s['id'] for s in sources if s['enabled']} == {'autosport', 'openf1-control'}
    assert not any(s['id'].startswith('championat') for s in sources)
    assert (await (await database.conn.execute("SELECT enabled FROM recap_news_sources WHERE source_id='championat-news'")).fetchone())[0] == 0
    for source in ('autosport', 'openf1-control'):
        assert (await client.patch(f'/api/admin/tools/recap-news/sources/{source}', json={'enabled': False})).status_code == 200
    await news.ensure_schema(database.conn)
    await database.conn.commit()
    assert not any(s['enabled'] for s in (await client.get('/api/admin/tools/recap-news?season=2026')).json()['sources'])
    assert (await client.patch('/api/admin/tools/recap-news/sources/autosport', json={'enabled': True})).status_code == 200
    assert (await client.patch('/api/admin/tools/recap-news/sources/championat-news', json={'enabled': True, 'permission_confirmed': True})).status_code == 404


def test_three_distinct_headlines_and_topic_diversity():
    entries = [article(score=100, category="incident"), article(score=100, category="incident", path="duplicate"),
               article("Baku race: collision and retirements", "near-duplicate", score=100, category="incident"),
               article("Baku race: puncture forces a retirement", "puncture", score=100, category="incident"),
               article("Baku race: a late pit stop changes the strategy", "strategy", score=80, category="strategy"),
               article("Baku race: stewards impose a penalty", "penalty", score=90, category="penalty")]
    selected = news.select_news(entries)
    assert len(selected) == 3
    assert {entry["category"] for entry in selected} == {"incident", "strategy", "penalty"}
    assert len({entry["url"] for entry in selected}) == 3


async def insert_news(database):
    entries = news.candidates([article(), article("Baku race: a late pit stop changes strategy", "strategy")], EVENT, 2026, NOW)
    await news.save_candidates(database.conn, entries, EVENT, 2026, NOW)
    await database.conn.commit()
    return entries


async def test_sources_are_opt_in_and_public_reads_never_fetch(workspace, monkeypatch):
    database, _, client = workspace
    await insert_news(database)
    fetch = AsyncMock(side_effect=AssertionError("Public requests cannot fetch RSS"))
    monkeypatch.setattr(news, "fetch_feed", fetch)
    assert await news.public_news(2026, 15) == []
    assert (await client.patch('/api/admin/tools/recap-news/sources/bbc', json={"enabled": True})).status_code == 422
    enabled = await client.patch('/api/admin/tools/recap-news/sources/bbc', json={"enabled": True, "permission_confirmed": True})
    assert enabled.status_code == 200
    result = await news.public_news(2026, 15)
    assert len(result) == 2 and result[0]["publisher"] == "BBC Sport"
    assert not ({"score", "hidden", "context", "source_id"} & result[0].keys())
    assert await news.public_news(2026, 14) == []
    fetch.assert_not_awaited()


async def test_hide_restore_disable_archive_and_idempotent_refresh(workspace, monkeypatch):
    database, _, client = workspace
    entries = await insert_news(database)
    await client.patch('/api/admin/tools/recap-news/sources/bbc', json={"enabled": True, "permission_confirmed": True})
    state = await client.get('/api/admin/tools/recap-news', params={"season": 2026, "round_num": 15})
    assert state.headers["cache-control"] == "no-store"
    identifier = state.json()["items"][0]["id"]
    url = f'/api/admin/tools/recap-news/articles/{identifier}'
    assert (await client.patch(url, json={"hidden": True})).status_code == 200
    await client.patch(url, json={"hidden": True})
    await news.save_candidates(database.conn, entries, EVENT, 2026, NOW)
    await database.conn.commit()
    assert len(await news.public_news(2026, 15)) == 1
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM recap_news_articles")).fetchone())[0] == 2
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM admin_audit_log WHERE action='recap_news.visibility'")).fetchone())[0] == 1
    await client.patch(url, json={"hidden": False})
    assert len(await news.public_news(2026, 15)) == 2
    await client.patch('/api/admin/tools/recap-news/sources/bbc', json={"enabled": False})
    assert await news.public_news(2026, 15) == []
    assert len((await client.get('/api/admin/tools/recap-news', params={"season": 2026})).json()["items"]) == 2


async def test_admin_auth_validation_and_no_prediction_writes(workspace):
    database, application, client = workspace
    assert (await client.patch('/api/admin/tools/recap-news/sources/evil', json={"enabled": False})).status_code == 404
    assert (await client.patch('/api/admin/tools/recap-news/articles/999', json={"hidden": True})).status_code == 404
    assert (await client.get('/api/admin/tools/recap-news', params={"season": 2026, "round_num": 0})).status_code == 422
    application.dependency_overrides.clear()
    for method, path, body in [("GET", '/api/admin/tools/recap-news?season=2026', None),
                               ("PATCH", '/api/admin/tools/recap-news/sources/bbc', {"enabled": True, "permission_confirmed": True}),
                               ("PATCH", '/api/admin/tools/recap-news/articles/1', {"hidden": True})]:
        assert (await client.request(method, path, json=body)).status_code in (401, 403)
    for table in ("race_predictions", "prediction_round_results", "telegram_deliveries"):
        assert (await (await database.conn.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0] == 0


async def test_statistical_cache_not_mutated_and_waiting_has_no_news(workspace, monkeypatch):
    database, _, client = workspace
    await insert_news(database)
    await database.conn.execute("UPDATE recap_news_sources SET enabled=1 WHERE source_id='bbc'")
    await database.conn.commit()
    original = {"season": 2026, "round": 15, "status": "partial", "items": [], "note": "test"}
    monkeypatch.setattr(recap, "get_race_recap", AsyncMock(return_value=original))
    result = await recap.get_race_recap_with_news(2026, 15)
    assert result["news"] and "news" not in original
    response = await client.get('/api/race-recap?season=2026&round_num=15')
    assert response.status_code == 200 and response.json()["news"]
    original["status"] = "waiting"
    assert not (await recap.get_race_recap_with_news(2026, 15))["news"]


def test_both_telegram_presentations_include_links_and_escape_headlines():
    result = {"status": "ready", "items": [], "news": [{"title": 'Baku: <b>collision</b> & restart',
              "url": "https://www.bbc.com/sport/formula1/a", "publisher": "BBC Sport"}]}
    text = recap.format_recap_telegram(result, spoiler=True)
    assert 'class="tg-spoiler"' in text and '&lt;b&gt;collision&lt;/b&gt; &amp;' in text
    assert '<a href="https://www.bbc.com/sport/formula1/a">' in text
    card = race_card("Baku", 2026, 15, [], result).model_dump_json()
    assert 'Интересные моменты гонки' in card and 'BBC Sport' in card and 'https://www.bbc.com/sport/formula1/a' in card
    assert 'Интересные моменты гонки' in race_fallback("Baku", 2026, 15, [], result)


async def test_rss_fetch_is_bounded_conditional_and_rejects_redirects():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=rss(), headers={"ETag": "version-1"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        entries, validators = await news.fetch_feed(client, FEED, {"etag": "old"})
    assert len(entries) == 1 and validators["etag"] == "version-1"
    assert len(calls) == 1 and calls[0].headers["If-None-Match"] == "old"
    for response in [httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
                     httpx.Response(429), httpx.Response(200, content=b'x' * (news.MAX_FEED_BYTES + 1))]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response), follow_redirects=False) as client:
            with pytest.raises((httpx.HTTPStatusError, ValueError)):
                await news.fetch_feed(client, FEED, {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(304))) as client:
        assert await news.fetch_feed(client, FEED, {}) == (None, {})


async def test_background_opt_in_failure_backoff_and_persistence(workspace, monkeypatch):
    database, _, _ = workspace
    from app import f1_data
    schedule = AsyncMock(return_value=[EVENT, {**EVENT, "round": 16, "is_cancelled": True}])
    monkeypatch.setattr(f1_data, "get_season_schedule_short_async", schedule)
    monkeypatch.setattr(news, "datetime", SimpleNamespace(now=lambda zone: NOW, fromisoformat=datetime.fromisoformat))
    fetch = AsyncMock(return_value=([article()], {"etag": "version-1"}))
    monkeypatch.setattr(news, "fetch_feed", fetch)
    await news._refresh_recent_news()
    fetch.assert_not_awaited()
    schedule.assert_not_awaited()
    await database.conn.execute("UPDATE recap_news_sources SET enabled=1 WHERE source_id='bbc'")
    await database.conn.commit()
    await news._refresh_recent_news()
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM recap_news_articles")).fetchone())[0] == 1
    await news._refresh_recent_news()
    assert fetch.await_count == 1  # persisted throttle survives consecutive passes
    await database.conn.execute("UPDATE recap_news_sources SET next_check=0 WHERE source_id='bbc'")
    await database.conn.commit()
    fetch.side_effect = httpx.HTTPStatusError("rate limit", request=httpx.Request('GET', FEED.url), response=httpx.Response(429))
    await news._refresh_recent_news()
    row = await (await database.conn.execute("SELECT * FROM recap_news_sources WHERE source_id='bbc'")).fetchone()
    assert row["error"] == "HTTP 429" and row["next_check"] > NOW.timestamp()
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM recap_news_articles")).fetchone())[0] == 1


async def test_permission_revoked_during_fetch_does_not_store_news(workspace, monkeypatch):
    database, _, _ = workspace
    from app import f1_data
    monkeypatch.setattr(f1_data, "get_season_schedule_short_async", AsyncMock(return_value=[EVENT]))
    monkeypatch.setattr(news, "datetime", SimpleNamespace(now=lambda zone: NOW, fromisoformat=datetime.fromisoformat))
    await database.conn.execute("UPDATE recap_news_sources SET enabled=1 WHERE source_id='bbc'")
    await database.conn.commit()
    async def fetch(*args):
        await database.conn.execute("UPDATE recap_news_sources SET enabled=0 WHERE source_id='bbc'")
        await database.conn.commit()
        return [article()], {}
    monkeypatch.setattr(news, "fetch_feed", fetch)
    await news._refresh_recent_news()
    assert (await (await database.conn.execute("SELECT COUNT(*) FROM recap_news_articles")).fetchone())[0] == 0


@pytest.mark.parametrize("header,expected", [("7200", 7200), ("Mon, 28 Sep 2026 12:00:00 GMT", 86400), ("bad", 900)])
def test_publisher_retry_after_is_respected(header, expected):
    exc = httpx.HTTPStatusError("rate limit", request=httpx.Request('GET', FEED.url), response=httpx.Response(429, headers={"Retry-After": header}))
    assert news.retry_delay(exc, 0, NOW) == expected


async def test_missing_schedule_is_visible_in_admin_without_fetching_feeds(workspace, monkeypatch):
    database, _, client = workspace
    from app import f1_data
    monkeypatch.setattr(f1_data, "get_season_schedule_short_async", AsyncMock(side_effect=TimeoutError()))
    monkeypatch.setattr(news, "datetime", SimpleNamespace(now=lambda zone: NOW, fromisoformat=datetime.fromisoformat))
    fetch = AsyncMock(side_effect=AssertionError("No feed fetch without race attribution"))
    monkeypatch.setattr(news, "fetch_feed", fetch)
    await database.conn.execute("UPDATE recap_news_sources SET enabled=1 WHERE source_id='bbc'")
    await database.conn.commit()
    await news._refresh_recent_news()
    response = await client.get('/api/admin/tools/recap-news', params={"season": 2026})
    source = next(row for row in response.json()["sources"] if row["id"] == 'bbc')
    assert 'Календарь' in source['error'] and source['next_check'] == NOW.timestamp() + news.INTERVAL
    fetch.assert_not_awaited()
