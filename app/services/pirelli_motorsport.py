"""Official Pirelli previews + circuit-specific race history, refreshed by the worker.

Readers never scrape. A bad/changed infographic preserves the last validated values.
The snapshot is shared by web/worker through the existing database data directory.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import hashlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from lxml import html
from PIL import Image, ImageOps

from app.db import db
from app.utils.process_lock import ProcessLock

INTERVAL = 21600
VERSION = 1
HOSTS = {'press.pirelli.com', 'content.presspage.com', 'api.jolpi.ca'}
RATINGS = [
    ('TRACTION', 'Тяга на выходе'), ('TYRE STRESS', 'Нагрузка на шины'),
    ('ASPHALT GRIP', 'Сцепление асфальта'), ('BRAKING', 'Торможение'),
    ('ASPHALT ABRASION', 'Абразивность асфальта'), ('LATERAL', 'Боковая нагрузка'),
    ('TRACK EVOLUTION', 'Эволюция трассы'), ('DOWNFORCE', 'Прижимная сила'),
]


def normal(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()).strip()


def snapshot_path() -> Path:
    return db.db_path.parent / 'pirelli-motorsport.json'


def read_snapshot() -> dict:
    try:
        data = json.loads(snapshot_path().read_text())
        return data if isinstance(data, dict) and data.get('version') == VERSION and isinstance(data.get('stages'), dict) else {'version': VERSION, 'stages': {}, 'articles': {}}
    except (OSError, ValueError):
        return {'version': VERSION, 'stages': {}, 'articles': {}}


def write_snapshot(data: dict) -> None:
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        try:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


class SourceThrottle:
    """Share one request budget across the parallel history lookups in a refresh."""
    def __init__(self):
        self.lock = asyncio.Lock()
        self.next_request = 0.0

    async def __call__(self, request: httpx.Request) -> None:
        if request.url.host != 'api.jolpi.ca':
            return
        async with self.lock:
            loop = asyncio.get_running_loop()
            delay = self.next_request - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self.next_request = loop.time() + .6


async def fetch(client: httpx.AsyncClient, url: str, limit: int = 3_000_000) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise ValueError('Untrusted motorsport source')
    # Do not follow an allowlisted site's redirect onto an untrusted host.
    async with client.stream('GET', url, follow_redirects=False) as response:
        response.raise_for_status()
        parts, size = [], 0
        async for part in response.aiter_bytes():
            size += len(part)
            if size > limit:
                raise ValueError('Motorsport source exceeds size limit')
            parts.append(part)
        return b''.join(parts)


def article_document(body: bytes) -> tuple[object, dict, list[str]]:
    tree = html.fromstring(body)
    metadata = {}
    for raw in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            value = json.loads(raw)
            if isinstance(value, dict) and value.get('@type') in ('Article', 'NewsArticle'):
                metadata = value
                break
        except ValueError:
            continue
    paragraphs = [' '.join(p.text_content().split()) for p in tree.xpath('//div[contains(@class,"textblock")]//p')]
    return tree, metadata, paragraphs


def article_matches(metadata: dict, event: dict, season: int) -> bool:
    keys = metadata.get('keywords', [])
    if isinstance(keys, str):
        keys = keys.split(',')
    return any(normal(str(k)) == normal(f"{season} {event['event_name']}") for k in keys)


def compound_selection(paragraphs: list[str], event: dict, exact_preview: bool = False, season: int | None = None) -> list[str] | None:
    aliases = [normal(event.get('event_name', '')), normal(event.get('location', ''))]
    for paragraph in paragraphs:
        # Allocation releases name several venues. Bind each trio to its sentence.
        for sentence in re.split(r'(?<=[.!?])\s+', paragraph):
            if not exact_preview and not any(a and re.search(r'\b' + re.escape(a) + r'\b', normal(sentence)) for a in aliases):
                continue
            if re.search(r'last year|previous', sentence, re.I) or any(int(year) != season for year in re.findall(r'\b(20\d{2})\b', sentence)):
                continue
            values = [re.findall(r'\b(C[0-6])\s+(?:as\s+)?' + role + r'\b', sentence, re.I) for role in ('Hard', 'Medium', 'Soft')]
            if all(len(v) == 1 for v in values):
                trio = [v[0].upper() for v in values]
                if len(set(trio)) == 3 and list(map(lambda x: int(x[1]), trio)) == sorted(int(x[1]) for x in trio):
                    return trio
    return None


def ocr_words(image: Image.Image) -> list[dict]:
    if not shutil.which('tesseract'):
        raise RuntimeError('Tesseract is required to read Pirelli infographics')
    with tempfile.TemporaryDirectory(prefix='pirelli-ocr-') as folder:
        path = Path(folder) / 'preview.png'
        image.save(path)
        result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', '11', 'tsv'], capture_output=True, timeout=25, check=True)
    return [dict(row, left=int(row['left']), top=int(row['top']), width=int(row['width']), height=int(row['height']))
            for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter='\t') if row.get('text', '').strip() and float(row['conf']) >= 30]


def parse_infographic(body: bytes, season: int, location: str | list[str]) -> dict:
    image = Image.open(io.BytesIO(body))
    if image.width * image.height > 12_000_000 or image.width < 900:
        raise ValueError('Unsupported infographic dimensions')
    image = image.convert('RGB')
    original_scale = image.width / 1920 if image.width > 1920 else 1
    original_words = ocr_words(image)
    if original_scale > 1:
        image = image.resize((1920, round(image.height / original_scale)), Image.Resampling.BICUBIC)
        words = ocr_words(image)
    else:
        words = original_words
    text = ' '.join(w['text'] for w in words if w['top'] < image.height * .16)
    venues = [location] if isinstance(location, str) else location
    if str(season) not in text or not any(normal(venue) in normal(text) for venue in venues if venue) or 'preview' not in normal(text):
        raise ValueError('Infographic season/venue mismatch')
    ratings = []
    for english, label in RATINGS:
        parts = english.split()
        anchor = None
        for word in words:
            if normal(word['text']) != normal(parts[0]):
                continue
            line = sorted([w for w in words if abs(w['top'] - word['top']) < image.height * .012 and word['left'] <= w['left'] < word['left'] + image.width * .17], key=lambda w: w['left'])
            if normal(' '.join(w['text'] for w in line)).startswith(normal(english)):
                anchor = word
        if anchor is None:
            continue
        # Read five aligned scale boxes beneath the label. The stylised digits
        # are unreliable in OCR, so use the uniquely filled red box's position.
        x, y = anchor['left'], anchor['top'] + anchor['height']
        crop = image.crop((max(0, x - 8), y + 2, min(image.width, x + round(image.width * .13)), min(image.height, y + round(image.height * .05))))
        pixels = crop.load()
        mask = {(xx, yy) for yy in range(crop.height) for xx in range(crop.width)
                if min(pixels[xx, yy]) > 120 or (pixels[xx, yy][0] > 170 and pixels[xx, yy][0] > pixels[xx, yy][1] * 1.7)}
        boxes = []
        while mask:
            point = mask.pop()
            todo, component = [point], [point]
            while todo:
                xx, yy = todo.pop()
                for neighbour in ((xx - 1, yy), (xx + 1, yy), (xx, yy - 1), (xx, yy + 1)):
                    if neighbour in mask:
                        mask.remove(neighbour)
                        todo.append(neighbour)
                        component.append(neighbour)
            left, right = min(p[0] for p in component), max(p[0] for p in component)
            top, bottom = min(p[1] for p in component), max(p[1] for p in component)
            width, height = right - left + 1, bottom - top + 1
            if image.height * .018 < height < image.height * .045 and .8 < width / height < 1.2:
                boxes.append((left, top, right + 1, bottom + 1))
        boxes.sort()
        if len(boxes) != 5 or max(b[1] for b in boxes) - min(b[1] for b in boxes) > 3:
            continue
        spacing = [boxes[i + 1][0] - boxes[i][0] for i in range(4)]
        if max(spacing) - min(spacing) > 4:
            continue
        scores = []
        for bounds in boxes:
            box = crop.crop(bounds)
            scores.append(sum(r > 150 and r > g * 1.7 and r > b * 1.7 for r, g, b in box.getdata()) / (box.width * box.height))
        best = max(scores)
        if best > .18 and sum(s > .12 for s in scores) == 1:
            ratings.append({'label': label, 'value': scores.index(best) + 1})
    if len(ratings) < 7:
        raise ValueError(f'Unrecognised Pirelli rating layout ({len(ratings)} validated scales)')
    values = {'ratings': ratings}
    pit = next((w for w in words if normal(w['text']) in ('estimate', 'average')), None)
    if pit:
        nearby = ' '.join(w['text'] for w in words if pit['left'] - 5 <= w['left'] < pit['left'] + image.width * .15 and pit['top'] < w['top'] < pit['top'] + image.height * .1)
        match = re.search(r'\b(\d{1,2}(?:[.,]\d)?)s\b', nearby)
        if match:
            values['pitLoss'] = match[1].replace('.', ',') + ' с'
    starting = next((w for w in words if normal(w['text']) == 'starting'), None)
    pressures = {}
    if starting:
        for axle in ('front', 'rear'):
            word = next((w for w in words if normal(w['text']) == axle and starting['top'] < w['top'] < starting['top'] + image.height * .12 and w['left'] < image.width * .32), None)
            if not word:
                continue
            crop = image.crop((max(0, word['left'] - round(image.width * .0115)), max(0, word['top'] - round(image.height * .0315)), word['left'] + word['width'] + round(image.width * .009), word['top'] - 2))
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop)).resize((crop.width * 5, crop.height * 5))
            readings = []
            with tempfile.TemporaryDirectory(prefix='pirelli-pressure-') as folder:
                path = Path(folder) / 'pressure.png'
                crop.save(path)
                for mode in ('6', '7'):
                    output = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', mode, '-c', 'tessedit_char_whitelist=0123456789.psi'], capture_output=True, timeout=10, check=True).stdout.decode().strip()
                    match = re.fullmatch(r'(\d{2}\.\d)ps[i]?', output)
                    readings.append(match[1] if match and 10 <= float(match[1]) <= 40 else None)
            corroborated = any(w['text'] == readings[0] and float(w.get('conf', 0)) >= 80 and abs(w['left'] / original_scale - word['left']) < image.width * .02 and word['top'] - image.height * .04 < w['top'] / original_scale < word['top'] for w in original_words)
            if readings[0] and readings[0] == readings[1] and corroborated:
                pressures[axle] = readings[0].replace('.', ',') + ' psi'
    if len(pressures) == 2:
        values['pressures'] = pressures
    return values


async def circuit_records(client: httpx.AsyncClient, season: int, round_num: int) -> dict | None:
    base = 'https://api.jolpi.ca/ergast/f1/'
    event = json.loads(await fetch(client, f'{base}{season}/{round_num}.json'))['MRData']['RaceTable']['Races']
    if len(event) != 1 or int(event[0]['season']) != season or int(event[0]['round']) != round_num:
        return None
    circuit = event[0]['Circuit']
    identifier = circuit['circuitId']
    if not re.fullmatch('[a-z0-9_]+', identifier):
        return None

    async def history(path: str) -> list[dict]:
        races = []
        for offset in range(0, 400, 100):
            data = json.loads(await fetch(client, f'{base}circuits/{identifier}/{path}.json?limit=100&offset={offset}'))['MRData']
            races.extend(data['RaceTable']['Races'])
            if offset + 100 >= int(data['total']):
                break
        else:
            raise ValueError('Circuit history pagination limit exceeded')
        return [r for r in races if (int(r['season']), int(r['round'])) < (season, round_num)]

    races, fastest = await asyncio.gather(history('results/1'), history('fastest/1/results'))
    if not races:
        return None
    def winners(key: str) -> dict:
        counts, names = Counter(), {}
        for race in races:
            participant = race['Results'][0][key]
            ident = participant['driverId' if key == 'Driver' else 'constructorId']
            counts[ident] += 1
            names[ident] = f"{participant['givenName']} {participant['familyName']}" if key == 'Driver' else participant['name']
        maximum = max(counts.values())
        return {'name': ' / '.join(names[i] for i in sorted(counts) if counts[i] == maximum), 'wins': maximum}
    laps = []
    for race in fastest:
        for result in race.get('Results', []):
            lap = result.get('FastestLap', {})
            value = lap.get('Time', {}).get('time', '')
            if re.fullmatch(r'\d+:\d{2}\.\d{3}', value):
                minutes, seconds = value.split(':')
                driver = result['Driver']
                laps.append((int(minutes) * 60 + float(seconds), {'time': value, 'driver': f"{driver['givenName']} {driver['familyName']}", 'year': int(race['season'])}))
    return {'name': circuit['circuitName'], 'team': winners('Constructor'), 'driver': winners('Driver'),
            'firstRace': min(int(r['season']) for r in races), 'historyThrough': max(int(r['season']) for r in races),
            'lapRecord': min(laps, key=lambda pair: pair[0])[1] if laps else None,
            'historySource': f'{base}circuits/{identifier}/results/1.json?limit=100', 'circuitId': identifier}


async def refresh_profiles(season: int | None = None) -> None:
    with ProcessLock(db.db_path.with_suffix('.pirelli.lock')):
        await _refresh_profiles(season)


async def _refresh_profiles(season: int | None = None) -> None:
    from app.f1_data import get_season_schedule_short_async
    now = datetime.now(timezone.utc)
    season = season or now.year
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        raise RuntimeError('Pirelli refresh needs the season schedule')
    data = read_snapshot()
    errors = []
    async with httpx.AsyncClient(timeout=20, event_hooks={'request': [SourceThrottle()]}, headers={'User-Agent': 'TurboTears/1.0 (circuit facts; official sources)'}) as client:
        urls = []
        for index in (f'https://press.pirelli.com/?h=1&t={season}%20tyre%20compound%20choices', 'https://press.pirelli.com/?h=1&t=Formula%201'):
            tree = html.fromstring(await fetch(client, index))
            urls.extend(tree.xpath('//a[contains(@class,"text_latestnews_more")]/@href'))
        if not urls:
            raise RuntimeError('Pirelli publication index contains no article links')
        articles = data.setdefault('articles', {})
        for url in list(dict.fromkeys(urls))[:60]:
            try:
                tree, meta, paragraphs = article_document(await fetch(client, url))
                if not meta:
                    raise ValueError('Pirelli article metadata is unavailable')
                published = str(meta.get('datePublished', ''))
                if not published.startswith(str(season)) or meta.get('inLanguage', '').startswith('en') is False:
                    continue
                for event in schedule:
                    exact = article_matches(meta, event, season)
                    compounds = compound_selection(paragraphs, event, exact, season)
                    if not exact and not compounds:
                        continue
                    key = f"{season}:{event['round']}"
                    profile = data['stages'].setdefault(key, {'season': season, 'round': event['round'], 'eventName': event['event_name'], 'name': event['location'], 'ratings': [], 'compounds': [], 'sources': []})
                    # Event identity must agree even if a calendar has been revised.
                    if profile['eventName'] != event['event_name']:
                        profile.clear()
                        profile.update(season=season, round=event['round'], eventName=event['event_name'], name=event['location'], ratings=[], compounds=[], sources=[])
                    if compounds and published >= profile.get('published', ''):
                        profile.update(compounds=compounds, published=published, compoundSource=url)
                    if exact:
                        previews = tree.xpath('//a[contains(translate(@data-filename,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"preview")]/@data-sourcepath')
                        previews = [u for u in dict.fromkeys(previews) if re.search(r'preview[-_]en\.(?:jpg|png)', u, re.I) and 'visual' not in u.lower()]
                        signature = str(meta.get('dateModified', published))
                        if previews and published >= profile.get('ratingPublished', ''):
                            image_body = await fetch(client, previews[0], 8_000_000)
                            signature = f'{VERSION}:{signature}:{hashlib.sha256(image_body).hexdigest()}'
                            if articles.get(url) == signature:
                                continue
                            try:
                                values = await asyncio.to_thread(parse_infographic, image_body, season, [event['location'], event['event_name'].replace(' Grand Prix', '')])
                                for optional in ('pressures', 'pitLoss'):
                                    if optional not in values:
                                        profile.pop(optional, None)
                                profile.update(values, ratingSource=url, ratingPublished=published)
                                articles[url] = signature
                            except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
                                errors.append(f'{url}: {exc}')
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'{url}: {exc}')
        # Every round is warmed automatically. Completed-round history is stable;
        # future rounds are refreshed daily in case this circuit hosts two races.
        priority = sorted(schedule, key=lambda e: (abs((datetime.fromisoformat(e['date']).date() - now.date()).days), -e['round']))
        for event in priority:
            if data.get('recordsRetryAt') and datetime.fromisoformat(data['recordsRetryAt']) > now:
                errors.append('Circuit history is waiting for source Retry-After')
                break
            key = f"{season}:{event['round']}"
            existing = data['stages'].get(key, {})
            updated = existing.get('recordsUpdated')
            ttl = 7 * 86400 if event.get('date', '') < now.date().isoformat() else 86400
            if updated and existing.get('eventName') == event['event_name'] and (now - datetime.fromisoformat(updated)).total_seconds() < ttl:
                continue
            try:
                records = await circuit_records(client, season, event['round'])
                if records:
                    profile = data['stages'].setdefault(key, {'season': season, 'round': event['round'], 'eventName': event['event_name'], 'ratings': [], 'compounds': [], 'sources': []})
                    if profile.get('eventName') != event['event_name']:
                        profile.clear()
                        profile.update(season=season, round=event['round'], eventName=event['event_name'], ratings=[], compounds=[])
                    profile.update(records, recordsUpdated=now.isoformat())
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'history {key}: {exc}')
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    retry = exc.response.headers.get('Retry-After', '3600')
                    seconds = min(86400, max(60, int(retry))) if retry.isdigit() and len(retry) < 7 else 3600
                    data['recordsRetryAt'] = (now + timedelta(seconds=seconds)).isoformat()
                    break
    data.update(checked=now.isoformat(), errors=errors[-20:])
    write_snapshot(data)
    if errors:
        # The worker's operations view must report a partial failure, rather than
        # marking an OCR/transport failure as a successful automatic update.
        raise RuntimeError(f'Pirelli refresh partially failed: {"; ".join(errors[:3])}')


async def get_profile(season: int, round_num: int) -> dict:
    from app.f1_data import get_season_schedule_short_async
    schedule = await get_season_schedule_short_async(season)
    if not schedule:
        raise RuntimeError('Circuit calendar is temporarily unavailable')
    event = next((e for e in schedule if e['round'] == round_num), None)
    data = read_snapshot()
    profile = data['stages'].get(f'{season}:{round_num}')
    if not event or not profile or profile.get('eventName') != event['event_name']:
        return {'status': 'unavailable', 'season': season, 'round': round_num, 'profile': None}
    profile = dict(profile)
    profile['sources'] = [{'title': title, 'href': profile[key]} for key, title in [('compoundSource', 'Pirelli · выбор составов'), ('ratingSource', 'Pirelli · профиль трассы'), ('historySource', 'Jolpica · история гонок на этой трассе')] if profile.get(key)]
    checked = data.get('checked')
    try:
        stale = bool(data.get('errors')) or not checked or (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds() > INTERVAL * 2
    except (ValueError, TypeError):
        stale = True
    profile['stale'] = stale
    profile['updatedAt'] = checked
    return {'status': 'stale' if stale else 'ok', 'season': season, 'round': round_num, 'profile': profile}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, default=datetime.now(timezone.utc).year)
    args = parser.parse_args()
    if not 1950 <= args.season <= datetime.now(timezone.utc).year + 1:
        parser.error('season must be between 1950 and next year')
    asyncio.run(refresh_profiles(args.season))


if __name__ == '__main__':
    main()
