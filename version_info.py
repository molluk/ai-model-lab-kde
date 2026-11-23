"""Version and Git provenance for source checkouts and installed builds.

The installed application does not have a .git directory. Linux install.sh
generates build_info.json from the source tree at installation time.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

APP_VERSION = "3.10+dev"
MANIFEST = "build_info.json"
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def _git(source: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), *args],
            capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def source_build_info(source: Path) -> dict:
    """Identify only this exact Git checkout, never a parent repository."""
    source = Path(source).resolve()
    top_level = _git(source, "rev-parse", "--show-toplevel")
    commit = None
    dirty = False
    if top_level and Path(top_level).resolve() == source:
        sha = (_git(source, "rev-parse", "HEAD") or "").lower()
        if _SHA.fullmatch(sha):
            commit = sha
            status = _git(source, "status", "--porcelain", "--untracked-files=no")
            dirty = bool(status) if status is not None else False
    return {"version": APP_VERSION, "commit": commit, "dirty": dirty}


def _safe_manifest(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    version = raw.get("version")
    sha = raw.get("commit")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+_-]{1,60}", version):
        return None
    if sha is not None:
        if not isinstance(sha, str) or not _SHA.fullmatch(sha.lower()):
            return None
        sha = sha.lower()
    return {"version": version, "commit": sha, "dirty": raw.get("dirty") is True}


def read_build_info(root: Path | None = None) -> dict:
    """Use installed build manifest, otherwise inspect the actual source repo."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    path = root / MANIFEST
    try:
        saved = _safe_manifest(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        saved = None
    return saved if saved is not None else source_build_info(root)


def short_label(info: dict) -> str:
    sha = info.get("commit")
    suffix = " *" if info.get("dirty") else ""
    return f"v{info['version']} · {sha[:8] if sha else 'SHA: —'}{suffix}"


def detail_label(info: dict, translate=lambda text: text) -> str:
    lines = [
        f"{translate('Версия')}: {info['version']}",
        f"{translate('Коммит')}: {info.get('commit') or translate('Неизвестно')}",
    ]
    if info.get("dirty"):
        lines.append(translate("Локальные изменения"))
    return "\n".join(lines)


def write_manifest(destination: Path, source: Path) -> dict:
    """Atomically replace only the app-owned build manifest in destination."""
    info = source_build_info(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + f".{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return info


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AI Model Lab build identity")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write", type=Path, help="Installed build_info.json destination")
    args = parser.parse_args(argv)
    info = write_manifest(args.write, args.source) if args.write else read_build_info(args.source)
    print(short_label(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
