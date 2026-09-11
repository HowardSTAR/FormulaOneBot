"""Render a QA contact sheet using the actual API crop, not generated faces."""
import io
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.api.miniapp_api import _find_local_pilot_portrait_path, _render_head_crop_png_bytes
codes = sorted(json.loads((root / 'app/assets/2026/pilots/sources.json').read_text()))
sheet = Image.new('RGB', (800, 5 * 185), '#22252d')
draw = ImageDraw.Draw(sheet)
for i, code in enumerate(codes):
    photo = Image.open(io.BytesIO(_render_head_crop_png_bytes(_find_local_pilot_portrait_path(2026, code, None))))
    photo.thumbnail((150, 150))
    x, y = (i % 5) * 160, (i // 5) * 185
    sheet.paste(photo, (x, y), photo)
    draw.text((x + 60, y + 155), code, fill='white')
sheet.save(root / 'artifacts/verified-driver-portraits.png')
