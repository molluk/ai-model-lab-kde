"""Periodic *cache-only* housekeeping for AI Model Lab.

The GUI owns the timer. This module persists the schedule across restarts,
and runs an overdue cleanup once on the next start when the GUI is idle.
No background daemon, systemd unit, or network access is created.

The only deletion path is artifact_cleanup.preview(selected=('cache',))
followed by artifact_cleanup.apply() on the exact preview. Never select
logs, backups, reports, models, settings, or client configurations.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

import artifact_cleanup


INTERVAL_KEY = "auto_cache_cleanup_hours"
MIN_HOURS = 1
MAX_HOURS = 720
STATE_NAME = "auto_cache_cleanup_state.json"
LOCK_NAME = "auto_cache_cleanup.lock"


def validate_hours(value) -> int:
    """Zero disables the timer; otherwise a whole number of hours 1..720."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Интервал автоочистки должен быть целым числом часов")
    if value != 0 and not MIN_HOURS <= value <= MAX_HOURS:
        raise ValueError(f"Интервал автоочистки: 0 или {MIN_HOURS}–{MAX_HOURS} часов")
    return value


def _root(root: Path) -> Path:
    """Only the installed application directory is eligible."""
    return artifact_cleanup._safe_base(Path(root))


def _state_path(root: Path) -> Path:
    return root / "data" / STATE_NAME


def _read_state(root: Path) -> dict:
    target = _state_path(root)
    if target.is_symlink():
        raise RuntimeError("Файл расписания очистки не должен быть символической ссылкой")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}


def _write_state(root: Path, state: dict):
    data_dir = root / "data"
    if data_dir.is_symlink():
        raise RuntimeError("Каталог данных является символической ссылкой")
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    file = _state_path(root)
    if file.is_symlink():
        raise RuntimeError("Файл расписания очистки является символической ссылкой")
    fd, temporary = tempfile.mkstemp(prefix=".cache-cleanup-", suffix=".tmp",
                                    dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _lock(root: Path):
    data_dir = root / "data"
    if data_dir.is_symlink():
        raise RuntimeError("Каталог данных является символической ссылкой")
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lockfile = data_dir / LOCK_NAME
    if lockfile.is_symlink():
        raise RuntimeError("Недопустимая ссылка в файле блокировки")
    fd = os.open(lockfile, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _schedule_updated(state: dict, hours: int, now: float, *, reset: bool = False) -> tuple[dict, bool]:
    """Restore the saved due time unless the interval is new/changed."""
    previous = state.get("interval_hours")
    due = state.get("next_due_ts")
    if (reset or previous != hours or
            (hours > 0 and (not isinstance(due, (int, float)) or isinstance(due, bool)))):
        state = dict(state)
        state["interval_hours"] = hours
        state["next_due_ts"] = now + hours * 3600 if hours else None
        state.pop("last_error", None)
        return state, True
    return state, False


def configure(root: Path, hours: int, *, now: float | None = None, reset: bool = False) -> dict:
    """Persist an interval change, without deleting anything."""
    hours = validate_hours(hours)
    root = _root(root)
    now = time.time() if now is None else float(now)
    with _lock(root) as acquired:
        if not acquired:
            return {"status": "busy"}
        before = _read_state(root)
        after, changed = _schedule_updated(before, hours, now, reset=reset)
        if changed:
            _write_state(root, after)
        return {"status": "configured" if changed else "unchanged", "schedule": after}


def status(root: Path, hours: int, *, now: float | None = None) -> dict:
    """Read-only status, safe for the Qt event thread."""
    hours = validate_hours(hours)
    root = _root(root)
    now = time.time() if now is None else float(now)
    data = _read_state(root)
    if hours == 0:
        return {"status": "disabled", "interval_hours": 0, "last_run_ts": data.get("last_run_ts")}
    if data.get("interval_hours") != hours or not isinstance(data.get("next_due_ts"), (int, float)):
        return {"status": "uninitialized", "interval_hours": hours}
    due = float(data["next_due_ts"])
    return {
        "status": "due" if now >= due else "scheduled",
        "interval_hours": hours,
        "next_due_ts": due,
        "remaining_seconds": max(0, due - now),
        "last_run_ts": data.get("last_run_ts"),
        "last_count": data.get("last_count", 0),
        "last_bytes": data.get("last_bytes", 0),
        "last_error": data.get("last_error"),
    }


def run_due(root: Path, hours: int, *, now: float | None = None, busy: bool = False) -> dict:
    """Run at most once per interval; defer while app is busy.

    Nonblocking interprocess lock avoids double deletion when two GUI windows
    are running. An overdue schedule survives app restarts.
    """
    hours = validate_hours(hours)
    if hours == 0:
        return {"status": "disabled"}
    if busy:
        return {"status": "busy"}
    root = _root(root)
    now = time.time() if now is None else float(now)
    with _lock(root) as acquired:
        if not acquired:
            return {"status": "busy"}
        schedule = _read_state(root)
        schedule, updated = _schedule_updated(schedule, hours, now)
        if updated:
            _write_state(root, schedule)
            return {"status": "scheduled", "next_due_ts": schedule["next_due_ts"]}
        if now < float(schedule["next_due_ts"]):
            return {"status": "not_due", "next_due_ts": schedule["next_due_ts"]}
        try:
            plan = artifact_cleanup.preview(root, selected=("cache",))
            result = artifact_cleanup.apply(plan)
            count = int(result["cache"]["removed"])
            bytes_removed = int(result["cache"]["bytes"])
        except Exception as exc:
            # Don't hammer a failing filesystem every minute.
            schedule["next_due_ts"] = now + min(3600, hours * 3600)
            schedule["last_error"] = str(exc)[:500]
            _write_state(root, schedule)
            return {"status": "error", "error": str(exc), "next_due_ts": schedule["next_due_ts"]}
        schedule.update({
            "last_run_ts": now,
            "last_count": count,
            "last_bytes": bytes_removed,
            "next_due_ts": now + hours * 3600,
        })
        schedule.pop("last_error", None)
        _write_state(root, schedule)
        return {"status": "cleaned", "count": count, "bytes": bytes_removed,
                "next_due_ts": schedule["next_due_ts"]}


def next_run_label(root: Path, hours: int, *, now: float | None = None) -> str:
    """User-facing Russian schedule summary for the Settings panel."""
    entry = status(root, hours, now=now)
    state = entry["status"]
    if state == "disabled":
        return "Автоочистка выключена. Логи, бэкапы и модели не затрагиваются."
    if state == "uninitialized":
        return "Расписание будет создано при запуске таймера."
    due = dt.datetime.fromtimestamp(entry["next_due_ts"]).strftime("%d.%m.%Y %H:%M")
    label = "Очистка ожидает освобождения приложения" if state == "due" else f"Следующая очистка: {due}"
    if entry.get("last_run_ts"):
        last = dt.datetime.fromtimestamp(entry["last_run_ts"]).strftime("%d.%m.%Y %H:%M")
        label += f" · Последняя: {last}, {entry.get('last_count', 0)} файлов"
    if entry.get("last_error"):
        label += " · Последняя ошибка: " + str(entry["last_error"])[:130]
    return label
