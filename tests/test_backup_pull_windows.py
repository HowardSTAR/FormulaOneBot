"""Backup transport children must stay console-free even under pythonw."""
import subprocess
import sys

import pytest

from scripts import backup_pull


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows console behavior')
@pytest.mark.parametrize('operation', ['list', 'download', 'acknowledge'])
def test_transport_child_has_no_console(operation, monkeypatch, tmp_path):
    run = subprocess.run
    calls = []

    def probe_child(command, **kwargs):
        calls.append(command[0])
        # Execute a real console program with the transport's actual options.
        # A mock alone cannot establish that Windows did not allocate a console.
        return run([sys.executable, '-c',
                    'import ctypes; '
                    'assert not ctypes.windll.kernel32.GetConsoleWindow(), "Unexpected console"; '
                    'print("[]")'], **kwargs)

    monkeypatch.setattr(backup_pull.subprocess, 'run', probe_child)
    remote = backup_pull.SSH('user@example.test', '/backups')
    if operation == 'list':
        assert remote.list() == []
    elif operation == 'download':
        remote.download('backup.db.gz', tmp_path/'backup.db.gz')
    else:
        remote.acknowledge('backup.db.gz', 'a'*64)
    assert calls == ['scp' if operation == 'download' else 'ssh']
