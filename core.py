#!/usr/bin/env python3
"""Local service controller, stdlib only. Never kills processes by name."""
from __future__ import annotations
import datetime as dt
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.request

import platform_paths

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
# Preserve the existing Linux layout; Windows keeps all mutable data out of
# bundled code and Program Files.
USER_ROOT = platform_paths.user_root(ROOT)
DATA = USER_ROOT / 'data'
LOGS = DATA / 'logs'
REPORTS = DATA / 'reports'
MODELS = USER_ROOT / 'models.json'
SETTINGS = USER_ROOT / 'settings.json'


def prepare():
    for path in (USER_ROOT, DATA, LOGS, REPORTS):
        path.mkdir(parents=True, exist_ok=True)
        try: path.chmod(0o700)
        except OSError: pass


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def atomic_json(path, data):
    prepare()
    path = Path(path)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    with temp.open('w', encoding='utf-8') as out:
        os.chmod(temp, 0o600)
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write('\n')
    os.replace(temp, path)


def config():
    source = MODELS if MODELS.is_file() else ROOT / 'models.example.json'
    return load_json(source, {})


def settings():
    source = SETTINGS if SETTINGS.is_file() else ROOT / 'settings.example.json'
    return load_json(source, {})


def model_by_id(alias):
    return next((p for p in config().get('models', []) if p.get('id') == alias), None)


def model_root():
    return Path(os.environ.get('AI_LAB_MODEL_ROOT', config().get('model_root', '/mnt/Games/AI/Censored'))).expanduser()


def resolve_gguf(profile):
    root = model_root()
    override = os.environ.get('AI_LAB_GGUF_' + profile['id'].upper().replace('-', '_'))
    if override:
        target = Path(override).expanduser()
        if not target.is_file(): raise FileNotFoundError(str(target))
        return target.resolve()
    if profile.get('path'):
        path = root / profile['path']
        if path.is_file(): return path.resolve()
    pattern = profile.get('match', '')
    found = [p.resolve() for p in root.rglob('*.gguf') if fnmatch.fnmatch(p.name, pattern)] if root.is_dir() and pattern else []
    if len(found) != 1:
        raise RuntimeError(f"{profile['id']}: найдено {len(found)} файлов по шаблону {pattern}. Укажи точный путь в models.json")
    return found[0]


def server_exe():
    return Path(config().get('server_bin', '~/llama.cpp/build/bin/llama-server')).expanduser().resolve()


def server_command(profile):
    """Build one model server command. GPU affinity is handled in multi.launch env."""
    import shlex
    exe = server_exe()
    if not exe.is_file():
        raise FileNotFoundError(f'Не найден llama-server: {exe}')
    gguf = resolve_gguf(profile)
    context = int(profile['context'])
    if not 4096 <= context <= 524288:
        raise ValueError('Недопустимый context')
    port = int(profile.get('port', 8080))
    if not 1024 <= port <= 65535:
        raise ValueError('Недопустимый порт')
    parallel = int(profile.get('parallel', 1))
    batch = int(profile.get('batch', 1024))
    ubatch = int(profile.get('ubatch', 256))
    ngl = int(profile.get('ngl', 99))
    if not (1 <= parallel <= 64 and 1 <= ubatch <= batch <= 65536 and 0 <= ngl <= 999):
        raise ValueError('Неверные параметры batch/ubatch/parallel/ngl')
    cache_k = str(profile.get('cache_type_k', 'q8_0'))
    cache_v = str(profile.get('cache_type_v', 'q8_0'))
    allowed_cache = {'f16', 'q8_0', 'q4_0', 'q4_1', 'q5_0', 'q5_1', 'iq4_nl'}
    if cache_k not in allowed_cache or cache_v not in allowed_cache:
        raise ValueError('Неверный тип KV cache')
    args = [str(exe), '-m', str(gguf), '-ngl', str(ngl), '-c', str(context),
            '-np', str(parallel), '-b', str(batch), '-ub', str(ubatch)]
    if profile.get('flash_attn', True):
        args += ['-fa', 'on']
    if profile.get('no_kv_offload', True):
        args += ['--no-kv-offload']
    args += ['--cache-type-k', cache_k, '--cache-type-v', cache_v]
    if profile.get('jinja', True):
        args.append('--jinja')
    if profile.get('reasoning_off', True):
        args += ['--reasoning', 'off']
    if profile.get('n_cpu_moe'):
        args += ['--n-cpu-moe', str(int(profile['n_cpu_moe']))]
    if profile.get('mmproj'):
        mm = model_root() / profile['mmproj']
        if not mm.is_file():
            raise FileNotFoundError('Не найден mmproj: ' + str(mm))
        args += ['--mmproj', str(mm)]
    if profile.get('image_min_tokens'):
        args += ['--image-min-tokens', str(int(profile['image_min_tokens']))]
    if profile.get('thinking_off'):
        args += ['--chat-template-kwargs', '{"enable_thinking":false}']
    sampling = {'temp': .7, 'top_p': .8, 'top_k': 20, 'min_p': 0, 'repeat_penalty': 1}
    sampling.update(profile.get('sampling', {}))
    for name, flag in [('temp', '--temp'), ('top_p', '--top-p'), ('top_k', '--top-k'),
                       ('min_p', '--min-p'), ('repeat_penalty', '--repeat-penalty')]:
        args += [flag, str(sampling[name])]
    extra = profile.get('extra_args', [])
    if isinstance(extra, str):
        extra = shlex.split(extra)
    if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
        raise ValueError('extra_args должен быть строкой командных аргументов или списком')
    reserved = {'-m', '--model', '--model-path', '-c', '--ctx-size', '--port', '--host',
                '--alias', '-ngl', '--n-gpu-layers'}
    if any(x.split('=', 1)[0] in reserved for x in extra):
        raise ValueError('Переопределять model/context/host/port/alias/ngl через extra_args нельзя')
    args += extra
    args += ['--metrics', '--host', '127.0.0.1', '--port', str(port), '--alias', profile['id']]
    return args


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), .25): return True
    except OSError: return False


def json_api(url, data=None, timeout=1.5):
    try:
        encoded = json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(url, data=encoded, headers={'Content-Type':'application/json'} if encoded else {}), timeout=timeout) as r:
            return json.load(r)
    except (OSError, ValueError): return None


def start_ticks(pid):
    try: return int(Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[19])
    except (ValueError, OSError, IndexError): return None


def cmdline(pid):
    try: return Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
    except OSError: return ''


def pid_file(name):
    return DATA / f'{name}.json'


def verified(name):
    meta = load_json(pid_file(name))
    if not isinstance(meta, dict) or meta.get('service') != name: return None
    try:
        pid = int(meta['pid'])
        if pid < 2 or start_ticks(pid) != int(meta['ticks']): return None
        exe = str(Path(f'/proc/{pid}/exe').resolve())
        if exe != meta.get('exe'): return None
        command = cmdline(pid)
        if name == 'llama' and '--alias ' + str(meta.get('alias')) not in command: return None
        if name == 'office' and 'run.py' not in command: return None
        if name == 'comfy' and 'main.py' not in command: return None
        return meta
    except (OSError, ValueError, KeyError): return None


def spawn(name, args, cwd=None, **extra):
    prepare()
    log = LOGS / f'{name}_{dt.datetime.now():%Y%m%d_%H%M%S}.log'
    with log.open('ab', buffering=0) as out:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             cwd=str(cwd or HOME), start_new_session=True)
    ticks=None
    # The child may still be between fork() and execve(): wait until its
    # expected argv actually appears, avoiding a stale /proc/exe identity.
    match_arg = {'llama':'llama-server', 'office':'run.py', 'comfy':'main.py'}.get(name,name)
    for i in range(100):
        if p.poll() is not None: break
        ticks = start_ticks(p.pid)
        if ticks is not None and match_arg in cmdline(p.pid): break
        time.sleep(.03)
    else:
        ticks=None
    if ticks is None or p.poll() is not None:
        raise RuntimeError(f'{name}: процесс завершился или PID недоступен; см. {log}')
    exe = str(Path(f'/proc/{p.pid}/exe').resolve())
    atomic_json(pid_file(name), {'service':name,'pid':p.pid,'ticks':ticks,'exe':exe,'log':str(log),**extra})
    return p, log


def stop(name):
    meta = verified(name)
    if not meta: return f'{name}: подтверждённого управляемого процесса нет'
    pid = int(meta['pid'])
    # Every Lab-managed server is created using start_new_session=True.
    # If it still leads its own session/process group, stop only that owned
    # group (including child workers), never use pkill or broad name matches.
    try:
        if os.getpgid(pid) == pid and name in ('office','comfy','webui'):
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file(name).unlink(missing_ok=True)
        return f'{name}: процесс уже завершился'
    # Never SIGKILL or kill by pattern; only confirmed owner, allow graceful shutdown.
    for i in range(30):
        if not verified(name):
            pid_file(name).unlink(missing_ok=True)
            return f'{name}: остановлен (PID {pid})'
        time.sleep(.2)
    return f'{name}: SIGTERM отправлен, процесс ещё работает. Повторно проверь статус.'


def start_model(alias):
    profile = model_by_id(alias)
    if not profile: raise ValueError('Неизвестная модель: ' + alias)
    current = verified('llama')
    if current: raise RuntimeError(f"Сначала останови управляемый llama: {current.get('alias')}")
    if port_open(8080): raise RuntimeError('Порт 8080 занят другим сервером. Не останавливаю его автоматически.')
    args = server_command(profile)
    p, log = spawn('llama', args, alias=alias, context=profile['context'])
    # Async GUI worker; timeout not too optimistic for slow model load.
    for i in range(180):
        if p.poll() is not None: raise RuntimeError(f'Модель завершилась; журнал: {log}')
        health = json_api('http://127.0.0.1:8080/health', timeout=.7)
        if health and health.get('status') == 'ok':
            props = json_api('http://127.0.0.1:8080/props') or {}
            if props.get('model_alias') and props['model_alias'] != alias:
                raise RuntimeError('Неправильный alias на порту 8080; проверь сервер.')
            return f'✅ {profile["name"]}: готова, контекст {profile["context"]}; лог: {log}'
        time.sleep(1)
    return f'Запуск {alias} продолжается (тайм-аут проверки готовности). Лог: {log}'


def _webui_cli():
    """Return an existing local Open WebUI entry point without downloading anything."""
    candidates = [
        shutil.which('open-webui'),
        HOME / '.local/bin/open-webui',
        HOME / '.local/share/uv/tools/open-webui/bin/open-webui',
    ]
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    return None


def webui_start():
    if verified('webui'):
        return 'Open WebUI уже работает как управляемый процесс'
    if port_open(3000):
        return 'Open WebUI уже отвечает на порту 3000 (чужой процесс не перехватывается)'
    service = settings().get('webui_service', 'open-webui.service')
    error = ''
    if shutil.which('systemctl'):
        try:
            proc = subprocess.run(['systemctl','--user','start',service],
                                  capture_output=True,text=True,timeout=30)
            if proc.returncode == 0:
                return f'WebUI: служба {service} запущена'
            error = proc.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            error = str(exc)
    cli = _webui_cli()
    if not cli:
        raise RuntimeError(
            'Не найдены работающая служба systemd --user и исполняемый open-webui. '
            'Установи Open WebUI или укажи действующую службу. '
            'Инструкция: https://docs.openwebui.com/getting-started/quick-start/ '
            + (f'Причина: {error}' if error else '')
        )
    proc, log = spawn('webui', [cli, 'serve', '--host', '127.0.0.1', '--port', '3000'], cwd=HOME)
    if proc.poll() is not None:
        raise RuntimeError(f'Open WebUI немедленно завершился; журнал: {log}')
    return f'Open WebUI запускается как отдельный процесс (PID {proc.pid}); журнал: {log}'


def webui_stop():
    if verified('webui'):
        return stop('webui')
    if not shutil.which('systemctl'):
        return 'WebUI: systemctl отсутствует; чужие процессы не остановлены'
    service = settings().get('webui_service', 'open-webui.service')
    active = subprocess.run(['systemctl','--user','is-active','--quiet',service],
                            capture_output=True, timeout=6)
    if active.returncode != 0:
        return 'WebUI: управляемой активной службы нет; чужие процессы не остановлены'
    proc = subprocess.run(['systemctl','--user','stop',service],
                          capture_output=True,text=True,timeout=30)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or 'Ошибка остановки WebUI')
    return f'WebUI: остановлена служба {service}; сторонние процессы не тронуты'


def office_path():
    return Path(settings().get('office_dir', '~/AI/agent-office')).expanduser()


def office_start():
    if verified('office'): return 'Agent Office уже запущен через AI Lab'
    directory = office_path()
    legacy_pidfile=HOME/'.local/state/agent-office.pid'
    try:
        legacy_pid=int(legacy_pidfile.read_text().strip())
        if legacy_pid>1 and 'run.py' in cmdline(legacy_pid) and Path(f'/proc/{legacy_pid}/cwd').resolve()==directory.resolve():
            return 'Agent Office уже работает (запущен старым лаунчером). AI Lab не перехватывает чужой PID.'
    except (OSError, ValueError): pass
    if not (directory/'run.py').is_file(): raise FileNotFoundError(f'Нет Agent Office run.py: {directory}')
    py = shutil.which('python3') or '/usr/bin/python3'
    proc, log = spawn('office', [py,'run.py'], cwd=directory)
    time.sleep(1.2)
    if proc.poll() is not None: raise RuntimeError(f'Agent Office завершился; журнал: {log}')
    return f'Agent Office: запущен, PID {proc.pid}; журнал: {log}'


def comfy_path():
    chosen = Path(settings().get('comfy_dir','~/AI/ComfyUI')).expanduser()
    for d in (chosen, HOME/'AI/ComfyUI', Path('/mnt/Games/AI/Censored/Comfyui'), Path('/mnt/Games/AI/Censored/ComfyUI')):
        if (d/'main.py').is_file(): return d
    raise FileNotFoundError('ComfyUI main.py не найден; укажи директорию в настройках')


def comfy_start():
    if verified('comfy'): return 'ComfyUI уже запущен через AI Lab'
    if port_open(8188): raise RuntimeError('Порт 8188 занят другим экземпляром; не запускаю второй')
    folder = comfy_path()
    py = folder/'venv/bin/python'
    if not py.is_file(): raise FileNotFoundError(f'Нет виртуального окружения ComfyUI: {py}')
    proc, log = spawn('comfy',[str(py),'main.py','--listen','127.0.0.1','--port','8188'],cwd=folder)
    time.sleep(1.2)
    if proc.poll() is not None: raise RuntimeError(f'ComfyUI завершился; журнал: {log}')
    return f'ComfyUI: запущен, PID {proc.pid}; журнал: {log}'


def office_url():
    url = settings().get('office_url', '')
    if url.startswith(('http://127.0.0.1:', 'http://localhost:')): return url
    meta = verified('office')
    if meta:
        try: text = Path(meta['log']).read_text(errors='replace')[-24000:]
        except OSError: return ''
        ports = re.findall(r'(?:127\.0\.0\.1|0\.0\.0\.0|localhost):(\d{2,5})', text)
        for port in reversed(ports):
            if int(port) not in (8080,3000,8188) and port_open(int(port)):
                return 'http://127.0.0.1:' + port
    return ''


def get_status():
    props = json_api('http://127.0.0.1:8080/props', timeout=.6) or {}
    ctx = (props.get('default_generation_settings') or {}).get('n_ctx') or props.get('n_ctx')
    office_meta = verified('office')
    return {
        'llama': bool(verified('llama')), 'llama_external': port_open(8080) and not bool(verified('llama')),
        'alias': props.get('model_alias') or (verified('llama') or {}).get('alias') or '', 'ctx':ctx,
        'webui': port_open(3000), 'office':bool(office_meta), 'comfy':port_open(8188),
        'office_url':office_url() if office_meta else (settings().get('office_url') or '')}


def gpu_metrics(gpu_index=None):
    cmd = shutil.which('nvidia-smi')
    if not cmd: return {}
    try:
        index = str(gpu_index if gpu_index is not None and str(gpu_index).strip() else settings().get('gpu_index',0))
        r = subprocess.run([cmd,'--id='+index,'--query-gpu=utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
        if r.returncode != 0: return {}
        values = [float(x.strip()) for x in r.stdout.splitlines()[0].split(',')]
        if len(values)!=5: return {}
        return dict(zip(('gpu','vram','vram_total','power','temp'), values))
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired): return {}


def ram_metrics():
    try:
        lines = Path('/proc/meminfo').read_text().splitlines()
        mem = {k.strip():int(v.strip().split()[0])/(1024**2) for k,v in (l.split(':',1) for l in lines) if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}
        return {'ram':mem['MemTotal']-mem['MemAvailable'],'ram_total':mem['MemTotal'],
                'swap':mem['SwapTotal']-mem['SwapFree']}
    except (OSError,ValueError,KeyError): return {}


def pi_config_for(alias):
    pi = load_json(HOME/'.pi/agent/models.json', {})
    return next((x for x in pi.get('providers',{}).get('local-lab',{}).get('models',[]) if x.get('id')==alias), None)


def preflight_android():
    state = get_status()
    if not state.get('alias'): raise RuntimeError('Запусти модель на порту 8080 до начала теста')
    pi = pi_config_for(state['alias'])
    if not pi: raise RuntimeError(f"Модель {state['alias']} отсутствует в Pi local-lab")
    if not isinstance(state.get('ctx'),int): raise RuntimeError('Сервер не сообщает n_ctx')
    if int(pi.get('contextWindow',0)) != int(state['ctx']):
        raise RuntimeError(f"Контекст Pi {pi.get('contextWindow')} не равен серверу {state['ctx']}")
    if int(pi.get('maxTokens',0)) < 512: raise RuntimeError('Слишком мал maxTokens в Pi')
    return state


def discover():
    root=model_root()
    if not root.is_dir(): return []
    return sorted(str(p) for p in root.rglob('*.gguf') if 'mmproj' not in p.name.lower())


def all_gpu_metrics():
    """Query every NVIDIA GPU without assuming there is only one card."""
    cmd = shutil.which('nvidia-smi')
    if not cmd: return []
    try:
        r = subprocess.run([cmd, '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu',
                            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
        if r.returncode: return []
        results=[]
        for line in r.stdout.splitlines():
            values=[x.strip() for x in line.split(',')]
            if len(values)!=7: continue
            try:
                results.append(dict(index=int(values[0]),name=values[1],gpu=float(values[2]),
                                    vram=float(values[3]),vram_total=float(values[4]),
                                    power=float(values[5]),temp=float(values[6])))
            except ValueError:
                continue
        return results
    except (OSError, subprocess.TimeoutExpired):
        return []


def _age_days(path):
    try:
        return (time.time() - path.stat().st_mtime) / 86400.0
    except OSError:
        return 0.0


def cleanup_artifacts(log_days=0, report_days=0, keep_log_paths=None):
    """Delete old logs/report folders.

    log_days/report_days: 0 disables automatic deletion.
    keep_log_paths: iterable of absolute paths that must never be deleted
    (for example logs of currently running managed instances).
    Returns dict with counters.
    """
    prepare()
    keep = {str(Path(p).resolve()) for p in (keep_log_paths or []) if p}
    stats = {'logs_deleted': 0, 'report_dirs_deleted': 0, 'errors': []}
    try:
        log_days = int(log_days or 0)
        report_days = int(report_days or 0)
    except (TypeError, ValueError):
        log_days = report_days = 0
    if log_days > 0 and LOGS.is_dir():
        for path in LOGS.glob('*.log'):
            try:
                resolved = str(path.resolve())
                if resolved in keep:
                    continue
                if _age_days(path) >= log_days:
                    path.unlink(missing_ok=True)
                    stats['logs_deleted'] += 1
            except OSError as exc:
                stats['errors'].append(f'log {path.name}: {exc}')
    if report_days > 0 and REPORTS.is_dir():
        for summary in REPORTS.glob('*/summary.json'):
            root = summary.parent
            try:
                if _age_days(root) >= report_days:
                    shutil.rmtree(root, ignore_errors=False)
                    stats['report_dirs_deleted'] += 1
            except OSError as exc:
                stats['errors'].append(f'report {root.name}: {exc}')
    return stats


def update_model_client_preference(alias, client):
    """Persist preferred client for a stopped or running profile, without starting it.

    Does not mutate global Pi/OpenCode configuration. The caller keeps its UI
    cache in sync after this function succeeds.
    """
    if client not in ('pi', 'opencode'):
        raise ValueError('Поддерживаются только Pi и OpenCode')
    data = load_json(MODELS)
    if not isinstance(data, dict) or not isinstance(data.get('models'), list):
        raise ValueError('Не найден корректный models.json')
    matches = [p for p in data['models'] if p.get('id') == alias]
    if len(matches) != 1:
        raise ValueError('Не найден уникальный профиль: ' + str(alias))
    matches[0]['preferred_client'] = client
    prepare()
    backups = DATA / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    if MODELS.is_file():
        filename = 'models_client_' + dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json'
        import shutil as _shutil
        _shutil.copy2(MODELS, backups / filename)
    atomic_json(MODELS, data)
    for older in sorted(backups.glob('models_client_*.json'))[:-20]:
        older.unlink(missing_ok=True)
    return data
