"""Render an audited FIA source for visual tracing (requires pdfplumber)."""
import argparse
import io
import json
from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]

def render(row):
    event = row['event']
    try:
        if not row['maps']:
            raise ValueError(f'No audited reference for {event}')
        source = row['maps'][0]['url']
        cache = ROOT / 'artifacts' / f'{event}-source.pdf'
        if not cache.exists():
            with urlopen(source, timeout=30) as response:
                payload = response.read()
            # Validate before caching an error response as a PDF.
            with pdfplumber.open(io.BytesIO(payload)):
                cache.write_bytes(payload)
        pdf = pdfplumber.open(cache)
        with pdf:
            # Skip the document cover; Canada V2 has a map on its second page too.
            page = pdf.pages[1]
            target = ROOT / 'artifacts' / f'{event}-source.png'
            page.to_image(resolution=120).save(target)
            print(event, source, target, sep='\n')
            print(page.extract_text())
    except Exception as error:
        print(f'{event}: {error}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', nargs='+', help='Exact event names from the audit')
    args = parser.parse_args()
    rows = json.loads((ROOT / 'artifacts/circuit-source-audit.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(render, [next(row for row in rows if row['event'] == event) for event in args.events]))
