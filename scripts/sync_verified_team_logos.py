"""Import published official team logos at card resolution and optionally pack them.

Only touches app/assets/2026/team-logos; all other archive entries are preserved.
Run explicitly after reviewing the source pages, never from a bot request.
"""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "app/assets/2026/team-logos/"
TEAMS = {
    "alpine": "ALPINE", "aston-martin": "ASTON MARTIN", "audi": "AUDI",
    "cadillac": "CADILLAC", "ferrari": "FERRARI", "haas": "HAAS F1 TEAM",
    "mclaren": "MCLAREN", "mercedes": "MERCEDES", "racing-bulls": "RACING BULLS",
    "red-bull-racing": "RED BULL RACING", "williams": "WILLIAMS",
}


def download_logos():
    folder = ROOT / PREFIX
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with requests.Session() as client:
        index = client.get("https://www.formula1.com/en/teams", timeout=25)
        index.raise_for_status()
        for slug, identity in TEAMS.items():
            path = f"/en/teams/{slug}"
            if path not in index.text:
                raise ValueError(f"Team page no longer published: {slug}")
            page_url = "https://www.formula1.com" + path
            response = client.get(page_url, timeout=25)
            response.raise_for_status()
            urls = {html.unescape(u) for u in re.findall(r'https[^\s"<>\\]+', response.text)}
            candidates = sorted(u for u in urls if len(u) < 350 and u.startswith(
                "https://media.formula1.com/image/upload/c_fit,h_64/")
                and "/common/f1/" in u and re.search(r"logo(?:white|light)\.webp$", u))
            if len(candidates) != 1:
                raise ValueError(f"Review changed logo sources for {identity}: {candidates}")
            published = candidates[0]
            # Same published asset, rasterized larger from the source artwork.
            image_url = published.replace("/c_fit,h_64/", "/c_fit,h_512,w_768/").replace("/q_auto/", "/q_100/")[:-5] + ".png"
            result = client.get(image_url, timeout=25)
            result.raise_for_status()
            with Image.open(io.BytesIO(result.content)) as source:
                image = source.convert("RGBA")
                if max(image.size) < 256 or image.getchannel("A").getextrema()[0] == 255:
                    raise ValueError(f"Invalid resolution or opaque logo: {identity}")
                target = folder / f"{identity}.png"
                image.save(target, format="PNG", optimize=True)
            manifest[identity] = {"page": page_url, "published_image": published,
                                  "image": image_url, "size": list(image.size),
                                  "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            print(f"{identity}: {image.width} x {image.height}")
    (folder / "sources.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder


def pack_logos(folder):
    archive_path = ROOT / "app-assets.zip"
    backup = ROOT / ".tmp/bot-standings-qa/app-assets.before-logos.zip"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(archive_path, backup)
    files = sorted(folder.iterdir())
    if len(files) != len(TEAMS) + 1:
        raise ValueError("Expected eleven logos and their source manifest")
    with tempfile.NamedTemporaryFile(dir=ROOT, suffix=".zip", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        hashes = {}
        with zipfile.ZipFile(archive_path) as original, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as output:
            for item in original.infolist():
                if not item.filename.replace("\\", "/").startswith(PREFIX):
                    data = original.read(item)
                    hashes[item.filename] = hashlib.sha256(data).hexdigest()
                    output.writestr(item, data)
            for file in files:
                output.write(file, PREFIX + file.name)
        with zipfile.ZipFile(temporary) as output:
            if output.testzip() is not None:
                raise ValueError("Damaged asset archive")
            for name, digest in hashes.items():
                if hashlib.sha256(output.read(name)).hexdigest() != digest:
                    raise ValueError(f"Existing asset changed: {name}")
            for file in files:
                if output.read(PREFIX + file.name) != file.read_bytes():
                    raise ValueError(f"Logo failed archive validation: {file.name}")
        temporary.replace(archive_path)
        print(f"Packed eleven logos; preserved {len(hashes)} other entries. Backup: {backup}")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", action="store_true", help="Also update app-assets.zip after validation")
    args = parser.parse_args()
    folder = download_logos()
    if args.pack:
        pack_logos(folder)
