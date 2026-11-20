"""Graceful, verified shutdown of AI Model Lab-owned processes.

Never terminates arbitrary processes found by name/port. All checks are
performed using the existing ownership checks in multi/core/custom_services.
"""
from __future__ import annotations

import shutil
import subprocess

import core
import multi
import custom_services


def _unit_active(name):
    if not shutil.which('systemctl'):
        return False
    unit = str(core.settings().get('webui_service', 'open-webui.service')).strip()
    if not unit:
        return False
    result = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit],
                            capture_output=True, timeout=8, check=False)
    return result.returncode == 0


def stop_all_managed():
    """Stop all confirmed managed model and service processes. Return a report.

    The caller must explicitly authorize this operation. Any failures leave the
    GUI open, so the user can inspect errors. External processes remain running.
    """
    completed = []
    failed = []
    external = []

    def attempt(label, stop, is_still_owned):
        try:
            message = stop()
            if is_still_owned():
                failed.append(f'{label}: процесс не остановлен ({message})')
            else:
                completed.append(label)
        except Exception as exc:
            failed.append(f'{label}: {type(exc).__name__}: {exc}')

    # Each independent llama.cpp server belongs to a single alias/port/PID.
    try:
        aliases = list(multi.active_instances())
    except Exception as exc:
        aliases = []
        failed.append(f'llama.cpp: не удалось прочитать список процессов: {exc}')
    for alias in aliases:
        attempt(f'llama.cpp / {alias}', lambda a=alias: multi.stop(a),
                lambda a=alias: bool(multi.inspect(a).get('managed') and multi.inspect(a).get('alive')))

    legacy = core.verified('llama')
    if legacy and legacy.get('alias') not in aliases:
        attempt('llama.cpp / legacy', lambda: core.stop('llama'),
                lambda: bool(core.verified('llama')))

    for key, label in [('office', 'Agent Office'), ('comfy', 'ComfyUI')]:
        if core.verified(key):
            attempt(label, lambda k=key: core.stop(k), lambda k=key: bool(core.verified(k)))

    # WebUI may be a verified Lab-owned CLI process or a configured systemd user
    # service. Port 3000 alone is never evidence of ownership.
    try:
        if core.verified('webui'):
            attempt('Open WebUI (managed CLI)', core.webui_stop,
                    lambda: bool(core.verified('webui')))
        elif _unit_active('webui'):
            attempt('Open WebUI (systemd --user)', core.webui_stop,
                    lambda: _unit_active('webui'))
        elif core.port_open(3000):
            external.append('Open WebUI / :3000 (неуправляемый процесс)')
    except Exception as exc:
        failed.append(f'Open WebUI: {type(exc).__name__}: {exc}')

    # Include orphan records for services removed from services.json while
    # still running, as long as their precise process identity is verified.
    ids = {p['id'] for p in custom_services.list_profiles()}
    if custom_services.STATE_DIR.is_dir():
        for path in custom_services.STATE_DIR.glob('*.json'):
            if custom_services.ID_PATTERN.fullmatch(path.stem):
                ids.add(path.stem)
    for ident in sorted(ids):
        try:
            if not custom_services.owned(custom_services._metadata(ident)):
                continue
        except Exception as exc:
            failed.append(f'Сервис {ident}: ошибка проверки PID: {exc}')
            continue
        attempt(f'Сервис / {ident}', lambda i=ident: custom_services.stop(i),
                lambda i=ident: custom_services.owned(custom_services._metadata(i)))

    # External/unowned services are never killed by this command.
    try:
        for alias, state in multi.all_states().items():
            if state.get('state') in ('external', 'port_conflict'):
                external.append(f'llama.cpp / {alias} (чужой процесс на порту {state.get("port")})')
        if core.port_open(8188) and not core.verified('comfy'):
            external.append('ComfyUI / :8188 (неуправляемый процесс)')
    except Exception:
        pass

    return {'success': not failed, 'stopped': completed, 'failed': failed,
            'external': sorted(set(external))}
