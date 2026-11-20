"""Small, file-based user-interface localization layer for AI Model Lab.

The Russian text in gui.py is the source-language key. English (and future
languages) is provided in locales/<code>.json. No web services are used.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

_LOCALES = Path(__file__).resolve().parent / 'locales'
_language = 'ru'
_catalogs = {}


def available_languages():
    """List supported locales, reading names from UTF-8 JSON catalog files."""
    choices = [('ru', '🇷🇺 Русский')]
    if _LOCALES.is_dir():
        for path in sorted(_LOCALES.glob('*.json')):
            if path.stem == 'ru':
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                name = data.get('name')
                messages = data.get('translations')
                if isinstance(name, str) and isinstance(messages, dict):
                    choices.append((path.stem, name))
            except (ValueError, OSError):
                continue
    return choices


def set_language(language):
    global _language
    supported = {code for code, _ in available_languages()}
    _language = str(language) if language in supported else 'ru'
    return _language


def get_language():
    return _language


def _catalog(language):
    if language not in _catalogs:
        try:
            raw = json.loads((_LOCALES / f'{language}.json').read_text(encoding='utf-8'))
            _catalogs[language] = raw['translations']
        except (OSError, KeyError, ValueError):
            _catalogs[language] = {}
    return _catalogs[language]


def T(source):
    """Translate a UI string; preserve runtime aliases/paths in composite texts.

    Unknown strings stay in Russian rather than being passed to an external AI
    translator. Text with dynamic values receives known phrase substitutions.
    """
    if not isinstance(source, str) or _language == 'ru':
        return source
    table = _catalog(_language)
    if source in table:
        return table[source]
    # For interpolated messages, phrases are not known until runtime.
    # Only replace substantial phrases to avoid matching unrelated words.
    result = source
    for original, translated in sorted(table.items(), key=lambda kv: len(kv[0]), reverse=True):
        if len(original) >= 4 and original in result:
            # Never translate a fragment of a longer Russian word.
            boundary = r'(?<![\w])' + re.escape(original) + r'(?![\w])'
            result = re.sub(boundary, lambda _match: translated, result)
    return result
