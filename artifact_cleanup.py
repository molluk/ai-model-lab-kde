"""Preview-first cleanup of AI Model Lab *application-owned* cache/logs/backups.

Never touches models.json, settings.json, services.json, data/reports,
data/clients, GGUF, external cache directories, or running models.
No symlinks are followed. A candidate's inode must still match the preview.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

CATEGORIES = ("cache", "logs", "backups")
CONFIG_NAMES = {"models.json", "settings.json", "services.json", "build_info.json"}


def targets(root: Path) -> dict[str, tuple[Path, ...]]:
    return {
        "cache": (root / "__pycache__", root / "tests/__pycache__",
                  root / "benchmarks/__pycache__",
                  root / "data/cache", root / "data/tmp"),
        "logs": (root / "data/logs",),
        "backups": (root / "data/backups",),
    }


def _safe_base(root: Path) -> Path:
    root = Path(root).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Каталог установки отсутствует или является ссылкой")
    resolved = root.resolve()
    if resolved == Path("/") or resolved == Path.home().resolve():
        raise ValueError("Отказ: слишком широкий каталог для удаления")
    if not (resolved / "core.py").is_file() or not (resolved / "gui.py").is_file():
        raise ValueError("Не удалось подтвердить каталог установленного AI Model Lab")
    return resolved


def _tree_files(folder: Path):
    """Yield paths and stats, with no symlinks and no external recursion."""
    dirs = []
    files = []
    if folder.is_symlink() or not folder.is_dir():
        return files, dirs
    for current, names, filenames in os.walk(folder, followlinks=False):
        directory = Path(current)
        if directory.is_symlink():
            names[:] = []
            continue
        names[:] = [name for name in names if not (directory / name).is_symlink()]
        dirs.append(directory)
        for filename in filenames:
            path = directory / filename
            try:
                meta = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(meta.st_mode):
                files.append((path, meta))
    return files, dirs


def preview(root: Path, *, selected=CATEGORIES, protected=()) -> dict:
    """Return a stable file snapshot without writing anything."""
    root = _safe_base(root)
    options = tuple(selected)
    if any(category not in CATEGORIES for category in options):
        raise ValueError("Неизвестная категория очистки")
    protected_paths = {str(Path(path).resolve()) for path in protected if path}
    output = {"root": str(root), "categories": {}}
    for category in options:
        entries = []
        folders = []
        bytes_total = 0
        for parent in targets(root)[category]:
            scanned_files, scanned_dirs = _tree_files(parent)
            for file, meta in scanned_files:
                # Configs are never within the selected active storage targets.
                # In backups they *are* snapshots and can be intentionally purged.
                if ((category != "backups" and file.name in CONFIG_NAMES)
                        or str(file.resolve()) in protected_paths):
                    continue
                # Recheck containment. A path through a symlink is never valid.
                if not file.resolve().is_relative_to(parent):
                    continue
                entries.append((str(file.relative_to(root)), meta.st_dev,
                                meta.st_ino, meta.st_size, meta.st_mtime_ns))
                bytes_total += meta.st_size
            folders.extend(str(p.relative_to(root)) for p in scanned_dirs)
        output["categories"][category] = {
            "count": len(entries),
            "bytes": bytes_total,
            "entries": entries,
            "dirs": sorted(set(folders), key=lambda x: len(Path(x).parts), reverse=True),
        }
    return output


def _symlink_component(root: Path, candidate: Path) -> bool:
    """Refuse a path if any component below app root was replaced by a link."""
    pointer = candidate
    while pointer != root:
        if pointer.is_symlink():
            return True
        if pointer == pointer.parent:
            return True
        pointer = pointer.parent
    return False


def apply(plan: dict, *, protected=()) -> dict:
    """Remove *only* files identified in a prior preview; never delete a new file."""
    root = _safe_base(Path(plan["root"]))
    protected_paths = {str(Path(path).resolve()) for path in protected if path}
    counts = {}
    for category, info in plan["categories"].items():
        if category not in CATEGORIES:
            raise ValueError("Недопустимая категория очистки")
        allowed_roots = targets(root)[category]
        removed = 0
        size = 0
        skipped = 0
        for relative, dev, ino, original_size, modified_ns in info["entries"]:
            path = root / relative
            if not any(path.is_relative_to(parent) for parent in allowed_roots):
                raise ValueError("Файл очистки вне разрешённого каталога")
            if (_symlink_component(root, path)
                    or (category != "backups" and path.name in CONFIG_NAMES)
                    or str(path.resolve()) in protected_paths):
                skipped += 1
                continue
            try:
                meta = path.lstat()
                if (not stat.S_ISREG(meta.st_mode) or meta.st_dev != dev
                        or meta.st_ino != ino or meta.st_size != original_size
                        or meta.st_mtime_ns != modified_ns
                        or not path.resolve().is_relative_to(root)):
                    skipped += 1
                    continue
                path.unlink()
                removed += 1
                size += meta.st_size
            except FileNotFoundError:
                skipped += 1
            except OSError:
                skipped += 1
        for relative in info["dirs"]:
            directory = root / relative
            if not any(directory == parent or directory.is_relative_to(parent)
                       for parent in allowed_roots):
                raise ValueError("Каталог очистки вне разрешённой области")
            try:
                if not _symlink_component(root, directory):
                    directory.rmdir()  # only empty folders, never recursive delete
            except OSError:
                pass
        counts[category] = {"removed": removed, "bytes": size, "skipped": skipped}
    return counts


def pretty_bytes(size: int) -> str:
    size = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return str(size)
