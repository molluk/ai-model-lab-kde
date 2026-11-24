#!/usr/bin/env python3
"""Non-destructive local GGUF catalogue import for AI Model Lab.

Scans only explicitly configured local roots; never launches, downloads, moves,
deletes or modifies model files. Existing profiles are left byte-for-byte intact.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fnmatch
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import tempfile

DEFAULT_ROOTS = ("/mnt/Games/AI/Censored", "/mnt/Games/AI/Uncensored")
IGNORED_DIRS = {".git", ".cache", "__pycache__", "node_modules", "venv",
                ".venv", "Comfyui", "ComfyUI", "comfyui"}
SPLIT_RE = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$", re.IGNORECASE)
QUANT_RE = re.compile(
    r"(?i)(?:^|[-_. ])(IQ[1-4]_[A-Z0-9_]+|Q[2-8]_(?:K(?:_[A-Z0-9]+)?|[A-Z0-9_]+)|BF16|F16|F32)(?=$|[-_. ])"
)


def roots_for(config: dict) -> list[Path]:
    """Keep the existing model_root and discover both station folders."""
    configured = config.get("model_roots")
    paths = list(configured) if isinstance(configured, list) else []
    paths += [config.get("model_root", ""), *DEFAULT_ROOTS]
    roots = []
    seen = set()
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser().resolve()
        if str(path) not in seen:
            roots.append(path)
            seen.add(str(path))
    return roots


def _is_projector(filename: str) -> bool:
    name = filename.lower()
    return ("mmproj" in name or "vision-tower" in name or
            name.startswith(("clip-", "clip_", "tokenizer-")))


def _model_files(root: Path):
    if not root.is_dir():
        return
    for current, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(f for f in folders
                            if f not in IGNORED_DIRS
                            and not (Path(current) / f).is_symlink())
        for filename in sorted(files):
            if not filename.lower().endswith(".gguf") or _is_projector(filename):
                continue
            split = SPLIT_RE.search(filename)
            if split and int(split.group(1)) != 1:
                continue  # llama.cpp opens the first shard, then loads the rest
            candidate = Path(current) / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                continue
            yield resolved


def _projector_for(model: Path, root: Path) -> Path | None:
    """Only pair a projector inside the same model-family directory."""
    relative = model.relative_to(root)
    family = root / relative.parts[0] if len(relative.parts) > 1 else model.parent
    matches = []
    for current, folders, files in os.walk(family, followlinks=False):
        folders[:] = [f for f in folders
                      if f not in IGNORED_DIRS and not (Path(current) / f).is_symlink()]
        for name in files:
            if name.lower().endswith(".gguf") and "mmproj" in name.lower():
                candidate = (Path(current) / name)
                if candidate.is_file() and not candidate.is_symlink():
                    matches.append(candidate.resolve())
    return matches[0] if len(matches) == 1 else None


def _slug(value: str) -> str:
    """Stable, valid <= 80-character alias; never produce an invalid ID."""
    raw = str(value)
    text = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "model"
    if len(text) > 72:
        # Keep a digest so paths sharing a long prefix remain distinguishable.
        text = text[:62].rstrip("-") + "-" + sha256(raw.encode("utf-8")).hexdigest()[:8]
    return text


def _unique_alias(value: str, used: set[str]) -> str:
    base = _slug(value)
    alias = base
    serial = 2
    while alias in used:
        suffix = f"-{serial}"
        alias = base[:80 - len(suffix)].rstrip("-") + suffix
        serial += 1
    if len(alias) > 80:
        raise AssertionError("Generated alias exceeds 80 characters")
    used.add(alias)
    return alias


def _quant(name: str) -> str:
    result = QUANT_RE.findall(Path(name).stem)
    return result[-1].upper() if result else ""


def _occupied(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.05):
            return True
    except OSError:
        return False


def _existing_paths(config: dict, discovered: list[tuple[Path, Path]]) -> set[Path]:
    """Handle old relative paths and uniquely matching legacy glob profiles."""
    found = set()
    base = Path(config.get("model_root") or DEFAULT_ROOTS[0]).expanduser()
    paths = [path for _, path in discovered]
    for profile in config.get("models", []):
        value = profile.get("path")
        if value:
            direct = Path(value).expanduser()
            if not direct.is_absolute():
                direct = base / direct
            if direct.is_file():
                found.add(direct.resolve())
            # A stale path remains in the original profile, never deleted.
            continue
        pattern = profile.get("match")
        if pattern and pattern != "*.gguf":
            candidates = [path for path in paths if fnmatch.fnmatch(path.name, pattern)]
            if len(candidates) == 1:
                found.add(candidates[0])
    return found


def plan_import(config: dict, roots=None) -> dict:
    """Return a preview and a new config. No filesystem writes or model execution."""
    if not isinstance(config, dict) or not isinstance(config.get("models"), list):
        raise ValueError("models.json: ожидается объект с массивом models")
    search_roots = roots_for(config) if roots is None else [
        Path(path).expanduser().resolve() for path in roots
    ]
    accessible = [root for root in search_roots if root.is_dir()]
    missing = [str(root) for root in search_roots if not root.is_dir()]
    discovered = []
    seen = set()
    for root in accessible:
        for model in _model_files(root):
            if model not in seen:
                discovered.append((root, model))
                seen.add(model)
    existing = _existing_paths(config, discovered)
    updated = copy.deepcopy(config)
    profiles = updated["models"]
    used_ids = {str(p.get("id", "")) for p in profiles}
    used_ports = {int(p.get("port", 8080)) for p in profiles
                  if str(p.get("port", 8080)).isdigit()}
    added = []
    skipped = []
    warnings = []

    for root, model in discovered:
        if model in existing:
            skipped.append(str(model))
            continue
        rel = model.relative_to(root)
        family = rel.parts[0] if len(rel.parts) > 1 else model.stem
        quant = _quant(model.name)
        category = root.name if root.name in ("Censored", "Uncensored") else root.name
        alias = _unique_alias(category + "-" + str(rel.with_suffix("")), used_ids)

        port = next((n for n in range(8081, 9000)
                     if n not in used_ports and not _occupied(n)), None)
        if port is None:
            raise RuntimeError("Нет доступных портов 8081–8999")
        used_ports.add(port)
        vision = bool(re.search(r"(?:^|[^a-z])(vl|vision)(?:[^a-z]|$)",
                                family.lower()))
        mmproj = _projector_for(model, root) if vision else None
        if vision and mmproj is None:
            warnings.append(f"{model.name}: mmproj не определён; проверь поддержку изображений")
        coding = any(word in family.lower() for word in ("coder", "devstral", "code"))
        profile = {
            "id": alias,
            "name": f"[{category}] {family}" + (f" · {quant}" if quant else ""),
            "purpose": f"Импортирован из {category}; параметры проверить перед запуском",
            "path": str(model),
            "match": "",
            "context": 32768,
            "port": port,
            "gpu": "",
            "ngl": 99,
            "parallel": 1,
            "batch": 1024,
            "ubatch": 256,
            "flash_attn": True,
            "no_kv_offload": True,
            "cache_type_k": "q8_0",
            "cache_type_v": "q8_0",
            "jinja": True,
            "reasoning_off": True,
            "thinking_off": False,
            "preferred_client": "opencode" if coding else "pi",
            "sampling": {"temp": .7, "top_p": .8, "top_k": 20,
                         "min_p": 0, "repeat_penalty": 1},
        }
        if mmproj:
            profile["mmproj"] = str(mmproj)
        profiles.append(profile)
        added.append(profile)
    return {
        "config": updated, "added": added, "existing": skipped,
        "found": len(discovered), "missing_roots": missing, "warnings": warnings
    }


def save_config(path: Path, config: dict) -> Path | None:
    """Atomic save with an unlimited timestamped backup; never remove old backups."""
    path = Path(path)
    if path.exists():
        directory = path.parent / "data" / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / ("models_import_" +
                              dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    else:
        backup = None
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".models-import-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GGUF catalog import (dry-run by default)")
    parser.add_argument("--apply", action="store_true", help="create backup and save new profiles")
    parser.add_argument("--root", action="append", help="override default scan roots; may repeat")
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "models.json")
    args = parser.parse_args(argv)
    source = args.config if args.config.is_file() else Path(__file__).parent / "models.example.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    report = plan_import(config, roots=args.root)
    print(f"GGUF: найдено {report['found']}, уже подключено {len(report['existing'])}, "
          f"новых профилей {len(report['added'])}")
    for model in report["added"]:
        print(f" + {model['id']} @:{model['port']} [{model['context']}] {model['path']}")
    for missing in report["missing_roots"]:
        print(" ! Нет каталога: " + missing)
    for warning in report["warnings"]:
        print(" ! " + warning)
    if args.apply and report["added"]:
        backup = save_config(args.config, report["config"])
        print(f"Сохранено: {args.config}")
        if backup:
            print(f"Резервная копия: {backup}")
    elif not args.apply:
        print("Пробный запуск: изменений нет. Для записи используй --apply.")
    else:
        print("Новых моделей нет, models.json не изменён.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
