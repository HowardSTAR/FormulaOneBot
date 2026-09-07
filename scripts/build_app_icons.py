"""Generate install icons from the same geometric mark as front/public/app-icon.svg."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "front" / "public"
image = Image.new("RGB", (512,512), "#101116")
draw = ImageDraw.Draw(image)
draw.polygon([(92,145),(436,145),(414,213),(295,213),(241,375),(163,375),(217,213),(70,213)], fill="#e10600")
draw.polygon([(317,244),(413,244),(393,304),(297,304)], fill="white")
draw.polygon([(294,320),(367,320),(349,375),(276,375)], fill="white")
for size in (180,192,512):
    image.resize((size,size), Image.Resampling.LANCZOS).save(root / f"app-icon-{size}.png")
