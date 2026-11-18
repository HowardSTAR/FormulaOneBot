"""Seasonal portrait transformations with bounded, file-versioned reuse."""
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image
from app.utils.default import DRIVER_CODE_TO_FILE


def _file_version(path: Path):
    path = path.resolve()
    source = path.stat()
    return path, source.st_mtime_ns, source.st_size, source.st_ctime_ns


def render_head_crop_png_bytes(path: Path, crop_ratio: float = .35) -> bytes:
    version = _file_version(path)
    path = version[0]
    manifest = path.parent / "sources.json"
    try:
        metadata = manifest.stat()
        provenance = (metadata.st_mtime_ns, metadata.st_size, metadata.st_ctime_ns)
    except FileNotFoundError:
        provenance = None
    return _render_version(*version, provenance, crop_ratio)


def render_compact_portrait_webp(path: Path) -> bytes:
    return _render_compact_version(*_file_version(path))


@lru_cache(maxsize=128)
def _render_compact_version(path, mtime_ns, size, ctime_ns):
    with Image.open(path) as image:
        portrait = image.convert("RGBA")
        portrait.thumbnail((224, 320), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        portrait.save(output, format="WEBP", quality=78)
        return output.getvalue()


@lru_cache(maxsize=64)
def _render_version(path, mtime_ns, size, ctime_ns, provenance, crop_ratio):
    # Cache immutable bytes, never mutable PIL images. File/provenance changes
    # invalidate the key; exceptions and missing files are not cached.
    with Image.open(path) as img:
        base = img.convert("RGBA")
        w, h = base.size
        alpha_extrema = base.getchannel("A").getextrema()
        transparent_square = h <= int(w * 1.25) and alpha_extrema[0] < 255
        if path.stem in DRIVER_CODE_TO_FILE and provenance is not None:
            if path.stem == "TSU":
                head = base.crop((int(w * .25), 0, int(w * .25) + int(w * .533333), int(w * .533333)))
            else:
                side = min(w, h)
                head = base.crop((0, 0, side, side))
            head.thumbnail((256, 256), Image.Resampling.LANCZOS)
        elif transparent_square:
            head = base
        else:
            head = base.crop((0, 0, w, max(1, int(h * crop_ratio))))
        output = io.BytesIO()
        head.save(output, format="PNG")
        return output.getvalue()
