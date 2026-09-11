"""Download identity-keyed portraits from the driver's official page, never search by team.

Writes the extracted asset directory; repack app-assets.zip after visual review.
"""
import concurrent.futures
import hashlib
import html
import io
import json
from pathlib import Path
import re
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DRIVERS = {
    'ALB': ('alexander-albon', 'alealb01'), 'ANT': ('kimi-antonelli', 'andant01'),
    'SAI': ('carlos-sainz', 'carsai01'), 'LEC': ('charles-leclerc', 'chalec01'),
    'OCO': ('esteban-ocon', 'estoco01'), 'ALO': ('fernando-alonso', 'feralo01'),
    'COL': ('franco-colapinto', 'fracol01'), 'BOR': ('gabriel-bortoleto', 'gabbor01'),
    'RUS': ('george-russell', 'georus01'), 'HAD': ('isack-hadjar', 'isahad01'),
    'STR': ('lance-stroll', 'lanstr01'), 'NOR': ('lando-norris', 'lannor01'),
    'HAM': ('lewis-hamilton', 'lewham01'), 'LAW': ('liam-lawson', 'lialaw01'),
    'VER': ('max-verstappen', 'maxver01'), 'HUL': ('nico-hulkenberg', 'nichul01'),
    'BEA': ('oliver-bearman', 'olibea01'), 'PIA': ('oscar-piastri', 'oscpia01'),
    'GAS': ('pierre-gasly', 'piegas01'), 'TSU': ('yuki-tsunoda', 'yuktsu01'),
    'BOT': ('valtteri-bottas', 'valbot01'), 'PER': ('sergio-perez', 'serper01'),
    'LIN': ('arvid-lindblad', 'arvlin01'),
}

def fetch(item):
    code, (slug, identity) = item
    if code == 'TSU':
        page_url = 'https://www.yukitsunoda.com/profile/'
        url = 'https://www.yukitsunoda.com/sys/wp-content/uploads/2026/05/2026-600x900.jpg'
        page = requests.get(page_url, timeout=30)
        page.raise_for_status()
        if url not in page.text:
            raise ValueError('Official Tsunoda portrait changed; review before downloading')
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            image.verify()
        target = ROOT / 'app/assets/2026/pilots/TSU.jpg'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return code, {'page': page_url, 'image': url, 'sha256': hashlib.sha256(response.content).hexdigest()}
    page_url = f'https://www.formula1.com/en/drivers/{slug}'
    page = requests.get(page_url, timeout=30)
    page.raise_for_status()
    urls = {html.unescape(url) for url in re.findall(r'https[^\s"<>\\]+', page.text)}
    candidates = sorted(url for url in urls if '/c_fill,w_720/' in url
                        and f'/{identity}/' in url and url.endswith('right.webp'))
    if not candidates:
        raise ValueError(f'{code}: no identity-matching portrait on official page')
    url = candidates[-1]
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        image.verify()
    target = ROOT / 'app/assets/2026/pilots' / f'{code}.webp'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return code, {'page': page_url, 'image': url, 'sha256': hashlib.sha256(response.content).hexdigest()}

if __name__ == '__main__':
    manifest = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, item) for item in DRIVERS.items()]
        for future in concurrent.futures.as_completed(futures):
            try:
                code, record = future.result()
                manifest[code] = record
                print(code, record['image'])
            except Exception as exc:
                print('MISSING', exc)
    (ROOT / 'app/assets/2026/pilots/sources.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
