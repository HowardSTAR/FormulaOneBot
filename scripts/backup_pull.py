"""Pull verified backups to a PC; unavailable disks/SSH are retried next run."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.sqlite_backup import checksum as digest, verify_backup as verify

NAME = re.compile(r'backup_\d{8}T\d{12}Z\.db(?:\.gz)?\Z')
LOG = logging.getLogger('backup-pull')
LIST = '''import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
print(json.dumps([json.loads(f.read_text()) for f in sorted(p.glob("backup_*.json")) if not f.with_suffix(".replicated").exists()]))
'''
ACK = '''import json,pathlib,sys
p=pathlib.Path(sys.argv[1])/sys.argv[2]
m=json.loads(p.with_suffix(".json").read_text())
assert m["sha256"]==sys.argv[3]
p.with_suffix(".replicated").write_text(sys.argv[3])
'''


class SSH:
    def __init__(self, source, directory, identity=None):
        if source.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.@:-]+', source):
            raise ValueError('Invalid SSH source')
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', directory):
            raise ValueError('Remote directory must be an absolute path without shell characters')
        self.source, self.directory = source, directory.rstrip('/')
        self.options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes']
        if identity:
            self.options += ['-i', str(identity), '-o', 'IdentitiesOnly=yes']

    def command(self, code, *args):
        command = 'python3 -c '+shlex.quote(code)+' '+shlex.join([self.directory, *args])
        return subprocess.run(['ssh', *self.options, self.source, command], check=True,
                              capture_output=True, text=True, timeout=60).stdout

    def list(self):
        return json.loads(self.command(LIST))

    def download(self, name, target):
        subprocess.run(['scp', '-q', *self.options, f'{self.source}:{self.directory}/{name}', str(target)],
                       check=True, capture_output=True, timeout=300)

    def acknowledge(self, name, checksum):
        self.command(ACK, name, checksum)


def sync(remote, destination):
    # A missing drive/path is not created: wait until the designated location returns.
    if not destination.is_dir():
        LOG.info('Backup destination is offline; waiting for the next run')
        return 0
    count = 0
    for manifest in remote.list():
        name = manifest.get('name', '')
        expected = manifest.get('sha256', '')
        if not NAME.fullmatch(name) or not re.fullmatch(r'[a-f0-9]{64}', expected) or manifest.get('verified') is not True:
            raise ValueError('Invalid backup manifest')
        target = destination/name
        if not target.exists() or digest(target) != expected:
            partial = target.with_suffix('.partial')
            try:
                remote.download(name, partial)
                if partial.stat().st_size != manifest['bytes'] or digest(partial) != expected:
                    raise ValueError('Downloaded backup checksum does not match')
                verify(partial)
                os.replace(partial, target)
            finally:
                partial.unlink(missing_ok=True)
        else:
            verify(target)
        target.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
        # A lost acknowledgement is safe: the next run verifies the local copy again.
        remote.acknowledge(name, expected)
        LOG.info('Backup verified and replicated: %s', name)
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='root@85.198.68.135')
    parser.add_argument('--remote-dir', default='/root/FormulaOneBot/data/backups')
    parser.add_argument('--destination', type=Path, default=Path(r'D:\backup - f1'))
    parser.add_argument('--identity', type=Path)
    args = parser.parse_args()
    handlers = [RotatingFileHandler(args.destination/'backup-pull.log', maxBytes=1_000_000,
                                   backupCount=2, encoding='utf-8')] if args.destination.is_dir() else []
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', handlers=handlers)
    try:
        sync(SSH(args.source, args.remote_dir, args.identity), args.destination)
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, sqlite3.Error) as exc:
        # Log categories only: SSH output may contain host/account configuration.
        LOG.warning('Replication deferred (%s); originals remain on the server', type(exc).__name__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
