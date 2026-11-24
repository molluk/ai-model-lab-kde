#!/usr/bin/env python3
"""Previewable, non-destructive cleanup and tuning for local GGUF profiles.

Only JSON profiles are changed after explicit approval; GGUF files and live
processes are never modified. An unmounted model directory is not a stale model.
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import json
from pathlib import Path
import re
import subprocess

import model_catalog
import multi

VRAM_GIB_FALLBACK = 22.0
LEGACY_PURPOSES = {
    "Android-архитектура и глубокий анализ кода",
    "Сравнение качества квантовки Q5",
    "Независимый Android-анализ и ревью",
    "Быстрые задачи программирования и патчи",
    "Экспериментальный Coder без фильтров",
    "Изображения, интерфейсы, дизайн",
    "Быстрое программирование и правки",
    "Example profile; specify actual GGUF path before launch",
}


def hardware_info():
    """Read-only nvidia-smi probe; only pin GPU when there is exactly one."""
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.total",
                               "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=3, check=True)
        cards = []
        for line in proc.stdout.splitlines():
            parts = [s.strip() for s in line.split(",")]
            if len(parts) == 2 and parts[0].startswith("GPU-"):
                cards.append((parts[0], float(parts[1]) / 1024))
        if len(cards) == 1:
            return {"uuid": cards[0][0], "vram_gib": cards[0][1]}
        if len(cards) > 1:
            return {"uuid": None, "vram_gib": VRAM_GIB_FALLBACK,
                    "warning": "Несколько NVIDIA GPU: привязку выбери вручную"}
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return {"uuid": None, "vram_gib": VRAM_GIB_FALLBACK,
            "warning": "nvidia-smi недоступна: профиль рассчитан для 22 ГБ VRAM"}


def _size_gib(path):
    """Include split GGUF siblings; an incomplete split must not be tuned."""
    match = model_catalog.SPLIT_RE.search(path.name)
    try:
        if match and int(match.group(1)) == 1:
            prefix, count = path.name[:match.start()], int(match.group(2))
            size = 0
            for part in range(1, count + 1):
                sibling = path.with_name(f"{prefix}-{part:05d}-of-{count:05d}.gguf")
                if not sibling.is_file():
                    return None
                size += sibling.stat().st_size
            return size / 1024**3
        return path.stat().st_size / 1024**3
    except OSError:
        return None


def _kind(profile, path):
    text = " ".join([str(profile.get("name", "")), str(profile.get("id", "")),
                     str(path.parent.name if path else ""),
                     str(path.name if path else "")]).lower()
    if re.search(r"qwen3[-_. ]?vl|(?:^|[-_ ])vision(?:[-_ ]|$)", text):
        return "vision"
    for part in ("devstral", "coder", "blend", "huihui", "turbo-fable", "unsloth",
                 "uncensored", "qwen"):
        if part in text:
            return part
    return "other"


def _quant(path):
    return model_catalog._quant(path.name) if path else ""


def _description(profile, path):
    kind = _kind(profile, path)
    quant = _quant(path)
    return {
        "vision": "Анализ скриншотов, UI и Android-дизайна",
        "devstral": "Программирование и быстрые правки Kotlin/Java",
        "coder": "Android-разработка: патчи и рефакторинг",
        "blend": "Android TV: архитектура, анализ и ревью",
        "huihui": "Эксперименты и альтернативный анализ",
        "turbo-fable": "Сравнительные тесты экспериментальной сборки",
        "unsloth": ("Android/Kotlin: детальный анализ и ревью"
                    if quant.upper().startswith("Q5") else
                    "Android/Kotlin: анализ и разработка"),
        "uncensored": "Эксперименты и сравнительные тесты",
        "qwen": "Универсальный анализ и ревью решений",
    }.get(kind, "Сравнительные тесты и общий анализ")


def _short_name(profile, path):
    if not path:
        return profile.get("name", "")
    kind = _kind(profile, path)
    families = {
        "vision": "Qwen3-VL 30B",
        "devstral": "Devstral Small 24B",
        "coder": "Qwen3-Coder 30B",
        "blend": "JetBrains Blend",
        "huihui": "Huihui Qwen3.8 27B",
        "turbo-fable": "Qwen3.8 Turbo-Fable",
        "unsloth": "Unsloth Qwen3.8 27B",
        "uncensored": "Qwen3.8 27B Uncensored",
        "qwen": "Qwen3.8 27B",
    }
    # Do not invent a model identity for unfamiliar families.
    if kind not in families:
        return profile.get("name", "")
    name = families[kind]
    quant = _quant(path)
    return f"{name} {quant}".strip()


def _is_imported(profile):
    return (str(profile.get("purpose", "")).startswith("Импортирован из ") or
            str(profile.get("name", "")).startswith(("[Censored]", "[Uncensored]")))


def _resolve(profile, config, roots, files):
    raw = str(profile.get("path") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_absolute():
            paths = [path]
        else:
            main = Path(config.get("model_root") or model_catalog.DEFAULT_ROOTS[0]).expanduser()
            paths = [main / path] + [root / path for root in roots]
        for p in paths:
            if p.is_file():
                return p.resolve(), "found"
        # Cannot claim missing when its configured storage volume is absent.
        expected_root = next((root for root in roots if root in path.parents), None)
        if expected_root is not None and not expected_root.is_dir():
            return None, "unmounted"
        if not path.is_absolute() and not any(root.is_dir() for root in roots):
            return None, "unmounted"
        return None, "missing"
    pattern = str(profile.get("match", "")).strip()
    if pattern and pattern != "*.gguf":
        matches = [p for p in files if fnmatch.fnmatch(p.name, pattern)]
        if len(matches) == 1:
            return matches[0], "found"
        return None, "ambiguous" if matches else "missing"
    return None, "ambiguous"


def _fix_mmproj(profile, path, roots):
    """Replace a broken/default projector only if exactly one local match exists."""
    if _kind(profile, path) != "vision":
        return profile, None
    current = str(profile.get("mmproj") or "").strip()
    if current and current != "replace-with-mmproj.gguf":
        candidate = Path(current).expanduser()
        if not candidate.is_absolute():
            candidate = path.parent / candidate
        if candidate.is_file():
            return profile, None
    root = next((r for r in roots if path.is_relative_to(r)), None)
    projector = model_catalog._projector_for(path, root) if root else None
    if projector:
        changed = copy.deepcopy(profile)
        changed["mmproj"] = str(projector)
        return changed, None
    return profile, "Нет однозначного mmproj; проверь проектор вручную"


def _tuned_preset(profile, path, hardware):
    updated = copy.deepcopy(profile)
    size = _size_gib(path)
    if size is None or size < .1:
        return None, "Размер GGUF не определён; автоподбор пропущен"
    vram = float(hardware.get("vram_gib") or VRAM_GIB_FALLBACK)
    # Disk size is only a proxy: kernel scratch, tensors and KV can change
    # real allocation. For larger weights, start with partial GPU offload.
    updated["context"] = 32768 if size <= 15 else 24576 if size <= 19 else 16384
    updated["ngl"] = 99 if size <= vram - 5 else 24 if size <= vram else 12
    updated["parallel"] = 1
    updated["batch"] = 512
    updated["ubatch"] = 128
    updated["flash_attn"] = True
    updated["no_kv_offload"] = True
    updated["cache_type_k"] = "q8_0"
    updated["cache_type_v"] = "q8_0"
    updated["jinja"] = True
    updated["reasoning_off"] = False
    updated["thinking_off"] = False
    if hardware.get("uuid") and not profile.get("gpu"):
        updated["gpu"] = hardware["uuid"]
    # Existing user-customized sampling remains unchanged.
    return updated, None


def plan_maintenance(config, *, roots=None, hardware=None):
    if not isinstance(config, dict) or not isinstance(config.get("models"), list):
        raise ValueError("models.json: отсутствует массив models")
    roots = ([Path(p).expanduser().resolve() for p in roots] if roots is not None
             else model_catalog.roots_for(config))
    files = sorted({p for root in roots if root.is_dir()
                    for p in model_catalog._model_files(root)})
    hw = hardware if hardware is not None else hardware_info()
    updated = copy.deepcopy(config)
    suggestions, changes, warnings, statuses = [], [], [], []
    # Repair legacy IDs produced by the old (88-char) importer. Do it in the
    # preview only; applying still needs an explicit confirmation and backup.
    # Reserve every original ID to avoid collisions with existing profiles.
    used_aliases = {str(p.get("id", "")) for p in updated["models"]}
    id_repairs = {}
    for profile in updated["models"]:
        old_id = profile.get("id")
        try:
            multi.validate_alias(old_id)
        except (ValueError, TypeError):
            new_id = model_catalog._unique_alias(
                str(old_id or profile.get("name") or "model"), used_aliases)
            id_repairs[new_id] = copy.deepcopy(profile)
            profile["id"] = new_id
            warnings.append(f"ID профиля {old_id!r} будет заменён на {new_id!r}")
    owner = {}
    kept = []
    if hw.get("warning"):
        warnings.append(hw["warning"])
    for profile in updated["models"]:
        alias = str(profile.get("id", ""))
        path, status = _resolve(profile, config, roots, files)
        statuses.append({"id": alias, "state": status, "path": str(path or "")})
        if path and path in owner:
            suggestions.append({"id": alias, "reason":
                                f"Дублирует GGUF профиля {owner[path]}", "type": "duplicate"})
            # Same GGUF can intentionally have different contexts and clients.
            kept.append(profile)
            continue
        if path:
            owner[path] = alias
        if status == "missing":
            suggestions.append({"id": alias, "reason": "Файл GGUF не найден", "type": "missing"})
            # Leave it unchanged unless user explicitly approves removal.
            kept.append(profile)
            continue
        if status == "unmounted":
            warnings.append(f"{alias}: путь не смонтирован — удалять профиль нельзя")
            kept.append(profile)
            continue
        if status == "ambiguous":
            warnings.append(f"{alias}: несколько GGUF или нет точного пути; требуется ручная проверка")
            kept.append(profile)
            continue
        before = copy.deepcopy(profile)
        profile, projector_error = _fix_mmproj(profile, path, roots)
        if projector_error:
            warnings.append(f"{alias}: {projector_error}")
        if str(profile.get("purpose", "")).startswith("Импортирован из ") or \
                profile.get("purpose") in LEGACY_PURPOSES:
            profile["purpose"] = _description(profile, path)
        if _is_imported(before):
            profile["name"] = _short_name(before, path)
            tuned, error = _tuned_preset(profile, path, hw)
            if tuned:
                profile = tuned
            if error:
                warnings.append(f"{alias}: {error}")
        if before != profile:
            changes.append({"id": alias, "before": before, "after": copy.deepcopy(profile)})
        kept.append(profile)

    # Duplicates and missing profiles remain until explicitly approved for removal.
    updated["models"] = kept
    # Present every alias repair as a single before/after edit, including
    # profiles with unmounted/missing GGUF which are otherwise left untouched.
    for alias, original in id_repairs.items():
        final = next((p for p in kept if p.get("id") == alias), None)
        if final is None:
            continue
        prior_change = next((x for x in changes if x.get("id") == alias), None)
        if prior_change is not None:
            prior_change["before"] = original
            prior_change["id"] = str(original.get("id"))
        else:
            changes.append({"id": str(original.get("id")),
                            "before": original, "after": copy.deepcopy(final)})
    return {"config": updated, "changes": changes, "suggested": suggestions,
            "warnings": warnings, "statuses": statuses,
            "found_files": len(files), "hardware": hw}


def apply_selection(report, *, remove_missing=False, remove_duplicates=False):
    """Remove candidates only after an explicit user selection."""
    config = copy.deepcopy(report["config"])
    types = set()
    if remove_missing:
        types.add("missing")
    if remove_duplicates:
        types.add("duplicate")
    ids = {item["id"] for item in report["suggested"] if item["type"] in types}
    config["models"] = [p for p in config["models"] if p.get("id") not in ids]
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description="Review/tune local GGUF profiles")
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "models.json")
    parser.add_argument("--root", action="append")
    parser.add_argument("--apply", action="store_true", help="save reviewed changes with backup")
    parser.add_argument("--remove-missing", action="store_true",
                        help="remove profiles whose GGUF is confirmed missing (requires --apply)")
    parser.add_argument("--remove-duplicates", action="store_true",
                        help="remove profiles pointing to the same GGUF (requires --apply)")
    args = parser.parse_args(argv)
    if (args.remove_missing or args.remove_duplicates) and not args.apply:
        parser.error("--remove-missing/--remove-duplicates require --apply")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = plan_maintenance(config, roots=args.root)
    print(f"GGUF: {report['found_files']} | изменяемых: {len(report['changes'])} | "
          f"к удалению (совпадение файла): "
          f"{sum(x['type']=='duplicate' for x in report['suggested'])}")
    for item in report["changes"]:
        p = item["after"]
        print(f" ✓ {item['id']}: {p.get('name')} | {p.get('purpose')} | "
              f"ctx={p.get('context')}, ngl={p.get('ngl')}")
    for item in report["suggested"]:
        print(f" ? {item['id']}: {item['reason']}")
    for warning in report["warnings"]:
        print(" ! " + warning)
    if not args.apply:
        print("Dry-run: ни одного файла не изменено. Для записи --apply.")
        return 0
    target = apply_selection(report, remove_missing=args.remove_missing,
                             remove_duplicates=args.remove_duplicates)
    if target == config:
        print("Нет изменений")
        return 0
    backup = model_catalog.save_config(args.config, target)
    print(f"Сохранено: {args.config}\nBackup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
