"""Patch only prediction deadline copy in the preserved UI; retain its layout.

The original archive is untouched. Rename the compiled JS namespace together so
browsers never reuse stale copies or mix old/new module graphs after release.
"""
from pathlib import Path
import hashlib
import re
import sys


def install(root):
    root = Path(root)
    pages = list((root/'static').glob('PredictionsPage-*.js'))
    if len(pages) != 1:
        raise RuntimeError('Expected exactly one preserved prediction page')
    page = pages[0]
    text = page.read_text()
    match = re.search(r'После старта \$\{([\w$]+)\.has_sprint', text)
    if match is None:
        raise RuntimeError('Preserved prediction deadline copy changed; inspect it before release')
    current = match[1]
    old = '"Прогноз сохранён. Его можно изменить до начала квалификации."'
    new = f'{current}?.race_day_exception?"Прогноз сохранён. Его можно изменить до старта гонки.":"Прогноз сохранён. Его можно изменить до закрытия приёма."'
    assert old in text
    text = text.replace(old, new, 1)
    old = '"Прогноз закрывается перед первой квалификацией. Чем точнее позиция — тем больше баллов."'
    assert old in text
    text = text.replace(old, f'{current}?.race_day_exception?"Сегодня прогнозы доступны до старта гонки. Чем точнее позиция — тем больше баллов.":{old}', 1)
    old = f'`После старта ${{{current}.has_sprint?"спринт-квалификации":"квалификации"}} сервер заблокирует любые изменения.`'
    assert old in text
    text = text.replace(old, f'{current}.race_day_exception?"После старта гонки сервер заблокирует любые изменения.":{old}', 1)
    page.write_text(text)
    tag = hashlib.sha256(text.encode()).hexdigest()[:10]
    assets = list((root/'static').glob('*.js'))
    names = {p.name:p.stem+'.deadline-'+tag+'.js' for p in assets}
    for p in assets:
        p.rename(p.with_name(names[p.name]))
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in {'.js','.html','.json'}:
            value = p.read_text()
            for old,new in names.items(): value = value.replace(old,new)
            p.write_text(value)
    index = root/'index.html'
    html = index.read_text().replace('</head>', '<link rel="stylesheet" href="/prediction-race-day.css">\n<script defer src="/prediction-race-day.js"></script>\n</head>')
    index.write_text(html)


if __name__ == '__main__':
    install(sys.argv[1])
