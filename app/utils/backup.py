"""Verified SQLite snapshots; unreplicated copies survive retention cleanup."""
import gzip
import shutil
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.db import db
from app.utils.process_lock import ProcessLock
from app.utils.sqlite_backup import checksum, verify_backup


def backup_directory():
    return Path(os.getenv('BACKUP_DIR') or db.db_path.parent / 'backups')


def create_backup():
    directory = backup_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with ProcessLock(directory / '.backup.lock'):
        now = datetime.now(timezone.utc)
        path = directory / f"backup_{now.strftime('%Y%m%dT%H%M%S%fZ')}.db.gz"
        raw = path.with_suffix('.sqlite.partial')
        partial = path.with_suffix('.gz.partial')
        try:
            source = sqlite3.connect(db.db_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
            target = sqlite3.connect(raw)
            try:
                source.backup(target)
            finally:
                source.close()
                target.close()
            verify_backup(raw)
            with raw.open('rb') as source, gzip.open(partial, 'wb', compresslevel=6) as target:
                shutil.copyfileobj(source, target)
            # Check the compressed artifact too, before publishing its manifest.
            verify_backup(partial)
            digest = checksum(partial)
            partial.replace(path)
            manifest = {'name': path.name, 'sha256': digest, 'bytes': path.stat().st_size,
                        'created': now.timestamp(), 'verified': True}
            metadata = path.with_suffix('.json.partial')
            metadata.write_text(json.dumps(manifest), encoding='utf-8')
            metadata.replace(path.with_suffix('.json'))
        finally:
            raw.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
        clean_old_backups(int(os.getenv('BACKUP_KEEP', '7')))
        return manifest


def clean_old_backups(keep=7):
    if keep < 1:
        raise ValueError('BACKUP_KEEP must be positive')
    directory = backup_directory()
    files = sorted(directory.glob('backup_*.db.gz'), reverse=True)
    for path in files[keep:]:
        # An offline PC is expected: preserve its entire unreplicated backlog.
        if not path.with_suffix('.replicated').exists():
            continue
        path.unlink()
        for suffix in ('.json', '.replicated'):
            path.with_suffix(suffix).unlink(missing_ok=True)


def backup_status():
    directory = backup_directory()
    manifests = sorted(directory.glob('backup_*.json'), reverse=True)
    if not manifests:
        return {'last_verified': None, 'pending_replication': 0, 'last_replicated': None}
    verified = [json.loads(path.read_text(encoding='utf-8')) for path in manifests]
    markers = list(directory.glob('backup_*.replicated'))
    return {'last_verified': verified[0]['created'],
            'pending_replication': sum(not p.with_suffix('.replicated').exists() for p in manifests),
            'last_replicated': max((p.stat().st_mtime for p in markers), default=None)}
