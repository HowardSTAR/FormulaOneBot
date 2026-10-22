"""Two deterministic poster directions, using synthetic championship data.

No provider, database, Telegram delivery or server installation is required.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from app.utils.championship_card import HEIGHT, build_card_models, render_championship_card
from app.utils.classification_card import _font
from scripts.championship_preview_data import preview_context


def main():
    target = Path('artifacts/championship-cards')
    target.mkdir(parents=True, exist_ok=True)
    context = preview_context()
    (target / 'demo-context.json').write_text(json.dumps(context, ensure_ascii=False), encoding='utf-8')
    models = build_card_models(context)
    files = []
    for style in ['aura', 'podium']:
        for model in models:
            filename = f'{style}-{model.kind}.png'
            data = render_championship_card(model, style=style)
            (target / filename).write_bytes(data)
            files.append(filename)
            print(f'{filename}: {len(data)} bytes')
    # A second data snapshot proves that all numbers are rendered dynamically.
    updated = preview_context(next_round=True)
    (target / 'updated-context.json').write_text(json.dumps(updated, ensure_ascii=False), encoding='utf-8')
    for model in build_card_models(updated):
        (target / f'updated-{model.kind}.png').write_bytes(render_championship_card(model))
    thumb_height = HEIGHT // 2
    row_height = thumb_height + 70
    sheet = Image.new('RGB', (1080, row_height * 2), '#090c10')
    draw = ImageDraw.Draw(sheet)
    for i, filename in enumerate(files):
        x, y = (i % 2)*540, (i // 2)*row_height
        draw.text((x+24, y+12), ('A · GOLD AURA' if i < 2 else 'B · GOLD PODIUM') + ('  /  DRIVERS' if 'drivers' in filename else '  /  TEAMS'), font=_font(20, True), fill='#e9cd85')
        with Image.open(target / filename) as source:
            sheet.paste(source.resize((540, thumb_height), Image.Resampling.LANCZOS), (x, y+50))
    sheet.save(target / 'overview.png')
    album = Image.new('RGB', (1080, 1130), '#17212b')
    ad = ImageDraw.Draw(album)
    ad.text((34, 20), 'ПРИМЕР УВЕДОМЛЕНИЯ · ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ', font=_font(22, True), fill='#aab9c8')
    ad.rounded_rectangle((24, 80, 1056, 1092), radius=24, fill='#243442')
    for index, kind in enumerate(['drivers', 'constructors']):
        with Image.open(target / f'aura-{kind}.png') as card:
            album.paste(card.resize((500, round(HEIGHT*500/1080)), Image.Resampling.LANCZOS), (34+index*512, 90))
    ad.text((52, 800), 'Скоро гонка · через 1 час', font=_font(38, True), fill='#f1f4f7')
    ad.text((52, 870), 'Титул может решиться на этом этапе.', font=_font(29), fill='#d1dae1')
    ad.text((52, 920), 'Зелёным — условия титула. Красным — что его отложит.', font=_font(26), fill='#d1dae1')
    ad.rounded_rectangle((48, 1000, 1032, 1067), radius=14, fill='#304b60')
    ad.text((540, 1015), 'Все условия титула', font=_font(29, True), fill='#9ed5ff', anchor='mt')
    album.save(target / 'notification-album.png')
    items = ''.join(f'<figure><a href="{filename}"><img src="{filename}"></a><figcaption>{filename}</figcaption></figure>' for filename in files)
    (target / 'index.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Чемпионство · варианты оформления</title><style>body{margin:0;background:#080b10;color:#eee;font:16px/1.6 system-ui;padding:32px}header{max-width:1000px;margin:auto}h1{color:#edcd83;font-size:30px}p{color:#aeb6c1}.grid{max-width:1200px;margin:auto;display:grid;grid-template-columns:1fr 1fr;gap:22px}figure{margin:0}img{width:100%;border-radius:16px}figcaption{color:#aeb6c1;padding:8px}a{color:#edcd83}@media(max-width:700px){.grid{grid-template-columns:1fr}body{padding:16px}}</style><header><h1>CHAMPION? · два направления</h1><p>Демонстрационные данные. Это варианты дизайна, а не текущая таблица чемпионата.</p><p>Зелёные ограничения выполняются одновременно. Красный результат любого соперника откладывает титул при указанном результате лидера. Золотое равенство, если оно есть, требует сравнения дополнительных показателей. На карточке показан один сценарий; полный перечень остаётся в тексте поста.</p></header><div class="grid">''' + items + '</div></html>', encoding='utf-8')
    print(target.resolve())


if __name__ == '__main__':
    main()
