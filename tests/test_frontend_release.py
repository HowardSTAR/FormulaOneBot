"""The preserved public interface must remain complete and byte-identical."""
import hashlib
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_public_release_is_complete():
    metadata = json.loads((ROOT / 'legacy/release.json').read_text())
    archive = ROOT / 'legacy/public-frontend.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == metadata['archive_sha256']
    with tarfile.open(archive) as source:
        members = {member.name.removeprefix('./'): member for member in source.getmembers()}
        assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in members)
        assert all(not member.issym() and not member.islnk() for member in members.values())
        html = source.extractfile(members['index.html']).read()
        assert hashlib.sha256(html).hexdigest() == metadata['index_sha256']
        for asset in re.findall(rb'(?:src|href)="(/static/[^"?]+)', html):
            assert asset.decode().lstrip('/') in members
        assert 'race-game/index.html' in members
        assert not any(Path(name).name == '.env' or name.endswith(('.pem', '.key', '.db')) for name in members)


def test_image_keeps_both_frontends_and_compose_selects_them():
    # Verify the deployment boundary: the two shells have separate processes.
    import yaml
    config = yaml.safe_load((ROOT / 'docker-compose-build.yml').read_text())
    services = config['services']
    assert services['web']['environment']['FRONTEND_VARIANT'] == 'legacy'
    assert services['web-new']['environment']['FRONTEND_VARIANT'] == 'new'
    assert services['web']['image'] == services['web-new']['image']
    assert services['web']['volumes'] == services['web-new']['volumes']
    assert services['web-new']['environment']['PUBLIC_WEB_URL'] == 'https://new.f1hub.ru'
