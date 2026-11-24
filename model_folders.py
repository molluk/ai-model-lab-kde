"""Virtual model folders and per-column filters for AI Model Lab.

Folders are only labels in models.json: never rename or move GGUF files.
The module has no Qt dependency, and never writes user data by itself.
"""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path

UNFILED = "__ai_lab_unfiled__"
ALL_FOLDERS = "__ai_lab_all_folders__"
AUTOMATIC_FOLDERS = ("Censored", "Uncensored")
COLUMN_COUNT = 7


def check_folder(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Название папки должно быть строкой")
    value = name.strip()
    if (not value or len(value) > 64 or value in (UNFILED, ALL_FOLDERS)
            or any(ch in value for ch in "/\\\n\r\t\0")):
        raise ValueError("Название папки: от 1 до 64 символов, без /, \\ и переводов строк")
    return value


def effective_folder(profile: dict, config: dict) -> str:
    """Explicit virtual folders override inferred GGUF roots.

    For legacy profiles, infer Censored/Uncensored from path without touching
    local files. An explicit UNFILED marker is respected even for these roots.
    """
    if "folder" in profile:
        value = profile["folder"]
        if value == UNFILED:
            return UNFILED
        if isinstance(value, str) and value.strip():
            return value.strip()
    raw = str(profile.get("path") or "").strip()
    if raw:
        source = Path(raw).expanduser()
        if not source.is_absolute():
            source = Path(config.get("model_root") or "/mnt/Games/AI/Censored").expanduser() / source
        # Exact path components; 'Uncensored-demo' must not count as Uncensored.
        for folder in AUTOMATIC_FOLDERS:
            if folder in source.parts[:-1]:
                return folder
    display = str(profile.get("name") or "")
    for folder in AUTOMATIC_FOLDERS:
        if display.startswith(f"[{folder}]"):
            return folder
    return UNFILED


def list_folders(config: dict) -> list[str]:
    """Stable union of user-created, assigned and inferred folders."""
    names = set()
    for name in config.get("model_folders", []):
        if isinstance(name, str) and name.strip() and name not in (UNFILED, ALL_FOLDERS):
            names.add(name.strip())
    for profile in config.get("models", []):
        folder = effective_folder(profile, config)
        if folder != UNFILED:
            names.add(folder)
    return sorted(names, key=lambda name: (name.casefold(), name))


def folder_counts(config: dict) -> dict[str, int]:
    return dict(Counter(effective_folder(p, config) for p in config.get("models", [])))


def _find_name(config: dict, value: str) -> str | None:
    return next((name for name in list_folders(config)
                 if name.casefold() == value.casefold()), None)


def _copy(config):
    if not isinstance(config, dict) or not isinstance(config.get("models"), list):
        raise ValueError("Некорректная конфигурация моделей")
    return copy.deepcopy(config)


def create_folder(config: dict, name: str) -> dict:
    updated = _copy(config)
    name = check_folder(name)
    if _find_name(updated, name) is not None:
        raise ValueError("Папка с таким названием уже существует")
    updated["model_folders"] = list_folders(updated) + [name]
    return updated


def rename_folder(config: dict, old_name: str, new_name: str) -> dict:
    updated = _copy(config)
    old = _find_name(updated, old_name)
    if not old:
        raise ValueError("Исходная папка отсутствует")
    new = check_folder(new_name)
    existing = _find_name(updated, new)
    if existing and existing != old:
        raise ValueError("Папка с таким названием уже существует")
    if new == old:
        return updated
    # Make inferred members explicit so renaming Censored is permanent.
    for profile in updated["models"]:
        if effective_folder(profile, updated) == old:
            profile["folder"] = new
    updated["model_folders"] = [new if name == old else name
                                 for name in list_folders(config)]
    return updated


def delete_folder(config: dict, name: str) -> dict:
    updated = _copy(config)
    old = _find_name(updated, name)
    if not old:
        raise ValueError("Папка отсутствует")
    for profile in updated["models"]:
        if effective_folder(profile, updated) == old:
            profile["folder"] = UNFILED
    updated["model_folders"] = [f for f in list_folders(config) if f != old]
    return updated


def move_model(config: dict, alias: str, target_folder: str) -> dict:
    updated = _copy(config)
    if target_folder != UNFILED:
        folder = _find_name(updated, check_folder(target_folder))
        if folder is None:
            raise ValueError("Целевая папка отсутствует")
    else:
        folder = UNFILED
    matches = [p for p in updated["models"] if p.get("id") == alias]
    if len(matches) != 1:
        raise ValueError("Модель не найдена или её ID не уникален")
    matches[0]["folder"] = folder
    return updated


def matches_row(folder: str, chosen_folder: str | None,
                row_values: list[str], column_filters: list[str]) -> bool:
    """All active filters combine with AND; each column is independent."""
    if chosen_folder not in (None, ALL_FOLDERS) and folder != chosen_folder:
        return False
    if len(row_values) != COLUMN_COUNT or len(column_filters) != COLUMN_COUNT:
        raise ValueError("Для фильтрации нужны семь столбцов")
    return all(needle.strip().casefold() in str(value).casefold()
               for value, needle in zip(row_values, column_filters))
