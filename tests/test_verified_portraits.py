import hashlib
import io
import json
import zipfile
import pytest
from pathlib import Path
from PIL import Image


@pytest.fixture(autouse=True)
def archived_assets(tmp_path, monkeypatch):
    from app.api import miniapp_api as api
    from app.utils import image_render as renderer
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(root / 'app-assets.zip') as archive:
        names = [n for n in archive.namelist() if n.startswith('app/assets/2026/pilots/')]
        assert len(names) == 24  # 23 originals + provenance, no obsolete portraits
        archive.extractall(tmp_path, members=names)
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(renderer, '__file__', str(tmp_path / 'app/utils/image_render.py'))
    return tmp_path


def test_verified_set_complete_unique_and_square(archived_assets):
    from app.api.miniapp_api import _find_local_pilot_portrait_path, _render_head_crop_png_bytes
    root = archived_assets
    sources = json.loads((root / 'app/assets/2026/pilots/sources.json').read_text())
    assert len(sources) == 23
    assert len({item['sha256'] for item in sources.values()}) == 23
    for code, record in sources.items():
        path = _find_local_pilot_portrait_path(2026, code, 'Wrong supplied name')
        assert path.stem == code
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
        with Image.open(io.BytesIO(_render_head_crop_png_bytes(path))) as image:
            assert image.size == (256, 256)


def test_legacy_matching_is_exact(tmp_path, monkeypatch):
    from app.api import miniapp_api as api
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    folder = tmp_path / 'app/assets/2025/pilots'
    folder.mkdir(parents=True)
    (folder / 'Lance Stroll.png').touch()
    assert api._find_local_pilot_portrait_path(2025, None, 'Lance') is None
    assert api._find_local_pilot_portrait_path(2025, 'STR', None).name == 'Lance Stroll.png'


def test_verified_aliases_and_unknown():
    from app.api.miniapp_api import _find_local_pilot_portrait_path
    assert _find_local_pilot_portrait_path(2026, None, 'Nico Hülkenberg').stem == 'HUL'
    assert _find_local_pilot_portrait_path(2026, '../STR', None) is None


def test_bot_uses_same_archived_originals_without_network(archived_assets, monkeypatch):
    from app.utils import image_render as renderer
    from app.api.miniapp_api import _find_local_pilot_portrait_path
    def reject_network(*args):
        pytest.fail('Verified local photos must not request online images')
    monkeypatch.setattr(renderer, '_get_online_driver_url', reject_network)
    sources = json.loads((archived_assets / 'app/assets/2026/pilots/sources.json').read_text())
    for code in sources:
        path = _find_local_pilot_portrait_path(2026, code, None)
        assert renderer.get_asset_path(2026, 'pilots', code) == path
        photo = renderer._get_driver_photo(code, 'Wrong name', 2026)
        with Image.open(path) as expected:
            assert photo.tobytes() == expected.convert('RGBA').tobytes()
    assert renderer.get_asset_path(2026, 'pilots', 'Lance Stroll').stem == 'STR'
    assert renderer.get_asset_path(2026, 'pilots', 'Nico Hülkenberg').stem == 'HUL'


def test_bot_classification_portrait_loader(archived_assets, monkeypatch):
    from app.utils import image_render, classification_card
    sources = json.loads((archived_assets / 'app/assets/2026/pilots/sources.json').read_text())
    def inspect(event, session, rows, season, favorites, loader):
        for code in sources:
            assert loader(code, 'Wrong name', season) is not None
        return 'checked'
    monkeypatch.setattr(classification_card, 'render_classification', inspect)
    assert image_render.create_f1_style_classification_image('QA', 'race', [], 2026) == 'checked'


@pytest.mark.asyncio
async def test_actual_http_portraits_from_archive(archived_assets):
    from httpx import ASGITransport, AsyncClient
    from app.api.miniapp_api import web_app
    sources = json.loads((archived_assets / 'app/assets/2026/pilots/sources.json').read_text())
    async with AsyncClient(transport=ASGITransport(app=web_app), base_url='http://test') as client:
        for code in sources:
            response = await client.get('/api/pilot-portrait', params={'season': 2026, 'code': code, 'strict': 'true'})
            assert response.status_code == 200
            with Image.open(io.BytesIO(response.content)) as image:
                assert image.size == (256, 256)


@pytest.mark.asyncio
async def test_compact_portrait_uses_selected_season_and_has_no_generic_fallback(archived_assets):
    from httpx import ASGITransport, AsyncClient
    from app.api.miniapp_api import web_app

    original = archived_assets / 'app/assets/2026/pilots/VER.webp'
    archive_path = Path(__file__).resolve().parents[1] / 'app-assets.zip'
    with zipfile.ZipFile(archive_path) as archive:
        archive.extract('app/assets/2025/pilots/Max Verstappen.png', archived_assets)

    async with AsyncClient(transport=ASGITransport(app=web_app), base_url='http://test') as client:
        response = await client.get('/api/pilot-portrait', params={'season': 2026, 'code': 'VER', 'compact': True})
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/webp'
        assert len(response.content) < original.stat().st_size
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.width <= 224 and image.height <= 320
            assert image.mode == 'RGBA'

        legacy = await client.get('/api/pilot-portrait', params={'season': 2025, 'code': 'VER', 'compact': True})
        assert legacy.status_code == 200
        assert legacy.content != response.content

        for season, code in ((1900, 'VER'), (2026, 'CAM'), (2026, 'MIN'), (2026, 'FOR'), (2025, 'LIN')):
            missing = await client.get('/api/pilot-portrait', params={'season': season, 'code': code, 'compact': True})
            assert missing.status_code == 204
            assert not missing.content
