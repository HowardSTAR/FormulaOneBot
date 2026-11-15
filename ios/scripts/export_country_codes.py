"""Export country URL aliases shared with the web client; no image copies."""
import json
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[2]

def export_countries():
    source = (ROOT / 'front/src/helpers/raceCountry.ts').read_text()
    country_block = source.split('const countries:')[1].split('const normalize')[0]
    aliases = {}
    for code, body in re.findall(r'(\w+): \[(.*?)\]', country_block):
        for name in [code] + re.findall("'([^']+)'", body):
            aliases[re.sub(r'\s+', ' ', name.strip().lower().replace('.', ''))] = code
    event_block = source.split('const events:')[1].split('export function')[0]
    events = {quoted or bare: code for quoted, bare, code in
              re.findall(r"(?:'([^']+)'|(\w+)):\s*'([^']+)'", event_block)}
    target = ROOT / 'ios/TurboTears/Resources/race-countries.json'
    target.write_text(json.dumps(dict(aliases=aliases, events=events), ensure_ascii=False))


if __name__ == "__main__":
    export_countries()
