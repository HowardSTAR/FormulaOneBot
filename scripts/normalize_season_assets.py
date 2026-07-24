from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


SUPPORTED_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}


def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return (
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    )


def remove_connected_background(
    source: Image.Image,
    *,
    edge_threshold: int = 10,
) -> Image.Image:
    """Remove a studio/card background without repainting the photographed person.

    The algorithm only flood-fills pixels connected to the top and upper side
    edges. A colour edge stops the fill, so the face, hair, suit and sponsor
    details remain byte-for-byte unchanged in RGB.
    """

    image = source.convert("RGBA")
    width, height = image.size
    rgb = image.convert("RGB")
    pixels = rgb.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    threshold_sq = edge_threshold * edge_threshold

    def add_seed(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index]:
            visited[index] = 1
            queue.append((x, y))

    for x in range(width):
        add_seed(x, 0)
    side_limit = max(1, int(height * 0.78))
    for y in range(side_limit):
        add_seed(0, y)
        add_seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        current = pixels[x, y]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            index = ny * width + nx
            if visited[index]:
                continue
            if _rgb_distance(current, pixels[nx, ny]) > threshold_sq:
                continue
            visited[index] = 1
            queue.append((nx, ny))

    mask = Image.frombytes(
        "L",
        (width, height),
        bytes(255 if value else 0 for value in visited),
    )
    # Slight expansion and feathering remove the original coloured fringe while
    # keeping facial and uniform detail untouched.
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    alpha = Image.eval(mask, lambda value: 255 - value)
    result = image.copy()
    result.putalpha(alpha)
    return result


def remove_connected_checkerboard(source: Image.Image) -> Image.Image:
    """Remove a baked checkerboard preview while preserving the portrait.

    Some asset libraries expose a JPEG preview where transparency is represented
    by a light grey checkerboard. Only bright, near-neutral pixels connected to
    an outer edge are removed, so white sponsor marks inside the suit remain.
    """

    image = source.convert("RGBA")
    width, height = image.size
    rgb = image.convert("RGB")
    pixels = rgb.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def is_background(pixel: tuple[int, int, int]) -> bool:
        return max(pixel) - min(pixel) <= 8 and min(pixel) >= 178

    def add_seed(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index] and is_background(pixels[x, y]):
            visited[index] = 1
            queue.append((x, y))

    for x in range(width):
        add_seed(x, 0)
        add_seed(x, height - 1)
    for y in range(height):
        add_seed(0, y)
        add_seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx in range(max(0, x - 1), min(width, x + 2)):
            for ny in range(max(0, y - 1), min(height, y + 2)):
                index = ny * width + nx
                if visited[index] or not is_background(pixels[nx, ny]):
                    continue
                visited[index] = 1
                queue.append((nx, ny))

    mask = Image.frombytes(
        "L",
        (width, height),
        bytes(255 if value else 0 for value in visited),
    )
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    alpha = Image.eval(mask, lambda value: 255 - value)
    result = image.copy()
    result.putalpha(alpha)
    return result


def normalize_checkerboard_portrait(source_path: Path, output_path: Path) -> Path:
    with Image.open(source_path) as source:
        transparent = remove_connected_checkerboard(source)
    width, height = transparent.size
    crop_size = min(width, height)
    left = max(0, (width - crop_size) // 2)
    transparent = transparent.crop((left, 0, left + crop_size, crop_size))
    transparent = transparent.resize((450, 450), Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    transparent.save(output_path, format="PNG", optimize=True)
    return output_path


def normalize_pilot_directory(source_dir: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path in sorted(source_dir.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        with Image.open(path) as source:
            normalized = (
                source.convert("RGBA")
                if "A" in source.getbands()
                else remove_connected_background(source)
            )
        destination = output_dir / f"{path.stem}.png"
        normalized.save(destination, format="PNG", optimize=True)
        written.append(destination)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize season pilot portraits to lossless transparent PNG."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--checkerboard-preview",
        action="store_true",
        help="Process one JPEG preview with a baked transparency checkerboard.",
    )
    args = parser.parse_args()

    if args.checkerboard_preview:
        written = normalize_checkerboard_portrait(args.source, args.output)
        print(f"normalized=1 output={written}")
        return

    written = normalize_pilot_directory(args.source, args.output)
    print(f"normalized={len(written)} output={args.output}")


if __name__ == "__main__":
    main()
