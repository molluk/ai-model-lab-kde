#!/usr/bin/env python3
"""Read-only inventory of GGUF/safetensors and AI Model Lab profiles.

No model launches, downloads, hashes of huge weights, or config writes.
Reads only directory entries, stat and the first four bytes of GGUF files.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fnmatch
import json
import os
from pathlib import Path
import re
import sys

import model_catalog

DEFAULT_ROOT = Path("/mnt/Games/AI")
DEFAULT_CONFIG = Path.home() / "AI/AI-Model-Lab/models.json"
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
WEIGHT_EXTENSIONS = {".gguf", ".safetensors"}
SPLIT = model_catalog.SPLIT_RE


def scan_weights(base: Path) -> dict:
    """Scan all immediate nested directories under Censored and Uncensored."""
    base = Path(base).expanduser()
    all_weights = []
    inaccessible = []
    symlinks = []
    roots = [base / "Censored", base / "Uncensored"]
    for root in roots:
        if not root.is_dir():
            inaccessible.append(str(root))
            continue
        def onerror(error):
            inaccessible.append(str(getattr(error, "filename", root)) + ": " + str(error))
        for current, folders, files in os.walk(root, followlinks=False, onerror=onerror):
            retained = []
            for name in sorted(folders):
                child = Path(current) / name
                if child.is_symlink():
                    symlinks.append(str(child))
                elif name not in IGNORED_DIRS:
                    retained.append(name)
            folders[:] = retained
            for filename in sorted(files):
                path = Path(current) / filename
                if path.suffix.lower() not in WEIGHT_EXTENSIONS:
                    continue
                if path.is_symlink():
                    symlinks.append(str(path))
                    continue
                try:
                    size = path.stat().st_size
                    if not path.is_file():
                        continue
                    magic = ""
                    if path.suffix.lower() == ".gguf":
                        with path.open("rb") as f:
                            magic = f.read(4).decode("ascii", "replace")
                except OSError as error:
                    inaccessible.append(str(path) + ": " + str(error))
                    continue
                all_weights.append({
                    "path": str(path.absolute()),
                    "file": path.name,
                    "directory": str(path.parent),
                    "root": root.name,
                    "bytes": size,
                    "extension": path.suffix.lower(),
                    "kind": ("projector" if model_catalog._is_projector(path.name)
                             else "model"),
                    "quant": model_catalog._quant(path.name),
                    "magic_ok": magic == "GGUF" if path.suffix.lower() == ".gguf" else None,
                })
    by_path = {str(Path(x["path"]).resolve()): x for x in all_weights}
    shard_groups = defaultdict(list)
    for row in all_weights:
        match = SPLIT.search(row["file"])
        if match:
            key = (row["directory"], row["file"][:match.start()], int(match.group(2)))
            shard_groups[key].append((int(match.group(1)), row))
    splits = []
    for (directory, prefix, count), found in sorted(shard_groups.items()):
        seen = {index for index, _ in found}
        expected = set(range(1, count + 1))
        splits.append({
            "name": prefix,
            "directory": directory,
            "expected": count,
            "found": len(seen & expected),
            "missing": sorted(expected - seen),
            "unexpected": sorted(seen - expected),
            "size_gib": round(sum(row["bytes"] for _, row in found) / 1024 ** 3, 3),
        })
    return {
        "base": str(base),
        "weights": all_weights,
        "by_path": by_path,
        "split_groups": splits,
        "missing_roots": inaccessible,
        "skipped_symlinks": symlinks,
    }


def analyze_profiles(config: dict, inventory: dict) -> dict:
    profiles = config.get("models", [])
    if not isinstance(profiles, list):
        raise ValueError("models.json: models должен быть массивом")
    model_root = Path(os.environ.get("AI_LAB_MODEL_ROOT") or
                      config.get("model_root") or str(DEFAULT_ROOT / "Censored")).expanduser()
    referenced = defaultdict(list)
    profile_rows = []
    physical_paths = {path for path, info in inventory["by_path"].items()
                      if info["extension"] == ".gguf" and info["kind"] == "model"}
    inventory_files = inventory["by_path"]
    for p in profiles:
        alias = str(p.get("id", ""))
        name = str(p.get("name", alias))
        raw_path = str(p.get("path") or "").strip()
        pattern = str(p.get("match") or "").strip()
        override = os.environ.get("AI_LAB_GGUF_" + alias.upper().replace("-", "_"))
        candidates = []
        location = None
        status = ""
        if override:
            location = Path(override).expanduser()
            if location.is_file():
                status = "OVERRIDE_OK"
                candidates = [location.resolve()]
            else:
                status = "OVERRIDE_MISSING"
        else:
            if raw_path:
                target = Path(raw_path).expanduser()
                if not target.is_absolute():
                    target = model_root / target
                if target.is_file():
                    status = "PATH_OK"
                    candidates = [target.resolve()]
                else:
                    status = "PATH_MISSING"
            if not candidates and pattern:
                matches = sorted(
                    path for path, info in inventory_files.items()
                    if (info["extension"] == ".gguf"
                        and fnmatch.fnmatch(info["file"], pattern)
                        and Path(path).is_relative_to(model_root.resolve())))
                if len(matches) == 1:
                    candidates = [Path(matches[0])]
                    status = "MATCH_OK"
                elif len(matches) > 1:
                    status = "MATCH_AMBIGUOUS"
                elif not raw_path:
                    status = "MATCH_MISSING"
            if not raw_path and not pattern:
                status = "NO_PATH_OR_PATTERN"
        if candidates:
            location = candidates[0]
            referenced[str(location)].append(alias)
            if str(location) not in inventory_files:
                status += "_OUTSIDE_SCAN"
        profile_rows.append({
            "id": alias, "name": name,
            "status": status, "resolved": str(location) if candidates else None,
            "path": raw_path, "match": pattern,
            "context": p.get("context"),
            "port": p.get("port"),
            "favorite": bool(p.get("favorite")),
            "id_valid": bool(re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", alias)),
        })
    orphan_files = sorted(physical_paths - set(referenced))
    duplicates = {path: ids for path, ids in referenced.items() if len(ids) > 1}
    invalid_gguf = sorted(x["path"] for x in inventory["weights"]
                          if x["extension"] == ".gguf" and not x["magic_ok"])
    ports = defaultdict(list)
    for row in profile_rows:
        if row["port"] is not None:
            ports[str(row["port"])].append(row["id"])
    return {
        "profiles": profile_rows, "unassigned_gguf": orphan_files,
        "shared_profile_files": duplicates,
        "shared_ports": {port: ids for port, ids in ports.items() if len(ids) > 1},
        "invalid_gguf_magic": invalid_gguf,
    }


def build_report(root: Path, config_file: Path) -> dict:
    inventory = scan_weights(root)
    data = None
    missing_config = None
    if config_file.is_file():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            missing_config = f"Не удалось прочитать models.json: {error}"
    else:
        missing_config = f"Нет models.json: {config_file}"
    compared = analyze_profiles(data, inventory) if isinstance(data, dict) else None
    inventory.pop("by_path")
    return {
        "source": str(root),
        "config": str(config_file),
        "config_error": missing_config,
        "inventory": inventory,
        "comparison": compared,
    }


def render_report(report: dict) -> str:
    inv = report["inventory"]
    compared = report["comparison"]
    weights = inv["weights"]
    grouped = Counter(row["root"] for row in weights if row["kind"] == "model"
                      and row["extension"] == ".gguf")
    lines = [
        "=== AI Model Lab · ПРОВЕРКА ЛОКАЛЬНЫХ МОДЕЛЕЙ (ТОЛЬКО ЧТЕНИЕ) ===",
        "Каталог: " + report["source"],
        "Конфигурация: " + report["config"],
        "GGUF-моделей / частей: " + str(sum(
            row["kind"] == "model" and row["extension"] == ".gguf"
            for row in weights)),
        "Censored: " + str(grouped["Censored"]) +
        " · Uncensored: " + str(grouped["Uncensored"]),
        "safetensors-файлов: " + str(sum(
            row["extension"] == ".safetensors" for row in weights)),
        "Проекторов/доп. GGUF: " + str(sum(
            row["kind"] == "projector" for row in weights)),
        "",
        "--- ФАЙЛЫ (размер и квантование — по имени и stat) ---",
    ]
    for row in weights:
        kind = "mmproj/aux" if row["kind"] == "projector" else row["extension"][1:]
        valid = "  !!! НЕ GGUF MAGIC" if row["magic_ok"] is False else ""
        lines.append(f"[{row['root']}] {row['bytes']/1024**3:.2f} GiB "
                     f"{kind} {row['quant'] or '-'}  {row['path']}{valid}")
    lines.append("\n--- МНОГОЧАСТНЫЕ GGUF ---")
    if not inv["split_groups"]:
        lines.append("(не обнаружены)")
    for part in inv["split_groups"]:
        lines.append(f"{part['name']}: {part['found']}/{part['expected']} частей "
                     f"({part['size_gib']} GiB), пропущены: {part['missing'] or 'нет'}"
                     f"  {part['directory']}")
    if inv["missing_roots"]:
        lines.append("\n--- НЕДОСТУПНЫЕ КАТАЛОГИ/ФАЙЛЫ ---")
        lines.extend("! " + row for row in inv["missing_roots"])
    if inv["skipped_symlinks"]:
        lines.append(f"Пропущено символических ссылок: {len(inv['skipped_symlinks'])}")
    if report["config_error"]:
        lines.append("! " + report["config_error"])
    if compared:
        lines.append("\n--- ПРОФИЛИ AI MODEL LAB ---")
        for row in compared["profiles"]:
            invalid = " [INVALID ID]" if not row["id_valid"] else ""
            fav = "★" if row["favorite"] else " "
            lines.append(f"{fav} {row['id']} {invalid} | {row['status']} | "
                         f"{row['name']} | {row['resolved'] or row['path'] or row['match'] or '-'}")
        lines.append("\n--- ФАЙЛЫ GGUF БЕЗ ПРОФИЛЯ ---")
        lines.extend(" + " + x for x in compared["unassigned_gguf"])
        if not compared["unassigned_gguf"]:
            lines.append("(нет)")
        lines.append("\n--- НЕОДНОЗНАЧНОСТИ / РИСКИ ---")
        if compared["shared_profile_files"]:
            for path, ids in compared["shared_profile_files"].items():
                lines.append(f"Один GGUF в нескольких профилях {ids}: {path}")
        if compared["shared_ports"]:
            for port, ids in compared["shared_ports"].items():
                lines.append(f"Одинаковый порт {port}: {ids}")
        for path in compared["invalid_gguf_magic"]:
            lines.append("Повреждён заголовок GGUF / не GGUF: " + path)
        bad = [p for p in compared["profiles"] if p["status"] not in
               ("PATH_OK", "MATCH_OK", "OVERRIDE_OK", "PATH_OK_OUTSIDE_SCAN",
                "MATCH_OK_OUTSIDE_SCAN", "OVERRIDE_OK_OUTSIDE_SCAN")]
        for p in bad:
            lines.append("Проверить профиль " + p["id"] + ": " + p["status"])
        if not (compared["shared_profile_files"] or compared["shared_ports"] or
                compared["invalid_gguf_magic"] or bad):
            lines.append("(предупреждений нет)")
    lines.append("\nФайлы моделей, профили и сервисы НЕ изменялись.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only model inventory")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="root that contains Censored and Uncensored")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--json", action="store_true",
                        help="print raw structured report as JSON")
    args = parser.parse_args(argv)
    report = build_report(args.root, args.config)
    print(json.dumps(report, ensure_ascii=False, indent=2)
          if args.json else render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
