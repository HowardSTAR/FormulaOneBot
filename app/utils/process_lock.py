"""OS-owned locks for processes sharing the local SQLite volume."""
import os
from pathlib import Path


class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if handle.tell() == 0:
                    handle.write(b'\0')
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.file = handle
        return True

    def close(self):
        if self.file is not None:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()
            self.file = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f'Another process owns {self.path.name}')
        return self

    def __exit__(self, *exc):
        self.close()
