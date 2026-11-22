"""Allow one running Lanternfish at a time (menu bar app and terminal launches alike)."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

LOCK = Path.home() / "Library" / "Application Support" / "Lanternfish" / "app.lock"


def acquire(path: Path = LOCK) -> int | None:
    """Take the lock and return its file descriptor, or None if another instance holds it.

    Keep the descriptor open for the life of the process; the OS releases the lock on exit,
    including a crash, so a stale lock file never blocks a restart.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd
