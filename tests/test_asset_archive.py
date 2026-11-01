"""Asset round trips must preserve bytes and reject incomplete or unsafe archives."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile


spec = importlib.util.spec_from_file_location(
    "pack_assets", Path(__file__).resolve().parents[1] / "scripts/pack_assets.py"
)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class AssetArchiveTests(unittest.TestCase):
    def test_round_trip_covers_every_consumer_and_excludes_generated_game(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            expected = {
                "app/assets/fonts/example.ttf": b"font",
                "app/profile_avatar_assets/driver.png": b"avatar",
                "front/src/assets/navigation/home.png": b"navigation",
                "front/public/app-icon.svg": b"icon",
                "front/public/static/circuit/São Paulo.svg": b"circuit",
                "race-game/public/assets/car.png": b"car",
                "art/password-racer/detail.webp": b"preview",
            }
            for name, content in {
                **expected, "front/public/race-game/assets/car.png": b"generated",
                "front/src/assets/example.ts": b"source",
            }.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            archive = assets.pack_assets(root)
            first = archive.read_bytes()
            assets.pack_assets(root)
            self.assertEqual(first, archive.read_bytes())
            restored = root / "restored"
            assets.extract_assets(root, restored)
            actual = {p.relative_to(restored).as_posix(): p.read_bytes()
                      for p in restored.rglob("*") if p.is_file()}
            self.assertEqual(expected, actual)

    def test_partial_extraction_cannot_replace_existing_archive(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app/assets").mkdir(parents=True)
            (root / "app/assets/icon.png").write_bytes(b"present")
            archive = root / "app-assets.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("front/public/missing.png", b"keep me")
            before = archive.read_bytes()
            with self.assertRaises(FileNotFoundError):
                assets.pack_assets(root)
            self.assertEqual(before, archive.read_bytes())

    def test_extraction_validates_all_paths_before_writing(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with ZipFile(root / "app-assets.zip", "w") as output:
                output.writestr("app/assets/good.png", b"good")
                output.writestr("app/assets/../../escape.png", b"bad")
            with self.assertRaises(ValueError):
                assets.extract_assets(root, root / "restored")
            self.assertFalse((root / "restored").exists())


if __name__ == "__main__":
    unittest.main()
