import asyncio
import io
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from PIL import Image, ImageDraw

from app.services import pirelli_motorsport as service


def event(name='United States Grand Prix', location='Austin', round=18):
    return {'event_name': name, 'location': location, 'round': round, 'date': '2026-10-25'}


ALLOCATION = ['For the United States Grand Prix in Austin (23-25 October), the compounds will be C2 as Hard, C3 as Medium and C4 as Soft. For the Mexico City Grand Prix and the São Paulo Grand Prix, the softest trio has been selected: C3 as Hard, C4 as Medium and C5 as Soft.']


def test_allocations_bound_to_sentence_venue_and_year():
    assert service.compound_selection(ALLOCATION, event(), season=2026) == ['C2', 'C3', 'C4']
    assert service.compound_selection(ALLOCATION, event('Mexico City Grand Prix', 'Mexico City'), season=2026) == ['C3', 'C4', 'C5']
    assert service.compound_selection(ALLOCATION, event('São Paulo Grand Prix', 'São Paulo'), season=2026) == ['C3', 'C4', 'C5']
    assert service.compound_selection(ALLOCATION, event('Miami Grand Prix', 'Miami'), season=2026) is None
    for text in ['Last year C1 as Hard, C3 as Medium and C4 as Soft.', 'In 2025 C1 as Hard, C3 as Medium and C4 as Soft.', 'C3 as Hard, C2 as Medium and C4 as Soft.']:
        assert service.compound_selection([text], event(), True, 2026) is None
    assert service.compound_selection(['In 2026 C2 as Hard, C3 as Medium and C4 as Soft.'], event(), True, 2026) == ['C2', 'C3', 'C4']


def test_article_uses_exact_stage_tag_and_season():
    meta = {'keywords': ['Pirelli', '2026 United States Grand Prix']}
    assert service.article_matches(meta, event(), 2026)
    assert not service.article_matches(meta, event(), 2025)
    assert not service.article_matches(meta, event('Miami Grand Prix'), 2026)


def infographic(monkeypatch, bad=False):
    image = Image.new('RGB', (1920, 1080), '#111111')
    draw = ImageDraw.Draw(image)
    def word(text, x, y):
        return {'text': text, 'left': x, 'top': y, 'width': len(text) * 10, 'height': 22}
    words = [word('2026', 20, 20), word('AUSTIN', 100, 80), word('PREVIEW', 250, 80)]
    for i, (english, _) in enumerate(service.RATINGS[:7]):
        x, y = 60 + i % 3 * 300, 200 + i // 3 * 110
        words.extend(word(part, x + sum(len(p) * 10 + 7 for p in english.split()[:j]), y) for j, part in enumerate(english.split()))
        for k in range(5):
            selected = k == i % 5 or bad and i == 0 and k == 4
            draw.rectangle((x + k * 42, y + 29, x + k * 42 + 31, y + 60), fill='#ff1111' if selected else None, outline='#cccccc')
    monkeypatch.setattr(service, 'ocr_words', lambda _: words)
    body = io.BytesIO()
    image.save(body, format='PNG')
    return body.getvalue()


def test_infographic_reads_selected_boxes_and_rejects_ambiguity(monkeypatch):
    result = service.parse_infographic(infographic(monkeypatch), 2026, 'Austin')
    assert [r['value'] for r in result['ratings']] == [1, 2, 3, 4, 5, 1, 2]
    with pytest.raises(ValueError, match='rating layout'):
        service.parse_infographic(infographic(monkeypatch, bad=True), 2026, 'Austin')
    with pytest.raises(ValueError, match='mismatch'):
        service.parse_infographic(infographic(monkeypatch), 2025, 'Austin')
    with pytest.raises(ValueError, match='mismatch'):
        service.parse_infographic(infographic(monkeypatch), 2026, 'Mexico City')


@pytest.mark.asyncio
async def test_fetch_allowlist_redirect_and_size():
    calls = []
    def transport(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'https://example.com/'}) if request.url.path == '/redirect' else httpx.Response(200, content=b'12345')
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        for url in ['http://press.pirelli.com/', 'https://example.com/', 'https://press.pirelli.com:8443/', 'https://user@press.pirelli.com/']:
            with pytest.raises(ValueError):
                await service.fetch(client, url)
        assert calls == []
        with pytest.raises(httpx.HTTPStatusError):
            await service.fetch(client, 'https://press.pirelli.com/redirect')
        assert len(calls) == 1
        with pytest.raises(ValueError, match='size'):
            await service.fetch(client, 'https://press.pirelli.com/', limit=4)


def race(year, round, driver='hamilton', team='mercedes', lap='1:40.000'):
    return {'season': str(year), 'round': str(round), 'Results': [{'Driver': {'driverId': driver, 'givenName': driver.title(), 'familyName': 'Driver'}, 'Constructor': {'constructorId': team, 'name': team.title()}, 'FastestLap': {'Time': {'time': lap}}}]}


@pytest.mark.asyncio
async def test_history_is_circuit_specific_excludes_selected_and_future_races():
    paths = []
    def transport(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/2026/18.json'):
            races = [{'season': '2026', 'round': '18', 'Circuit': {'circuitId': 'americas', 'circuitName': 'Circuit of The Americas'}}]
        else:
            assert '/circuits/americas/' in request.url.path
            races = [race(2012, 19), race(2013, 17, 'vettel', 'red_bull'), race(2025, 19, lap='1:36.169'), race(2026, 18, 'norris', lap='1:00.000'), race(2027, 18, 'norris', lap='0:55.000')]
        return httpx.Response(200, json={'MRData': {'total': str(len(races)), 'RaceTable': {'Races': races}}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await service.circuit_records(client, 2026, 18)
    assert result['team'] == {'name': 'Mercedes', 'wins': 2}
    assert result['driver']['wins'] == 2
    assert result['firstRace'] == 2012
    assert result['historyThrough'] == 2025
    assert result['lapRecord']['time'] == '1:36.169'
    assert len(paths) == 3


@pytest.mark.asyncio
async def test_cached_profile_identity_stale_and_archive(monkeypatch):
    from app import f1_data
    async def schedule(_):
        return [event()]
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', schedule)
    data = {'version': service.VERSION, 'checked': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), 'stages': {'2026:18': {'season': 2026, 'round': 18, 'eventName': event()['event_name'], 'compounds': ['C2', 'C3', 'C4'], 'ratingSource': 'https://press.pirelli.com/preview/'}}}
    service.write_snapshot(data)
    assert (await service.get_profile(2026, 18))['status'] == 'stale'
    assert (await service.get_profile(2025, 18))['profile'] is None
    assert (await service.get_profile(2026, 19))['profile'] is None
    data['stages']['2026:18']['eventName'] = 'Miami Grand Prix'
    service.write_snapshot(data)
    assert (await service.get_profile(2026, 18))['profile'] is None


@pytest.mark.asyncio
async def test_failed_ocr_retains_validated_values_and_retries(monkeypatch):
    from app import f1_data
    today = datetime.now(timezone.utc).date().isoformat()
    stage = dict(event(), date=today)
    async def schedule(_):
        return [stage]
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', schedule)
    source = 'https://press.pirelli.com/test-preview/'
    metadata = {'@type': 'Article', 'datePublished': '2026-10-20', 'dateModified': '2026-10-21', 'inLanguage': 'en-GB', 'keywords': ['2026 United States Grand Prix']}
    image_body = [b'image']
    async def fetch(client, url, limit=0):
        if '?h=1' in url:
            return f'<a class="text_latestnews_more" href="{source}">Preview</a>'.encode()
        if url == source:
            return f'<script type="application/ld+json">{json.dumps(metadata)}</script><a data-filename="18-us26-preview-en.jpg" data-sourcepath="https://content.presspage.com/preview-en.jpg"></a>'.encode()
        return image_body[0]
    async def records(*_):
        return None
    monkeypatch.setattr(service, 'fetch', fetch)
    monkeypatch.setattr(service, 'circuit_records', records)
    monkeypatch.setattr(service, 'parse_infographic', lambda *_: (_ for _ in ()).throw(ValueError('changed layout')))
    old = {'season': 2026, 'round': 18, 'eventName': stage['event_name'], 'ratings': [{'label': 'Торможение', 'value': 3}], 'ratingSource': source, 'ratingPublished': '2026-10-20', 'compounds': ['C2', 'C3', 'C4'], 'pressures': {'front': '26,5 psi', 'rear': '25,5 psi'}}
    service.write_snapshot({'version': 1, 'stages': {'2026:18': old}, 'articles': {source: '2026-10-20'}})
    with pytest.raises(RuntimeError, match='partially failed'):
        await service.refresh_profiles(2026)
    saved = service.read_snapshot()
    assert saved['stages']['2026:18']['ratings'] == old['ratings']
    assert saved['stages']['2026:18']['pressures'] == old['pressures']
    assert saved['articles'][source] == '2026-10-20'
    assert (await service.get_profile(2026, 18))['profile']['stale']
    monkeypatch.setattr(service, 'parse_infographic', lambda *_: {'ratings': [{'label': 'Торможение', 'value': 4}]})
    await service.refresh_profiles(2026)
    assert service.read_snapshot()['stages']['2026:18']['ratings'][0]['value'] == 4
    assert not service.read_snapshot()['errors']
    assert 'pressures' not in service.read_snapshot()['stages']['2026:18']
    monkeypatch.setattr(service, 'parse_infographic', lambda *_: (_ for _ in ()).throw(AssertionError('unchanged image should reuse validated OCR')))
    await service.refresh_profiles(2026)
    image_body[0] = b'amended pressure infographic, same article date'
    monkeypatch.setattr(service, 'parse_infographic', lambda *_: {'ratings': [{'label': 'Торможение', 'value': 5}]})
    await service.refresh_profiles(2026)
    assert service.read_snapshot()['stages']['2026:18']['ratings'][0]['value'] == 5


@pytest.mark.asyncio
async def test_public_api_validation_and_cached_response(monkeypatch):
    from fastapi import FastAPI
    from app.api import f1_insights_api
    app = FastAPI()
    app.include_router(f1_insights_api.router)
    async def profile(season, round):
        return {'status': 'unavailable', 'season': season, 'round': round, 'profile': None}
    monkeypatch.setattr(f1_insights_api, 'get_profile', profile)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.get('/api/circuit-profile?season=2026&round=18')
        assert result.status_code == 200
        assert result.json()['profile'] is None
        assert result.headers['cache-control'] == 'public, max-age=300'
        assert (await client.get('/api/circuit-profile?season=2026&round=0')).status_code == 422


def test_pressure_needs_independent_full_image_corroboration(monkeypatch):
    from types import SimpleNamespace
    body = infographic(monkeypatch)
    words = service.ocr_words(None)
    def word(text, x, y, confidence=95):
        return {'text': text, 'left': x, 'top': y, 'width': 35, 'height': 22, 'conf': confidence}
    words.extend([word('STARTING', 100, 830), word('FRONT', 234, 906), word('REAR', 490, 906), word('26.5', 220, 877), word('25.5', 475, 877)])
    readings = iter([b'26.5psi', b'26.5psi', b'15.5psi', b'15.5psi'])
    monkeypatch.setattr(service.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(stdout=next(readings)))
    assert 'pressures' not in service.parse_infographic(body, 2026, 'Austin')
    readings = iter([b'26.5psi', b'26.5psi', b'25.5psi', b'25.5psi'])
    assert service.parse_infographic(body, 2026, 'Austin')['pressures'] == {'front': '26,5 psi', 'rear': '25,5 psi'}


@pytest.mark.asyncio
async def test_history_rate_limit_stops_batch_and_respects_retry_after(monkeypatch):
    from app import f1_data
    async def schedule(_):
        return [event(round=i) for i in range(1, 4)]
    async def empty_index(client, url, **_kwargs):
        if '?h=1' in url:
            return b'<a class="text_latestnews_more" href="https://press.pirelli.com/old/">Older story</a>'
        return b'<script type="application/ld+json">{"@type":"Article","datePublished":"2025-01-01","inLanguage":"en-GB"}</script>'
    calls = []
    async def limited(*args):
        calls.append(args[-1])
        response = httpx.Response(429, headers={'Retry-After': '7200'}, request=httpx.Request('GET', 'https://api.jolpi.ca/ergast/f1/2026/1.json'))
        response.raise_for_status()
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', schedule)
    monkeypatch.setattr(service, 'fetch', empty_index)
    monkeypatch.setattr(service, 'circuit_records', limited)
    with pytest.raises(RuntimeError, match='429'):
        await service.refresh_profiles(2026)
    assert len(calls) == 1
    assert datetime.fromisoformat(service.read_snapshot()['recordsRetryAt']) > datetime.now(timezone.utc) + timedelta(hours=1)
    with pytest.raises(RuntimeError, match='Retry-After'):
        await service.refresh_profiles(2026)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_changed_index_keeps_previous_snapshot(monkeypatch):
    from app import f1_data
    async def schedule(_):
        return [event()]
    async def broken_index(*_args, **_kwargs):
        return b'<html>New layout</html>'
    monkeypatch.setattr(f1_data, 'get_season_schedule_short_async', schedule)
    monkeypatch.setattr(service, 'fetch', broken_index)
    original = {'version': 1, 'checked': '2026-10-20T12:00:00+00:00', 'stages': {'2026:18': {'compounds': ['C2', 'C3', 'C4']}}}
    service.write_snapshot(original)
    with pytest.raises(RuntimeError, match='index'):
        await service.refresh_profiles(2026)
    assert service.read_snapshot() == original
