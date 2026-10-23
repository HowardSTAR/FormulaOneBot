"""Pack project images and runtime assets, or restore them before local development."""
import argparse
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
IMAGE_DIRECTORIES = (
    "app/profile_avatar_assets", "art/password-racer", "front/public",
    "front/src/assets", "race-game/public",
)


def asset_path(name: str) -> bool:
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or any(
        part.startswith(".") or ":" in part or part == "__MACOSX" for part in path.parts
    ):
        return False
    return name.startswith("app/assets/") or (
        path.suffix.lower() in IMAGE_EXTENSIONS
        and any(name.startswith(directory + "/") for directory in IMAGE_DIRECTORIES)
        and not name.startswith("front/public/race-game/")
    )


def extract_assets(project: Path, destination: Path) -> None:
    destination = destination.resolve()
    with ZipFile(project / "app-assets.zip") as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or not all(asset_path(name) for name in names):
            raise ValueError("Asset archive contains duplicate or unexpected paths")
        if archive.testzip() is not None:
            raise ValueError("Asset archive failed CRC validation")
        for entry in entries:
            target = destination / entry.filename
            if not target.resolve().is_relative_to(destination):
                raise ValueError(f"Asset path escapes destination: {entry.filename}")
        archive.extractall(destination, members=entries)
    print(f"Extracted {len(entries)} assets to {destination}")


def pack_assets(project: Path) -> Path:
    assets = project / "app" / "assets"
    if not assets.is_dir():
        raise FileNotFoundError("Extract app-assets.zip before packing assets")
    files = {path for path in assets.rglob("*") if path.is_file()
             and asset_path(path.relative_to(project).as_posix())}
    for directory in IMAGE_DIRECTORIES:
        files.update(path for path in (project / directory).rglob("*") if path.is_file()
                     and asset_path(path.relative_to(project).as_posix()))
    files = sorted(files)
    if not files:
        raise ValueError("Refusing to create an empty asset archive")
    archive = project / "app-assets.zip"
    # A partial extraction must never silently discard archived images.
    if archive.exists():
        with ZipFile(archive) as original:
            missing = {name for name in original.namelist() if not name.endswith("/")} - {
                path.relative_to(project).as_posix() for path in files
            }
        if missing:
            raise FileNotFoundError("Extract all assets before packing: " + ", ".join(sorted(missing)))
    temporary = project / ".app-assets.tmp.zip"
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
            for path in files:
                entry = ZipInfo(path.relative_to(project).as_posix(), (1980, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                output.writestr(entry, path.read_bytes(), compresslevel=9)
        with ZipFile(temporary) as output:
            if output.testzip() is not None:
                raise ValueError("Asset archive failed CRC validation")
            for path in files:
                name = path.relative_to(project).as_posix()
                if output.read(name) != path.read_bytes():
                    raise ValueError(f"Asset archive does not match source: {name}")
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Packed and verified {len(files)} files: {archive} ({archive.stat().st_size:,} bytes)")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--destination", type=Path, help="Extraction directory (defaults to project root)")
    arguments = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    if arguments.extract:
        extract_assets(project, arguments.destination or project)
    elif arguments.destination:
        parser.error("--destination requires --extract")
    else:
        pack_assets(project)
