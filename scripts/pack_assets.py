"""Pack the extracted runtime assets identically on Windows and Linux."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def pack_assets(project: Path) -> Path:
    assets = project / "app" / "assets"
    if not assets.is_dir():
        raise FileNotFoundError("Extract app-assets.zip before packing assets")
    files = sorted(path for path in assets.rglob("*") if path.is_file()
                   and not any(part.startswith(".") or part == "__MACOSX"
                               for part in path.relative_to(assets).parts))
    if not files:
        raise ValueError("Refusing to create an empty asset archive")
    archive = project / "app-assets.zip"
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
    pack_assets(Path(__file__).resolve().parents[1])
