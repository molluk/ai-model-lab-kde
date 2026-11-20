"""Multiple independent local llama.cpp instances, strictly owned by this application.

Each profile has its own localhost TCP port, CUDA_VISIBLE_DEVICES selection and PID
identity. Never terminate a process that fails the /proc identity checks.
"""
from __future__ import annotations
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time

import core

INSTANCES = core.DATA / 'instances'
_CHILDREN = {}  # Hold Popen handles until graceful shutdown; prevents zombies/warnings.


def validate_alias(alias):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', alias or ''):
        raise ValueError('ID/alias: латиница, цифры, точка, дефис и _ (до 80 символов)')
    return alias


def port_of(profile):
    port = int(profile.get('port', 8080))
    if not 1024 <= port <= 65535:
        raise ValueError('Порт должен быть 1024–65535')
    return port


def gpu_of(profile):
    """Empty means leave CUDA device selection to llama.cpp; UUID/index otherwise."""
    gpu = str(profile.get('gpu', '') or '').strip()
    if gpu and not re.fullmatch(r'(?:\d{1,3}|GPU-[A-Za-z0-9-]{10,80})', gpu):
        raise ValueError('GPU: индекс CUDA (0, 1…) либо полный UUID вида GPU-…')
    return gpu


def profile_by_id(alias):
    return core.model_by_id(alias)


def meta_path(alias):
    return INSTANCES / (validate_alias(alias) + '.json')


@contextlib.contextmanager
def locked():
    core.prepare()
    INSTANCES.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (INSTANCES / '.lock').open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def metadata(alias):
    return core.load_json(meta_path(alias), {}) or {}


def record(alias, **updates):
    with locked():
        prior = metadata(alias)
        prior.update(updates)
        prior['alias'] = alias
        core.atomic_json(meta_path(alias), prior)
    return prior


def owned(meta):
    try:
        pid = int(meta['pid'])
        if pid < 2 or int(meta.get('ticks', -1)) != core.start_ticks(pid):
            return False
        if str(Path('/proc') .joinpath(str(pid), 'exe').resolve()) != meta.get('exe'):
            return False
        raw = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        args = [x.decode(errors='replace') for x in raw if x]
        if '--alias' not in args or args[args.index('--alias') + 1] != meta['alias']:
            return False
        if '--port' not in args or int(args[args.index('--port') + 1]) != int(meta['port']):
            return False
        return True
    except (OSError, IndexError, KeyError, ValueError):
        return False


def inspect(alias):
    """Returns normalized state: unstarted/stopped/starting/running/error/external.

    Presence of an unrelated service on the configured port never grants ownership.
    """
    m = metadata(alias)
    p = profile_by_id(alias) or {'port': m.get('port', 8080)}
    port = int(m.get('port', port_of(p)))
    if owned(m):
        active = core.json_api(f'http://127.0.0.1:{port}/health', timeout=.3)
        running = isinstance(active, dict) and active.get('status') == 'ok'
        stage = 'running' if running else 'starting'
        return {**m, 'state': stage, 'managed': True, 'port': port, 'alive': True}
    # Legacy v3.1 server remains manageable, but isn't implicitly replaced.
    legacy = core.verified('llama')
    if legacy and legacy.get('alias') == alias:
        return {**legacy, 'state': 'running', 'managed': True, 'legacy': True,
                'port': 8080, 'alive': True}
    if m:
        stage = m.get('state', 'stopped')
        if stage in ('running', 'starting'):
            stage = 'error'  # unexpected death/stale process
        elif stage not in ('stopped', 'error'):
            stage = 'stopped'
    else:
        stage = 'unstarted'
    if core.port_open(port):
        if INSTANCES.is_dir():
            for file in INSTANCES.glob('*.json'):
                other = core.load_json(file, {}) or {}
                if other.get('alias') != alias and owned(other) and int(other.get('port',0)) == port:
                    return {**m, 'state':'port_conflict', 'other_alias':other['alias'], 'managed':False, 'port':port, 'alive':False}
        if legacy and legacy.get('alias') != alias and port == 8080:
            return {**m, 'state':'port_conflict', 'other_alias':legacy['alias'], 'managed':False, 'port':port, 'alive':False}
        return {**m, 'state': 'external', 'managed': False, 'port': port, 'alive': False}
    return {**m, 'state': stage, 'managed': False, 'port': port, 'alive': False}


def all_states():
    profiles = core.config().get('models', [])
    result = {p['id']: inspect(p['id']) for p in profiles}
    if INSTANCES.exists():
        for path in INSTANCES.glob('*.json'):
            alias = path.stem
            if alias not in result:
                result[alias] = inspect(alias)
    return result


def active_instances():
    return {k: v for k, v in all_states().items() if v.get('managed') and v.get('alive')}


def launch(alias):
    p = profile_by_id(alias)
    if not p:
        raise ValueError('Неизвестный профиль: ' + alias)
    port = port_of(p)
    gpu = gpu_of(p)
    cmd = core.server_command(p)
    core.prepare()
    with locked():
        prior = metadata(alias)
        if owned(prior) or (core.verified('llama') or {}).get('alias') == alias:
            raise RuntimeError('Экземпляр модели уже запущен')
        if core.port_open(port):
            raise RuntimeError(f'Порт {port} уже занят. Выбери другой порт в редакторе модели.')
        # Check every instance record to avoid starting a second owner for the same port.
        for rec in INSTANCES.glob('*.json'):
            other = core.load_json(rec, {}) or {}
            if rec.stem != alias and owned(other) and int(other.get('port', 0)) == port:
                raise RuntimeError(f'Порт {port} назначен работающему экземпляру {rec.stem}')
        log = core.LOGS / f'llama_{alias}_{dt.datetime.now():%Y%m%d_%H%M%S}.log'
        env = os.environ.copy()
        if gpu:
            env['CUDA_VISIBLE_DEVICES'] = gpu
        with log.open('ab', buffering=0) as stream:
            child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True, env=env)
        ticks = None
        for _ in range(200):
            if child.poll() is not None:
                break
            ticks = core.start_ticks(child.pid)
            if ticks is not None and 'llama-server' in core.cmdline(child.pid):
                break
            time.sleep(.02)
        if child.poll() is not None or ticks is None:
            raise RuntimeError(f'llama-server не запустился. Лог: {log}')
        meta = {'alias': alias, 'pid': child.pid, 'ticks': ticks,
                'exe': str(Path(f'/proc/{child.pid}/exe').resolve()),
                'gpu': gpu, 'port': port, 'context': int(p['context']),
                'log': str(log), 'state': 'starting', 'started_at': dt.datetime.now().isoformat()}
        core.atomic_json(meta_path(alias), meta)
        _CHILDREN[alias] = child
    for _ in range(180):
        if child.poll() is not None:
            record(alias, state='error', error='Процесс завершился при загрузке')
            raise RuntimeError(f'{alias}: процесс завершился; см. лог: {log}')
        h = core.json_api(f'http://127.0.0.1:{port}/health', timeout=.8)
        if isinstance(h, dict) and h.get('status') == 'ok':
            props = core.json_api(f'http://127.0.0.1:{port}/props', timeout=1.5) or {}
            if props.get('model_alias') != alias:
                record(alias, state='error', error='Не совпадает alias /props')
                raise RuntimeError('Несовпадение alias загруженной модели')
            record(alias, state='running', error='')
            return f'✅ {alias} работает: GPU={gpu or "авто"}, порт={port}, лог={log}'
        time.sleep(1)
    return f'{alias}: сервер ещё загружается; GPU={gpu or "авто"}, порт={port}; лог={log}'


def stop(alias):
    state = inspect(alias)
    if state.get('legacy'):
        return core.stop('llama')
    if not state.get('managed') or not state.get('alive'):
        return f'{alias}: управляемый запущенный процесс не обнаружен'
    pid = int(state['pid'])
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        record(alias, state='stopped')
        return f'{alias}: процесс уже завершился'
    for _ in range(60):
        if not owned(state):
            child=_CHILDREN.pop(alias, None)
            if child is not None:
                try: child.wait(timeout=.3)
                except subprocess.TimeoutExpired: pass
            record(alias, state='stopped', stopped_at=dt.datetime.now().isoformat())
            return f'{alias}: остановлен PID={pid}'
        time.sleep(.2)
    return f'{alias}: отправлен SIGTERM, процесс ещё работает; проверь статус'


def stop_all():
    result = []
    for alias, state in active_instances().items():
        result.append(stop(alias))
    return '\n'.join(result) if result else 'Работающих управляемых llama-server нет'


def log_path(alias):
    m = inspect(alias)
    path = m.get('log')
    if not path:
        matches = sorted(core.LOGS.glob(f'llama_{alias}_*.log'), key=lambda x: x.stat().st_mtime)
        return matches[-1] if matches else None
    return Path(path)


def available_gpu_ids():
    """Display hints; CUDA_VISIBLE_DEVICES may also accept a GPU UUID."""
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=index,name,uuid,memory.total',
                           '--format=csv,noheader'], capture_output=True, text=True, timeout=3)
        if r.returncode:
            return []
        return [v.strip() for v in r.stdout.splitlines() if v.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []
