"""Audit official season-specific map availability; never infer operational zones."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin
import json
import requests

ROOT = Path(__file__).resolve().parents[1]
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.href=None; self.label=[]
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.href=dict(attrs).get('href'); self.label=[]
    def handle_data(self, data):
        if self.href: self.label.append(data)
    def handle_endtag(self, tag):
        if tag=='a' and self.href:
            self.links.append((self.href,' '.join(self.label))); self.href=None

def audit(event):
    url='https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072/event/'+quote(event)
    try:
        response=requests.get(url,timeout=20); response.raise_for_status()
        parser=Links(); parser.feed(response.text)
        maps=[{'url':urljoin(url,href),'title':label.strip()} for href,label in parser.links
              if '.pdf' in href.lower() and '2026' in href and ('circuit_map' in href.lower() or 'circuit map' in label.lower())]
        return {'event':event,'index':url,'maps':maps,'status':'found' if maps else 'not-found'}
    except Exception as exc:
        return {'event':event,'index':url,'maps':[],'status':'error','error':str(exc)}

if __name__=='__main__':
    events=sorted(p.stem for p in (ROOT/'front/public/static/circuit').glob('*.svg'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=[]
        for row in pool.map(audit,events):
            rows.append(row); print(row['event'],row['status'],len(row['maps']),flush=True)
    target=ROOT/'artifacts/circuit-source-audit.json'
    target.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
