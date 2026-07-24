from pathlib import Path

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
    "2026": {
        "Alexander Albon",
        "Andrea Kimi Antonelli",
        "Arvid Lindblad",
        "Carlos Sainz",
        "Charles Leclerc",
        "Esteban Ocon",
        "Fernando Alonso",
        "Franco Colapinto",
        "Gabriel Bortoleto",
        "George Russell",
        "Isack Hadjar",
        "Lance Stroll",
        "Lando Norris",
        "Lewis Hamilton",
        "Liam Lawson",
        "Max Verstappen",
        "Nico Hulkenberg",
        "Oliver Bearman",
        "Oscar Piastri",
        "Pierre Gasly",
        "Sergio Perez",
        "Valtteri Bottas",
    },
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
        assert _asset_stems(ASSETS_ROOT / season / "teams") == expected


def test_all_season_assets_have_real_transparency_and_clean_names():
    for season_dir in ASSETS_ROOT.iterdir():
        if not season_dir.is_dir():
            continue
        for category in ("pilots", "teams", "cars"):
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
                _assert_transparent(path)
