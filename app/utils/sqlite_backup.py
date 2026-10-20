"""Standard-library backup validation shared by the server and Windows downloader."""
import gzip
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
from contextlib import closing


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_backup(path):
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix='backup-verify-', dir=path.parent) as directory:
        directory = Path(directory)
        source_path = path
        with path.open('rb') as stream:
            compressed = stream.read(2) == b'\x1f\x8b'
        if compressed:
            source_path = directory/'snapshot.db'
            with gzip.open(path,'rb') as source, source_path.open('wb') as target:
                shutil.copyfileobj(source,target)
        with closing(sqlite3.connect(source_path.resolve().as_uri()+'?mode=ro',uri=True)) as source:
            with closing(sqlite3.connect(directory/'restored.db')) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise RuntimeError('Backup restore integrity check failed')
                if target.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise RuntimeError('Backup restore foreign key check failed')
