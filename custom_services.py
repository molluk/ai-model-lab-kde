"""User-defined local background services for AI Model Lab.

Commands are argv arrays (never shell commands); managed processes are identified
by PID + Linux /proc start ticks + executable + full argv before any stop.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import time
from urllib.parse import urlparse

import core

FILE = core.USER_ROOT / 'services.json'
STATE_DIR = core.DATA / 'custom_services'
_CHILDREN = {}  # Preserve Popen handles until stopped; no zombie warnings in active GUI.
RESERVED = {'llama', 'webui', 'office', 'comfy'}
ID_PATTERN = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z')


def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError('Service must be a JSON object')
    ident = str(profile.get('id', '')).strip()
    if not ID_PATTERN.fullmatch(ident) or ident in RESERVED:
        raise ValueError('Service ID: 1–64 ASCII letters, digits, _ or -, not a reserved ID')
    name = str(profile.get('name', '')).strip()
    if not name or len(name) > 100:
        raise ValueError('Service name required (max 100 characters)')
    command = profile.get('command')
    if isinstance(command, str):
        command = shlex.split(command)
    if not isinstance(command, list) or not command or any(not isinstance(v, str) or not v for v in command):
        raise ValueError('Command must be a nonempty argv list or shell-quoted string')
    if len(command) > 100 or sum(len(x) for x in command) > 10000:
        raise ValueError('Command is too long')
    directory = str(profile.get('cwd', '') or '').strip()
    if '\x00' in directory or '\n' in directory:
        raise ValueError('Invalid directory')
    for field in ('health_url', 'open_url'):
        value = str(profile.get(field, '') or '').strip()
        if value:
            u = urlparse(value)
            if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
                raise ValueError(f'Invalid {field}: HTTP(S) URL required')
            if field == 'health_url' and u.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('Health probes may only target local loopback HTTP(S) endpoints')
    return {
        'id': ident,
        'name': name,
        'command': command,
        'cwd': directory,
        'health_url': str(profile.get('health_url', '') or '').strip(),
        'open_url': str(profile.get('open_url', '') or '').strip(),
    }


def list_profiles():
    loaded = core.load_json(FILE, {'services': []})
    if not isinstance(loaded, dict) or not isinstance(loaded.get('services'), list):
        return []
    profiles = []
    for entry in loaded['services']:
        try:
            profiles.append(validate(entry))
        except (ValueError, TypeError):
            continue
    return profiles


def save_profiles(profiles):
    result = [validate(p) for p in profiles]
    ids = [x['id'] for x in result]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate service ID')
    core.atomic_json(FILE, {'version': 1, 'services': result})


def profile_of(ident):
    return next((p for p in list_profiles() if p['id'] == ident), None)


def meta_path(ident):
    if not ID_PATTERN.fullmatch(ident or ''):
        raise ValueError('Invalid service ID')
    return STATE_DIR / (ident + '.json')


def _metadata(ident):
    return core.load_json(meta_path(ident), {}) or {}


def owned(meta):
    try:
        pid = int(meta['pid'])
        if pid < 2 or core.start_ticks(pid) != int(meta['ticks']):
            return False
        exe = str(Path(f'/proc/{pid}/exe').resolve())
        if exe != meta['exe']:
            return False
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        argv = [v.decode(errors='replace') for v in cmd if v]
        expected = meta['argv']
        # Resolve argv[0] vs executable; other arguments must be identical.
        return bool(argv) and argv[1:] == expected[1:] and (argv[0] == expected[0] or Path(argv[0]).name == Path(expected[0]).name)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _local_probe(url):
    if not url:
        return None
    from urllib.request import build_opener, HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        opener = build_opener(NoRedirect)
        with opener.open(url, timeout=.35) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def inspect(ident):
    profile = profile_of(ident)
    meta = _metadata(ident)
    if owned(meta):
        url = (profile or {}).get('health_url', '') or meta.get('health_url', '')
        ready = _local_probe(url)
        return {**meta, 'state': 'running' if ready is not False else 'starting', 'managed': True}
    if meta and meta.get('state') in ('running', 'starting'):
        return {**meta, 'state': 'error', 'managed': False}
    return {**meta, 'state': meta.get('state', 'stopped'), 'managed': False}


def _expand_command(profile):
    argv = [os.path.expandvars(os.path.expanduser(part)) for part in profile['command']]
    cwd = Path(os.path.expandvars(os.path.expanduser(profile['cwd']))) if profile['cwd'] else Path.home()
    if not cwd.is_dir():
        raise FileNotFoundError(f'Working directory not found: {cwd}')
    executable = argv[0]
    if '/' in executable:
        binary = Path(executable)
        if not binary.is_file():
            raise FileNotFoundError(f'Executable not found: {binary}')
    else:
        import shutil
        if not shutil.which(executable):
            raise FileNotFoundError(f'Command not installed: {executable}')
    return argv, cwd


def start(ident):
    p = profile_of(ident)
    if not p:
        raise ValueError('Unknown user service')
    if inspect(ident)['managed']:
        raise RuntimeError('Service already running')
    argv, cwd = _expand_command(p)
    core.prepare()
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = core.LOGS / f'custom_{ident}_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.log'
    with log.open('ab', buffering=0) as stream:
        proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
    ticks = None
    for _ in range(150):
        if proc.poll() is not None:
            break
        ticks = core.start_ticks(proc.pid)
        if ticks is not None:
            raw = Path(f'/proc/{proc.pid}/cmdline').read_bytes().split(b'\0')
            current = [v.decode(errors='replace') for v in raw if v]
            if current and current[1:] == argv[1:] and (current[0] == argv[0] or Path(current[0]).name == Path(argv[0]).name):
                break
        time.sleep(.025)
    if proc.poll() is not None or ticks is None:
        raise RuntimeError(f'Service exited on start; see {log}')
    actual = Path(f'/proc/{proc.pid}/exe').resolve()
    cmd = Path(f'/proc/{proc.pid}/cmdline').read_bytes().split(b'\0')
    running_argv = [v.decode(errors='replace') for v in cmd if v]
    metadata = {'pid': proc.pid, 'ticks': ticks, 'exe': str(actual),
                'argv': running_argv, 'state': 'starting', 'health_url': p['health_url'],
                'log': str(log), 'started_at': dt.datetime.now().isoformat()}
    core.atomic_json(meta_path(ident), metadata)
    _CHILDREN[ident] = proc
    if p['health_url']:
        for _ in range(20):
            if proc.poll() is not None:
                metadata['state'] = 'error'; core.atomic_json(meta_path(ident), metadata)
                raise RuntimeError(f'Service exited during startup; see {log}')
            if _local_probe(p['health_url']):
                break
            time.sleep(.35)
    metadata['state'] = 'running' if owned(metadata) else 'error'
    core.atomic_json(meta_path(ident), metadata)
    return f"{p['name']}: {metadata['state']} (PID {proc.pid}); log: {log}"


def stop(ident):
    meta = _metadata(ident)
    if not owned(meta):
        return f'{ident}: no confirmed managed process; nothing stopped'
    pid = int(meta['pid'])
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not owned(meta):
            break
        time.sleep(.1)
    # Never SIGKILL / pkill. Mark stopped only after verified process ended.
    if not owned(meta):
        child = _CHILDREN.pop(ident, None)
        if child is not None:
            try:
                child.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                pass
        meta['state'] = 'stopped'
        meta['stopped_at'] = dt.datetime.now().isoformat()
        core.atomic_json(meta_path(ident), meta)
        return f'{ident}: stopped PID {pid}'
    return f'{ident}: SIGTERM sent, still running; check status'


def active_log_paths():
    result = []
    for p in list_profiles():
        meta = _metadata(p['id'])
        if owned(meta) and meta.get('log'):
            result.append(meta['log'])
    return result
