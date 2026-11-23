"""Resolve mutable state paths without changing the existing Linux layout."""
from __future__ import annotations

import os
from pathlib import Path


def user_root(resource_root: Path, *, platform_name: str | None = None,
              environ: dict | None = None, home: Path | None = None) -> Path:
    """Linux: installed app root. Windows: per-user LocalAppData.

    A frozen Windows executable may live under Program Files or PyInstaller's
    internal resources directory; neither should contain mutable user profiles.
    """
    platform_name = os.name if platform_name is None else platform_name
    if platform_name != 'nt':
        return Path(resource_root)
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    configured = env.get('LOCALAPPDATA')
    base = Path(configured) if configured else user_home / 'AppData' / 'Local'
    return base / 'AI-Model-Lab'
