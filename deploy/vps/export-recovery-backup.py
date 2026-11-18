#!/usr/bin/python3
"""Export one consistent deployment snapshot over a restricted SSH connection."""
import fcntl
import gzip
import io
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

APP = Path("/opt/f1hub")
CONFIG = (".env", "Dockerfile", "docker-compose-build.yml", "nginx.conf", "deploy/vps", "secrets")
EXTERNAL_CONFIG = (
    ("/opt/f1hub-ci", "f1hub-ci"),
    ("/etc/letsencrypt", "letsencrypt"),
    ("/usr/local/sbin/turbotears-export-backup", "backup-tools/export-recovery-backup.py"),
    ("/usr/local/sbin/turbotears-register-backup-key", "backup-tools/register-recovery-key.py"),
)


def snapshot(source_path, copy_path):
    deadline = time.monotonic() + 300

    def check_deadline(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite snapshot timed out")

    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(copy_path)) as copy:
            source.backup(copy, pages=1024, progress=check_deadline)
            if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite integrity check failed")
            if copy.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("SQLite foreign key check failed")


def export():
    if os.environ.get("SSH_ORIGINAL_COMMAND", ""):
        raise PermissionError("This SSH key is restricted to the backup stream")
    with Path("/run/lock/turbotears-recovery-backup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="turbotears-recovery-") as directory:
            copy_path = Path(directory) / "bot.db"
            snapshot(APP / "data/bot.db", copy_path)
            image = subprocess.check_output(
                ["/usr/bin/docker", "image", "inspect", "--format",
                 '{{.Id}} {{index .Config.Labels "version"}}', "formulaonebot-app:latest"],
                text=True, timeout=10,
            ).strip().split()
            metadata = json.dumps({
                "format": 1,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "image_id": image[0],
                "app_revision": image[1] if len(image) > 1 else None,
                "sqlite_checks": ["integrity_check", "foreign_key_check"],
            }, indent=2).encode() + b"\n"

            with gzip.GzipFile(fileobj=sys.stdout.buffer, mode="wb", compresslevel=3) as stream:
                with tarfile.open(fileobj=stream, mode="w|", dereference=False) as archive:
                    marker = tarfile.TarInfo("backup-info.json")
                    marker.size = len(metadata)
                    archive.addfile(marker, io.BytesIO(metadata))
                    db_entry = archive.gettarinfo(str(copy_path), "f1hub/data/bot.db")
                    db_entry.mode = 0o600
                    with copy_path.open("rb") as content:
                        archive.addfile(db_entry, content)
                    for item in CONFIG:
                        archive.add(APP / item, arcname=f"f1hub/{item}")
                    for path, name in EXTERNAL_CONFIG:
                        if Path(path).exists():
                            archive.add(path, arcname=name)


if __name__ == "__main__":
    try:
        export()
    except Exception as error:
        # Do not emit file contents or the values of environment variables.
        print(f"Backup export failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
