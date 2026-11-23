"""Strict Windows process ownership for AI Model Lab-managed llama-server.exe.

The marker is PID + creation time + executable path + complete argv. Failure to
read any required attribute fails closed; a listening port is never ownership.
Windows implementation only; Linux retains the existing /proc checks.
"""
from __future__ import annotations

import os
from pathlib import Path


def _psutil():
    import psutil
    return psutil


def _canonical(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _match(proc, meta: dict) -> bool:
    try:
        pid = int(meta["pid"])
        timestamp = float(meta["created_at"])
        expected_exe = str(meta["exe"])
        argv = meta["argv"]
        if (pid <= 1 or timestamp <= 0 or not isinstance(argv, list)
                or not argv or any(not isinstance(x, str) for x in argv)):
            return False
        if proc.pid != pid or abs(proc.create_time() - timestamp) > 0.001:
            return False
        if _canonical(proc.exe()) != _canonical(expected_exe):
            return False
        observed = proc.cmdline()
        if not observed or observed[1:] != argv[1:]:
            return False
        if _canonical(observed[0]) != _canonical(argv[0]):
            return False
        return True
    except (OSError, KeyError, TypeError, ValueError, IndexError):
        return False


def capture(pid: int, argv: list[str]) -> dict:
    """Snapshot the directly spawned process, rejecting substituted argv/exe."""
    psutil = _psutil()
    try:
        proc = psutil.Process(int(pid))
        with proc.oneshot():
            expected = {"pid": int(pid), "created_at": proc.create_time(),
                        "exe": proc.exe(), "argv": list(argv)}
            if not _match(proc, expected) or _canonical(argv[0]) != _canonical(expected["exe"]):
                raise RuntimeError("Запущенный процесс не совпадает с ожидаемым исполняемым файлом/аргументами")
            return expected
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
        raise RuntimeError("Невозможно подтвердить принадлежность запущенного Windows-процесса") from exc


def is_owned(meta: dict) -> bool:
    """Never infer ownership from a PID or an open network port alone."""
    if not isinstance(meta, dict):
        return False
    try:
        psutil = _psutil()
        proc = psutil.Process(int(meta["pid"]))
        with proc.oneshot():
            return _match(proc, meta)
    except (OSError, KeyError, TypeError, ValueError, psutil.NoSuchProcess,
            psutil.AccessDenied, psutil.ZombieProcess):
        return False


def terminate_owned(meta: dict) -> bool:
    """Terminate only a positively identified process, never its PID alone."""
    if not isinstance(meta, dict):
        return False
    psutil = _psutil()
    try:
        proc = psutil.Process(int(meta["pid"]))
        with proc.oneshot():
            if not _match(proc, meta):
                return False
        # psutil Process retains creation time; terminate() checks reuse.
        proc.terminate()
        return True
    except (OSError, KeyError, TypeError, ValueError, psutil.NoSuchProcess,
            psutil.AccessDenied, psutil.ZombieProcess):
        return False
