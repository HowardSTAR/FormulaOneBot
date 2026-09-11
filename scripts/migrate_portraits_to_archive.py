"""One-time migration, with validated hashes and recoverable backups."""
import hashlib
import json
import shutil
import zipfile
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / 'app/portrait_assets/2026').resolve()
    target = (ROOT / 'app/assets/2026/pilots').resolve()
    archive = ROOT / 'app-assets.zip'
    prefix = 'app/assets/2026/pilots/'
    assert source.is_relative_to(ROOT) and target.is_relative_to(ROOT)
    manifest = json.loads((source / 'sources.json').read_text())
    assert len(manifest) == 23
    files = [source / 'sources.json']
    for code, record in manifest.items():
        matches = list(source.glob(f'{code}.*'))
        if not matches:
            content = urllib.request.urlopen(record['image'], timeout=30).read()
            assert hashlib.sha256(content).hexdigest() == record['sha256']
            file = source / (code + Path(record['image']).suffix)
            file.write_bytes(content)
            matches = [file]
        assert len(matches) == 1
        assert hashlib.sha256(matches[0].read_bytes()).hexdigest() == record['sha256']
        files.append(matches[0])
    backup = ROOT / 'artifacts' / ('portrait-migration-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True)
    shutil.copy2(archive, backup / archive.name)
    temporary = ROOT / '.app-assets.portraits.tmp.zip'
    preserved = {}
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as result:
        for item in original.infolist():
            if not item.filename.replace('\\', '/').startswith(prefix):
                content = original.read(item)
                preserved[item.filename] = hashlib.sha256(content).hexdigest()
                result.writestr(item, content)
        for file in files:
            result.write(file, prefix + file.name)
    with zipfile.ZipFile(temporary) as result:
        assert result.testzip() is None
        for name, digest in preserved.items():
            assert hashlib.sha256(result.read(name)).hexdigest() == digest
        assert len([name for name in result.namelist() if name.startswith(prefix)]) == 24
        for file in files:
            assert result.read(prefix + file.name) == file.read_bytes()
    if target.exists():
        shutil.move(str(target), str(backup / 'old-2026-pilots'))
    target.mkdir(parents=True)
    for file in files:
        shutil.copy2(file, target / file.name)
    temporary.replace(archive)
    # Remove the duplicate source from deployment, retaining recovery copies.
    shutil.move(str(source.parent), str(backup / 'portrait_assets'))
    print(f'Packed 23 portraits; preserved {len(preserved)} other entries. Backup: {backup}')


if __name__ == '__main__':
    main()
