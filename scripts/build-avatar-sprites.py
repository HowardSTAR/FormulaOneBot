"""Build lossless editor atlases from the production renderer; no AI regeneration.

Run from the repository root after changing the versioned avatar artwork.
Each atlas has horizontal cells in the same order as profile_avatar.OPTIONS.
"""
import sys
from itertools import product
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.profile_avatar import OPTIONS, _background, _layer


def build(destination):
    destination.mkdir(parents=True, exist_ok=True)
    atlases = {}
    for part, variants in OPTIONS.items():
        # CSS backgrounds must be opaque; retain the renderer's RGB palette rather
        # than blending procedural decorations with the dialog behind the image.
        cells = [(_background(name).convert('RGB') if part == 'background' else _layer(name, part == 'helmet'))
                 for name in variants]
        width, height = cells[0].size
        atlas = Image.new('RGBA', (width * len(cells), height))
        for index, cell in enumerate(cells):
            atlas.paste(cell, (index * width, 0))
        path = destination / f'{part}-v1.webp'
        atlas.save(path, 'WEBP', lossless=True, exact=True, method=6)
        # Read the actual encoded bytes for the pixel-equivalence check below.
        with Image.open(path) as saved:
            atlases[part] = saved.convert('RGBA')
        print(f'{path.relative_to(ROOT)}: {path.stat().st_size:,} bytes')

    for helmet, suit, background in product(*OPTIONS.values()):
        layers = {}
        for part, name in dict(helmet=helmet, suit=suit, background=background).items():
            index = list(OPTIONS[part]).index(name)
            atlas = atlases[part]
            layers[part] = atlas.crop((index * 384, 0, (index + 1) * 384, atlas.height))
        image = layers['background']
        image.alpha_composite(layers['suit'], (0, 238))
        image.alpha_composite(layers['helmet'])
        expected = _background(background).convert('RGB').convert('RGBA')
        expected.alpha_composite(_layer(suit, False), (0, 238))
        expected.alpha_composite(_layer(helmet, True))
        assert image.tobytes() == expected.tobytes(), (helmet, suit, background)
    print('All 45 sprite compositions verified against the source layers and opaque backgrounds.')


if __name__ == '__main__':
    build(ROOT / 'front/src/assets/avatar')
