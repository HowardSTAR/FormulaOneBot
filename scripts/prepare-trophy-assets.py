"""Normalize the supplied transparent trophy art for the profile and reveal."""
import argparse
from pathlib import Path

from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
args = parser.parse_args()
output = Path(__file__).resolve().parents[1] / 'front/public/images/trophies'
output.mkdir(parents=True, exist_ok=True)
for family in ['oracle', 'podium', 'rhythm', 'lights', 'ghost', 'atlas', 'grid', 'heart']:
    for tier in ['bronze', 'silver', 'gold']:
        image = Image.open(args.source / f'{family}-{tier}.png').convert('RGBA')
        bounds = image.getchannel('A').point(lambda a: 255 if a >= 12 else 0).getbbox()
        art = image.crop(bounds)
        art.thumbnail((348,348), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA',(384,384))
        canvas.alpha_composite(art,((384-art.width)//2,(384-art.height)//2))
        canvas.save(output / f'{family}-{tier}.webp','WEBP',quality=90,method=6)
print('Prepared 24 transparent trophy images at 384px')
