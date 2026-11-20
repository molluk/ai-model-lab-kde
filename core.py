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

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
DATA = ROOT / 'data'
LOGS = DATA / 'logs'
REPORTS = DATA / 'reports'
MODELS = ROOT / 'models.json'
SETTINGS = ROOT / 'settings.json'


def prepare():
    for path in (DATA, LOGS, REPORTS):
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
    return load_json(MODELS, {})


def settings():
    return load_json(SETTINGS, {})


def model_by_id(alias):
    return next((p for p in config().get('models', []) if p.get('id') == alias), None)


def model_root():
    return Path(os.environ.get('AI_LAB_MODEL_ROOT', config().get('model_root', '/home/USER/AI/models'))).expanduser()


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
    exe = server_exe()
    if not exe.is_file(): raise FileNotFoundError(f'Не найден llama-server: {exe}')
    gguf = resolve_gguf(profile)
    context = int(profile['context'])
    if not 4096 <= context <= 524288: raise ValueError('Недопустимый context')
    args = [str(exe), '-m', str(gguf), '-ngl', '99', '-c', str(context), '-np', '1', '-b', '1024',
            '-ub', '256', '-fa', 'on', '--no-kv-offload', '--cache-type-k', 'q8_0',
            '--cache-type-v', 'q8_0', '--jinja', '--reasoning', 'off']
    if profile.get('n_cpu_moe'):
        args += ['--n-cpu-moe', str(profile['n_cpu_moe'])]
    if profile.get('mmproj'):
        mm = model_root() / profile['mmproj']
        if not mm.is_file(): raise FileNotFoundError('Не найден mmproj: ' + str(mm))
        args += ['--mmproj', str(mm)]
    if profile.get('image_min_tokens'):
        args += ['--image-min-tokens', str(profile['image_min_tokens'])]
    if profile.get('thinking_off'):
        args += ['--chat-template-kwargs', '{"enable_thinking":false}']
    sampling = {'temp': .7, 'top_p': .8, 'top_k': 20, 'min_p': 0, 'repeat_penalty': 1}
    sampling.update(profile.get('sampling', {}))
    for name, flag in [('temp','--temp'), ('top_p','--top-p'), ('top_k','--top-k'),
                       ('min_p','--min-p'), ('repeat_penalty','--repeat-penalty')]:
        args += [flag, str(sampling[name])]
    args += ['--metrics', '--host', '127.0.0.1', '--port', '8080', '--alias', profile['id']]
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
        if os.getpgid(pid) == pid and name in ('office','comfy'):
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


def webui_start():
    if not shutil.which('systemctl'): raise RuntimeError('Не найден systemctl')
    service = settings().get('webui_service', 'open-webui.service')
    proc = subprocess.run(['systemctl','--user','start',service], capture_output=True,text=True,timeout=30)
    if proc.returncode: raise RuntimeError(proc.stderr.strip() or 'Ошибка запуска WebUI')
    return f'WebUI: service {service} запущен'


def webui_stop():
    service = settings().get('webui_service', 'open-webui.service')
    proc = subprocess.run(['systemctl','--user','stop',service], capture_output=True,text=True,timeout=30)
    if proc.returncode: raise RuntimeError(proc.stderr.strip() or 'Ошибка остановки WebUI')
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
    for d in (chosen, HOME/'AI/ComfyUI', Path('/home/USER/AI/models/Comfyui'), Path('/home/USER/AI/models/ComfyUI')):
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


def gpu_metrics():
    cmd = shutil.which('nvidia-smi')
    if not cmd: return {}
    try:
        index = str(settings().get('gpu_index',0))
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
