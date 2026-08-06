"""Cross-platform advisory file locking for AIMAOS state mutations."""
from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from typing import IO, Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


_registry_guard = threading.Lock()
_process_locks: dict[str, threading.Lock] = {}
_held_process_locks: dict[int, threading.Lock] = {}


def _process_lock(handle: IO) -> threading.Lock:
    name = getattr(handle, "name", None)
    key = os.path.normcase(os.path.abspath(os.fspath(name))) if name else f"fd:{handle.fileno()}"
    with _registry_guard:
        return _process_locks.setdefault(key, threading.Lock())


def _ensure_lock_byte(handle: IO) -> None:
    """Windows byte-range locks require the lock file to contain one byte."""
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        try:
            handle.write(b"\0")
        except TypeError:
            handle.write("\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def lock_file(handle: IO, *, poll_interval: float = 0.05) -> None:
    """Acquire an exclusive advisory lock and wait until it is available."""
    local_lock = _process_lock(handle)
    local_lock.acquire()
    try:
        if os.name == "nt":
            _ensure_lock_byte(handle)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(poll_interval)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX)
        with _registry_guard:
            _held_process_locks[id(handle)] = local_lock
    except BaseException:
        local_lock.release()
        raise


def unlock_file(handle: IO) -> None:
    """Release a lock previously acquired with :func:`lock_file`."""
    try:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        with _registry_guard:
            local_lock = _held_process_locks.pop(id(handle), None)
        if local_lock is not None:
            local_lock.release()


@contextmanager
def exclusive_file_lock(path: str | os.PathLike[str]) -> Iterator[IO[bytes]]:
    """Open *path* and hold an exclusive lock for the context lifetime."""
    lock_path = os.path.abspath(os.fspath(path))
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    with open(lock_path, "a+b") as handle:
        lock_file(handle)
        try:
            yield handle
        finally:
            unlock_file(handle)
