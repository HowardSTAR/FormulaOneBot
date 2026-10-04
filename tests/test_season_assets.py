from pathlib import Path
import zipfile

from PIL import Image


ASSETS_ROOT = Path(__file__).resolve().parents[1] / "app" / "assets"
IMAGE_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}

EXPECTED_PILOTS = {
    "2025": {
        "Alexander Albon",
        "Andrea Kimi Antonelli",
        "Carlos Sainz",
        "Charles Leclerc",
        "Esteban Ocon",
        "Fernando Alonso",
        "Franco Colapinto",
        "Gabriel Bortoleto",
        "George Russell",
        "Isack Hadjar",
        "Jack Doohan",
        "Lance Stroll",
        "Lando Norris",
        "Lewis Hamilton",
        "Liam Lawson",
        "Max Verstappen",
        "Nico Hulkenberg",
        "Oliver Bearman",
        "Oscar Piastri",
        "Pierre Gasly",
        "Yuki Tsunoda",
    },
    # Verified studio set is identity-keyed, including Tsunoda's reviewed JPEG.
    "2026": {"ALB", "ANT", "LIN", "SAI", "LEC", "OCO", "ALO", "COL", "BOR",
             "RUS", "HAD", "STR", "NOR", "HAM", "LAW", "VER", "HUL", "BEA",
             "PIA", "GAS", "PER", "BOT", "TSU"},
}

EXPECTED_TEAMS = {
    "2025": {
        "Alpine",
        "Aston Martin",
        "Ferrari",
        "Haas F1 Team",
        "Kick Sauber",
        "McLaren",
        "Mercedes",
        "Racing Bulls",
        "Red Bull Racing",
        "Williams",
    },
    "2026": {
        "ALPINE",
        "ASTON MARTIN",
        "AUDI",
        "CADILLAC",
        "FERRARI",
        "HAAS F1 TEAM",
        "MCLAREN",
        "MERCEDES",
        "RACING BULLS",
        "RED BULL RACING",
        "WILLIAMS",
    },
}


def _asset_stems(directory: Path) -> set[str]:
    return {
        path.stem
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }


def _assert_transparent(path: Path) -> None:
    with Image.open(path) as image:
        image.load()
        assert "A" in image.getbands(), f"{path} has no alpha channel"
        alpha = image.getchannel("A")
        assert alpha.getextrema()[0] < 255, f"{path} has an opaque background"


def test_each_supported_season_has_complete_pilot_and_team_assets():
    season_directories = {
        path.name
        for path in ASSETS_ROOT.iterdir()
        if path.is_dir() and path.name.isdigit()
    }
    assert season_directories == set(EXPECTED_PILOTS)
    for season, expected in EXPECTED_PILOTS.items():
        assert _asset_stems(ASSETS_ROOT / season / "pilots") == expected
    for season, expected in EXPECTED_TEAMS.items():
        category = "team-logos" if season == "2026" else "teams"
        assert _asset_stems(ASSETS_ROOT / season / category) == expected


def test_all_season_assets_have_real_transparency_and_clean_names():
    for season_dir in ASSETS_ROOT.iterdir():
        if not season_dir.is_dir():
            continue
        for category in ("pilots", "teams", "team-logos", "cars"):
            category_dir = season_dir / category
            if not category_dir.exists():
                continue
            for path in category_dir.iterdir():
                if (
                    not path.is_file()
                    or path.suffix.lower() not in IMAGE_EXTENSIONS
                ):
                    continue
                assert path.name == path.name.strip()
                if season_dir.name == "2026" and category == "pilots" and path.name == "TSU.jpg":
                    # Not a cutout: provenance/hash are checked in test_verified_portraits.
                    with Image.open(path) as image:
                        assert image.size == (600, 900) and image.mode == "RGB"
                    continue
                _assert_transparent(path)


def test_asset_archive_matches_runtime_files_and_has_no_obsolete_media():
    with zipfile.ZipFile(ASSETS_ROOT.parents[1] / "app-assets.zip") as archive:
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        assert len(names) == len(set(names))
        assert archive.testzip() is None
        extracted = {
            path.relative_to(ASSETS_ROOT.parents[1]).as_posix(): path
            for path in ASSETS_ROOT.rglob("*")
            if path.is_file()
        }
        assert set(names) == set(extracted)
        for name, path in extracted.items():
            assert archive.read(name) == path.read_bytes(), name
        assert not any("/verified-pilots/" in name or "/2026/teams/" in name for name in names)
        for font in ("NotoColorEmoji-Regular.ttf", "Jost-SemiBoldItalic.ttf"):
            assert f"app/assets/fonts/{font}" not in names
