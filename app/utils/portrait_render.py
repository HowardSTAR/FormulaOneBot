"""Pure portrait transformation with bounded, file-versioned PNG reuse."""
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image
from app.utils.default import DRIVER_CODE_TO_FILE


def render_head_crop_png_bytes(path: Path, crop_ratio: float = .35) -> bytes:
    path = path.resolve()
    source = path.stat()
    manifest = path.parent / "sources.json"
    try:
        metadata = manifest.stat()
        provenance = (metadata.st_mtime_ns, metadata.st_size, metadata.st_ctime_ns)
    except FileNotFoundError:
        provenance = None
    return _render_version(path, source.st_mtime_ns, source.st_size, source.st_ctime_ns, provenance, crop_ratio)


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
