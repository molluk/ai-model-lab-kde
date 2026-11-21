"""Small stdlib-only advisory lock for model instance metadata.

Use a one-byte region lock on Windows, flock on POSIX. Never emulate locking
with a bare file-exists test (it is unsafe between processes).
"""
from __future__ import annotations

import contextlib
import os


@contextlib.contextmanager
def exclusive_lock(handle):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
