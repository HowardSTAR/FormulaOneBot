"""Inspect official driver page image metadata, without guessing CDN URLs."""
import re
import sys
import html
import requests

for slug in sys.argv[1:]:
    page = requests.get(slug if slug.startswith('https://') else f"https://www.formula1.com/en/drivers/{slug}", timeout=30)
    page.raise_for_status()
    urls = sorted(set(html.unescape(url).replace('\\u0026', '&') for url in re.findall(r'https[^\s"<>\\]+', page.text)))
    print(slug)
    for url in urls:
        if 'image' in url and any(x in url.lower() for x in ('driver/', 'drivers/', 'lanstr', 'alealb', 'headshot', 'tsunoda')):
            print(url[:1000])
    if slug.startswith('https://'):
        print(re.findall(r'<img[^>]+>', page.text)[:20])
        print(re.findall(r'[^\s"<>]+\.(?:png|jpg|css)', page.text)[:45])
        print([line[:1200] for line in page.text.splitlines() if any(word in line for word in ('data-', 'background', 'portrait'))][:30])
