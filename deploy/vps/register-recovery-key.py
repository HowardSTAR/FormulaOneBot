#!/usr/bin/python3
"""Authorize an SSH key solely to read the deployment backup stream."""
import base64
import fcntl
import os
from pathlib import Path
import re
import sys

PREFIX = 'restrict,command="/usr/local/sbin/turbotears-export-backup"'


def register(key):
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]{68}", key):
        raise SystemExit("Expected an Ed25519 public key")
    blob = base64.b64decode(key.split()[1], validate=True)
    if not blob.startswith(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20") or len(blob) != 51:
        raise SystemExit("Invalid Ed25519 public key")

    os.umask(0o077)
    directory = Path("/root/.ssh")
    directory.mkdir(mode=0o700, exist_ok=True)
    line = f"{PREFIX} {key} turbotears-backup"
    with (directory / "authorized_keys").open("a+", encoding="utf-8") as keys:
        fcntl.flock(keys, fcntl.LOCK_EX)
        os.fchmod(keys.fileno(), 0o600)
        keys.seek(0)
        existing = keys.read()
        if line in existing.splitlines():
            return
        if any(key.split()[1] in record.split() for record in existing.splitlines()):
            raise SystemExit("Use a dedicated backup key")
        keys.write(("" if not existing or existing.endswith("\n") else "\n") + line + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Pass one public key")
    register(sys.argv[1])
    print("Restricted backup key authorized")
