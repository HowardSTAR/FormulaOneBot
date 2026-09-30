from io import BytesIO
import hashlib
import json
from pathlib import Path
import zipfile

from PIL import Image
import pytest

from app.utils import image_render as renderer
from app.utils.standings_card import render_standings
from scripts.preview_bot_standings import driver_rows, team_rows


def test_every_2026_driver_including_reserve_has_a_local_photo():
    rows = driver_rows()
    assert len(rows) == 23
    for row in rows:
        path = renderer.get_asset_path(2026, "pilots", row["code"])
        assert path and path.is_file(), row["code"]
        assert renderer._local_standings_art(row["code"], row["name"], 2026, "pilots") is not None


def test_all_eleven_team_logos_match_correct_identity():
    for row in team_rows():
        path = renderer.get_asset_path(2026, "teams", row["code"]) or renderer.get_asset_path(2026, "teams", row["name"])
        assert path and path.is_file(), row["name"]
    assert renderer.get_asset_path(2026, "teams", "rb").stem == "RACING BULLS"
    assert renderer.get_asset_path(2026, "teams", "red_bull").stem == "RED BULL RACING"
    assert renderer.get_asset_path(2026, "teams", "bull") is None


def test_high_resolution_logos_are_available_after_archive_extraction(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    prefix = "app/assets/2026/team-logos/"
    with zipfile.ZipFile(root / "app-assets.zip") as archive:
        names = [name for name in archive.namelist() if name.startswith(prefix)]
        assert len(names) == 12
        archive.extractall(tmp_path, members=names)
    monkeypatch.setattr(renderer, "__file__", str(tmp_path / "app/utils/image_render.py"))
    manifest = json.loads((tmp_path / prefix / "sources.json").read_text())
    assert len(manifest) == 11
    for row in team_rows():
        path = renderer.get_asset_path(2026, "teams", row["code"])
        assert path and path.parent.name == "team-logos"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[path.stem]["sha256"]
        assert manifest[path.stem]["page"].startswith("https://www.formula1.com/en/teams/")
        with Image.open(path) as image:
            assert max(image.size) >= 256
            assert image.getchannel("A").getextrema()[0] < 255


@pytest.mark.parametrize("kind,rows", [("drivers", driver_rows()), ("teams", team_rows())])
def test_card_draws_artwork_for_every_row_and_is_not_a_two_column_grid(kind, rows):
    calls = []
    def loader(code, name, season):
        calls.append(code)
        return Image.new("RGBA", (100, 100), (20, 220, 40, 255))
    picture = Image.open(render_standings("", "", rows, 2026, kind, loader))
    assert calls == [r["code"] for r in rows]
    assert picture.width == 1080 and picture.height > 1000
    for index in range(len(rows)):
        assert picture.getpixel((156, 324 + 68 * index))[:3] == (20, 220, 40)


def test_wide_logos_are_contained_not_circle_cropped():
    source = Image.new("RGBA", (300, 60), (20, 220, 40, 255))
    picture = Image.open(render_standings("", "", team_rows(), 2026, "teams", lambda *args: source))
    assert picture.getpixel((127, 328)) == (20, 220, 40)
    assert picture.getpixel((187, 328)) == (20, 220, 40)


def test_missing_historical_art_does_not_download_current_year_images(monkeypatch):
    monkeypatch.setattr(renderer, "_get_online_driver_url", lambda *args: pytest.fail("Must not download a wrong-year photo"))
    photo = renderer.create_driver_standings_image("", "", [("1", "ALO", "Fernando Alonso", "12.5 очк.")], 1997)
    assert Image.open(photo).width == 1080
    def broken(*args):
        raise OSError("broken image")
    assert Image.open(render_standings("", "", team_rows(), 1997, "teams", broken)).height > 1000


def test_legacy_rows_keep_favorites_and_half_points():
    rows = renderer._standings_rows([("01", "⭐ ALO", "Fernando Alonso", "12.5 очк.")])
    assert rows[0]["points"] == "12.5" and rows[0]["favorite"]
    assert rows[0]["code"] == "ALO"


def test_comparison_graph_handles_gaps_negative_changes_and_zero():
    photo = renderer.create_comparison_image(
        {"name": "Team One", "kind": "teams", "season": 2025, "history": [0, 25, None, 23], "total_points": 23, "cumulative": True},
        {"name": "Team Two", "history": [0, 18, 36, 30], "total_points": 30, "cumulative": True},
        ["First", "Second", "Missing", "Penalty"],
    )
    assert Image.open(photo).size == (1296, 1440)
    with pytest.raises(ValueError):
        renderer.create_comparison_image({"history": []}, {"history": []}, [])
