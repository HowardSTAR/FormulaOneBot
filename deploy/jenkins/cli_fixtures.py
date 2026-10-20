"""Portable shell and fake CLI fixtures; never invoke the real Docker client."""
import os
from pathlib import Path
import shutil
import sys
import unittest


def shell_path(program='bash'):
    # Windows' bash.exe may launch WSL. Prefer the installed Git Bash instead.
    if os.name == 'nt':
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
        if candidate.is_file():
            return str(candidate)
    shell = shutil.which(program)
    if shell is None:
        raise unittest.SkipTest(f'CLI contract tests require {program} or Git Bash')
    return shell


def write_fake_cli(path, source):
    interpreter = '/usr/bin/env python' if os.name == 'nt' else sys.executable
    path.write_text(source.replace('/usr/bin/python3', interpreter), encoding='utf-8')
    path.chmod(0o700)


def cli_environment(directory, **values):
    path = os.pathsep.join((str(directory), str(Path(sys.executable).parent), os.environ['PATH']))
    return dict(os.environ, PATH=path, **values)
