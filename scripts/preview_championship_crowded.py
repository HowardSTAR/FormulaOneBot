"""Gold Aura previews with 4, 5 and 8 total participants per competition."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from app.utils.championship_card import build_card_models, render_championship_card
from app.utils.classification_card import _font
from scripts.championship_preview_data import preview_context


def main():
    target = Path('artifacts/championship-cards/multi')
    target.mkdir(parents=True, exist_ok=True)
    sections = []
    for count in [4, 5, 8]:
        participants = f'{count} участника' if count == 4 else f'{count} участников'
        rivals = f'{count-1} соперников' if count == 8 else f'{count-1} соперника'
        context = preview_context(participants=count)
        (target / f'context-{count}.json').write_text(json.dumps(context, ensure_ascii=False), encoding='utf-8')
        models = build_card_models(context)
        for model in models:
            assert len(model.rivals)+1 == count
            filename = f'aura-{model.kind}-{count}.png'
            (target / filename).write_bytes(render_championship_card(model))
            print(filename)
        with Image.open(target / f'aura-drivers-{count}.png') as driver, Image.open(target / f'aura-constructors-{count}.png') as team:
            # A paired contact sheet; individual posters remain full resolution.
            sheet = Image.new('RGB', (2160, driver.height+100), '#080b10')
            draw = ImageDraw.Draw(sheet)
            draw.text((48, 24), f'GOLD AURA / {participants.upper()} / ПИЛОТЫ', font=_font(30, True), fill='#eed088')
            draw.text((1128, 24), f'GOLD AURA / {participants.upper()} / КОМАНДЫ', font=_font(30, True), fill='#eed088')
            sheet.paste(driver, (0, 100))
            sheet.paste(team, (1080, 100))
            sheet.save(target / f'comparison-{count}.png')
        sections.append(f'''<section id="count-{count}"><h2>{participants}: лидер и {rivals}</h2><div class="grid">
            <figure><a href="aura-drivers-{count}.png"><img src="aura-drivers-{count}.png" alt="{count} пилотов"></a><figcaption>Пилоты</figcaption></figure>
            <figure><a href="aura-constructors-{count}.png"><img src="aura-constructors-{count}.png" alt="{count} команд"></a><figcaption>Команды</figcaption></figure></div></section>''')
    (target / 'index.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Gold Aura · 4, 5 и 8 участников</title><style>
        body{margin:0;background:#080b10;color:#f4f4ee;font:17px/1.6 system-ui;padding:30px}main{max-width:1600px;margin:auto}
        h1,h2,a{color:#eed088}p,figcaption{color:#aab1bc}nav{display:flex;gap:24px;position:sticky;top:0;background:#080b10;padding:15px 0}
        .grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}figure{margin:0}img{width:100%;border-radius:20px}figcaption{padding:12px 0}section{scroll-margin-top:80px;margin-bottom:60px}
        @media(max-width:750px){body{padding:16px}.grid{grid-template-columns:1fr}}
        </style><main><h1>Gold Aura · больше трёх участников</h1>
        <p>Демонстрационные очки. В число участников входит главный претендент. Ниже показаны все соперники, которые могут отложить его титул; они не обязательно могут сами стать чемпионами на этом этапе.</p>
        <p>Главный претендент — сверху. У каждого соперника — фото или логотип, текущие очки, зелёное и красное условие для результата лидера. Все зелёные условия нужны вместе, одного красного достаточно.</p>
        <nav><a href="#count-4">4 участника</a><a href="#count-5">5 участников</a><a href="#count-8">8 участников</a></nav>''' + ''.join(sections) + '</main></html>', encoding='utf-8')
    print(target.resolve())


if __name__ == '__main__':
    main()
