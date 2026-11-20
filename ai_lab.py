#!/usr/bin/env python3
"""AI Model Lab v2 — local controller, stdlib only, no external connections.
User-facing CLI & terminal UI. No pkill, no writes to Android repositories or Pi.
"""
import argparse
import datetime
import glob
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("AI_LAB_CONFIG", ROOT / "models.json")).expanduser()
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "ai-model-lab-v2"
LOGS = STATE / "logs"
API = "http://127.0.0.1:8080"
WEBUI = "http://127.0.0.1:3000"
SERVER_STATE = STATE / "llama.json"
COMFY_STATE = STATE / "comfy.json"


def say(message=""):
    print(message, flush=True)


def error(message):
    say("ОШИБКА: " + str(message))


def load_config():
    with CONFIG.open(encoding="utf-8") as f:
        obj = json.load(f)
    ids = [x["id"] for x in obj.get("models", [])]
    if len(ids) != len(set(ids)) or not ids:
        raise RuntimeError("В models.json повторяются ID либо нет моделей")
    return obj


def ensure_state():
    for p in (STATE, LOGS, STATE / "benchmarks"):
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        p.chmod(0o700)


def atomic_json(path, obj):
    ensure_state()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def port_busy(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def http_json(url, data=None, timeout=2):
    try:
        raw = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"} if raw else {}
        req = urllib.request.Request(url, data=raw, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def process_start_ticks(pid):
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return int(data.rsplit(") ", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def process_cmdline(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def process_owned(meta, expected_tag):
    if not isinstance(meta, dict) or meta.get("tag") != expected_tag:
        return False
    try:
        pid = int(meta["pid"])
        expected_ticks = int(meta["start_ticks"])
    except (ValueError, KeyError, TypeError):
        return False
    if pid <= 1 or process_start_ticks(pid) != expected_ticks:
        return False
    expected_exe = meta.get("exe")
    try:
        real_exe = str(Path(f"/proc/{pid}/exe").resolve())
    except OSError:
        return False
    # Exact executable for a native llama-server; fallback to exact script path
    # only for a Python shebang app such as ComfyUI.
    if expected_tag == "llama":
        return real_exe == expected_exe
    if expected_tag == "comfy":
        return (real_exe == expected_exe and "main.py" in process_cmdline(pid)
                and "8188" in process_cmdline(pid))
    return False


def model_root(cfg):
    return Path(os.environ.get("AI_LAB_MODEL_ROOT", cfg["model_root"])).expanduser()


def choose_file(cfg, profile):
    root = model_root(cfg)
    override = os.environ.get("AI_LAB_GGUF_" + profile["id"].upper().replace("-", "_"))
    if override:
        p = Path(override).expanduser()
        if not p.is_file():
            raise RuntimeError(f"Файл модели не найден: {p}")
        return p.resolve()
    if profile.get("path"):
        p = root / profile["path"]
        if p.is_file():
            return p.resolve()
    if not root.is_dir():
        raise RuntimeError(f"Нет каталога моделей: {root}")
    pattern = profile.get("match")
    if not pattern:
        raise RuntimeError("Для этой модели нет заданного пути или шаблона")
    choices = sorted(p.resolve() for p in root.rglob(pattern) if p.is_file())
    if len(choices) != 1:
        raise RuntimeError(f"Для {profile['id']} найдено {len(choices)} GGUF по шаблону {pattern}.\n"
                           + "\n".join(str(p) for p in choices[:15])
                           + "\nУкажи точный path в models.json или AI_LAB_GGUF_<ID>.")
    return choices[0]


def binary_path(cfg):
    return Path(os.environ.get("AI_LAB_SERVER_BIN", cfg["server_bin"])).expanduser().resolve()


def build_command(cfg, profile):
    exe = binary_path(cfg)
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise RuntimeError(f"llama-server отсутствует или неисполняем: {exe}")
    gguf = choose_file(cfg, profile)
    ctx = int(profile["context"])
    if ctx < 4096 or ctx > 524288:
        raise RuntimeError("Некорректный контекст в профиле")
    cmd = [str(exe), "-m", str(gguf), "-ngl", "99", "-c", str(ctx),
           "-np", "1", "-b", "1024", "-ub", "256", "-fa", "on",
           "--no-kv-offload", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--jinja"]
    if profile.get("n_cpu_moe"):
        cmd.extend(["--n-cpu-moe", str(profile["n_cpu_moe"])])
    if profile.get("mmproj"):
        mm = model_root(cfg) / profile["mmproj"]
        if not mm.is_file():
            raise RuntimeError(f"Не найден mmproj для VL: {mm}")
        cmd += ["--mmproj", str(mm)]
    if profile.get("image_min_tokens"):
        cmd += ["--image-min-tokens", str(profile["image_min_tokens"])]
    if profile.get("thinking_off"):
        cmd += ["--reasoning", "off", "--chat-template-kwargs", '{"enable_thinking":false}']
    else:
        cmd += ["--reasoning", "off"]
    sampling = {"temp":0.7,"top_p":0.8,"top_k":20,"min_p":0,"repeat_penalty":1}
    sampling.update(profile.get("sampling", {}))
    args = {"temp":"--temp", "top_p":"--top-p", "top_k":"--top-k",
            "min_p":"--min-p", "repeat_penalty":"--repeat-penalty"}
    for key, flag in args.items():
        cmd += [flag, str(sampling[key])]
    cmd += ["--metrics", "--host", "127.0.0.1", "--port", "8080", "--alias", profile["id"]]
    return cmd, gguf


def proc_meta(proc, tag, exe, **extra):
    for _ in range(30):
        ticks = process_start_ticks(proc.pid)
        if ticks is not None:
            break
        time.sleep(0.03)
    else:
        raise RuntimeError("Не удалось прочитать PID запущенного процесса")
    return {"tag":tag,"pid":proc.pid,"start_ticks":ticks,"exe":str(exe.resolve()),**extra}


def wait_for_service(proc, url, seconds=150):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        if proc.poll() is not None:
            return False
        # If model already serving and correct process, it should respond.
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status < 500:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1.5)
    return False


def start_llama(cfg, alias, dry=False):
    profile = next((x for x in cfg["models"] if x["id"] == alias), None)
    if profile is None:
        raise RuntimeError(f"Модель {alias} не зарегистрирована в models.json")
    cmd, gguf = build_command(cfg, profile)
    if dry:
        say(f"Профиль: {profile['name']}\nGGUF: {gguf}\nКоманда (без запуска):")
        say(" ".join(shlex_quote(s) for s in cmd))
        return True
    old = read_json(SERVER_STATE)
    if process_owned(old, "llama"):
        say(f"Уже работает управляемая модель {old.get('alias')} (PID {old['pid']}).")
        return False
    if port_busy(8080):
        props = http_json(API + "/props") or {}
        say(f"Порт 8080 занят внешним сервером ({props.get('model_alias', 'alias неизвестен')}). Не прерываю его.")
        return False
    ensure_state()
    log = LOGS / f"llama_{alias}_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
    say(f"Загружаю {profile['name']}\nКонтекст: {profile['context']} | KV RAM q8_0 | GGUF: {gguf}")
    with log.open("ab", buffering=0) as out:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True, cwd=str(HOME))
    meta = proc_meta(p, "llama", binary_path(cfg), alias=alias, ctx=profile["context"], log=str(log))
    atomic_json(SERVER_STATE, meta)
    say(f"PID {p.pid}; журнал: {log}")
    if not wait_for_service(p, API + "/health", 180):
        error("llama-server не вышел в ready за 180 секунд либо завершился.")
        say(f"Последние строки лога: {log}")
        if p.poll() is not None:
            SERVER_STATE.unlink(missing_ok=True)
        return False
    props = http_json(API + "/props") or {}
    reported = props.get("model_alias")
    if reported and reported != alias:
        error(f"На порту отвечает другой alias ({reported}), ожидается {alias}!")
        return False
    say(f"✅ Готово. API {API}/v1; alias: {reported or alias}")
    pi_warnings(profile)
    return True


def shlex_quote(s):
    import shlex
    return shlex.quote(str(s))


def pi_warnings(profile):
    pi = read_json(HOME / ".pi/agent/models.json")
    if not pi:
        return
    providers = pi.get("providers", {})
    lab = providers.get("local-lab", {}) if isinstance(providers, dict) else {}
    models = lab.get("models", []) if isinstance(lab, dict) else []
    found = next((m for m in models if m.get("id") == profile["id"]), None)
    if found:
        cw = found.get("contextWindow")
        if cw != profile["context"]:
            say(f"⚠ Pi: contextWindow={cw}, сервер={profile['context']} — исправь вручную при необходимости.")
    else:
        say("ℹ Эта модель не зарегистрирована у Pi в local-lab (не меняю models.json автоматически).")


def stop_owned(meta_path, tag, force=False):
    meta = read_json(meta_path)
    if not process_owned(meta, tag):
        say(f"Нет подтверждённого процесса {tag}, управляемого AI Lab v2.")
        return False
    pid = meta["pid"]
    say(f"Останавливаю {tag}: PID={pid} ...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        meta_path.unlink(missing_ok=True)
        return True
    for _ in range(40):
        if not process_owned(meta, tag):
            meta_path.unlink(missing_ok=True)
            say("Остановлен.")
            return True
        time.sleep(0.25)
    if force and process_owned(meta, tag):
        os.kill(pid, signal.SIGKILL)
        meta_path.unlink(missing_ok=True)
        say("Остановлен принудительно.")
        return True
    say("SIGTERM отправлен, процесс пока работает. Для принудительной остановки: stop --force")
    return False


def open_browser(url, app_mode=False):
    if app_mode:
        for name in ("chromium", "brave", "google-chrome-stable"):
            browser = shutil.which(name)
            if browser:
                subprocess.Popen([browser, "--app=" + url, "--window-size=500,900"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, url], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        say("Открой вручную: " + url)


def start_webui(open_it=True):
    if not port_busy(3000):
        service = subprocess.run(["systemctl", "--user", "start", "open-webui.service"],
                                 capture_output=True, text=True) if shutil.which("systemctl") else None
        if service is None or service.returncode:
            error("Не удалось запустить open-webui.service. Проверка: systemctl --user status open-webui.service")
            if service and service.stderr:
                say(service.stderr.strip())
            return False
        deadline = time.monotonic()+45
        while time.monotonic() < deadline and not port_busy(3000):
            time.sleep(1)
    if port_busy(3000):
        say(f"WebUI: {WEBUI}")
        if open_it:
            open_browser(WEBUI)
        return True
    error("WebUI не отвечает на порту 3000")
    return False


def find_office_url():
    env_url = os.environ.get("AI_LAB_OFFICE_URL", "").strip()
    if env_url.startswith("http://127.0.0.1:") or env_url.startswith("http://localhost:"):
        return env_url
    log = HOME / ".local/state/agent-office.log"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")[-16000:]
    except OSError:
        return None
    found = re.findall(r"(?:http://)?(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{2,5})", text)
    for port in reversed(found):
        if port not in ("8080", "3000", "8188") and port_busy(int(port)):
            return f"http://127.0.0.1:{port}"
    return None


def start_office():
    script = HOME / ".local/bin/start-agent-office.sh"
    if not script.is_file():
        error("Нет старого start-agent-office.sh; укажи верный путь")
        return False
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    say(result.stdout.strip())
    if result.returncode:
        error(result.stderr.strip() or "Agent Office не запущен")
        return False
    url = find_office_url()
    if url:
        say(f"Agent Office: {url}")
        open_browser(url, app_mode=True)
    else:
        say("Офис запущен, но веб-адрес не определён. Проверь ~/.local/state/agent-office.log")
    return True


def stop_office():
    pidfile = HOME / ".local/state/agent-office.pid"
    try:
        pid = int(pidfile.read_text().strip())
        cmd = process_cmdline(pid)
        cwd = Path(f"/proc/{pid}/cwd").resolve()
        expected = (HOME / "AI/agent-office").resolve()
        if not ("run.py" in cmd and cwd == expected):
            say("Agent Office: PID не подтверждён, чужой процесс не завершаю.")
            return False
        os.kill(pid, signal.SIGTERM)
        # The old launcher uses setsid; stop its process group if it is the leader.
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        pidfile.unlink(missing_ok=True)
        say("Agent Office: отправлен SIGTERM")
        return True
    except (OSError, ValueError, ProcessLookupError):
        say("Agent Office: управляемый процесс не обнаружен")
        return False


def comfy_dir():
    candidates = [HOME / "AI/ComfyUI", Path("/home/USER/AI/models/Comfyui"),
                  Path("/home/USER/AI/models/ComfyUI")]
    return next((x for x in candidates if (x / "main.py").is_file()), None)


def start_comfy():
    if port_busy(8188):
        say("Порт ComfyUI 8188 уже занят; открываю работающий интерфейс")
        open_browser("http://127.0.0.1:8188", app_mode=True)
        return True
    directory = comfy_dir()
    if directory is None:
        error("Каталог ComfyUI не найден — проверь путь к main.py")
        return False
    py = directory / "venv/bin/python"
    if not py.is_file():
        error(f"Нет Python ComfyUI: {py}")
        return False
    ensure_state()
    log = LOGS / f"comfy_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
    with log.open("ab", buffering=0) as out:
        proc = subprocess.Popen([str(py), "main.py", "--listen", "127.0.0.1", "--port", "8188"],
                                cwd=directory, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
    meta = proc_meta(proc, "comfy", py, log=str(log))
    atomic_json(COMFY_STATE, meta)
    if not wait_for_service(proc, "http://127.0.0.1:8188", 90):
        error(f"ComfyUI не отвечает; смотри {log}")
        return False
    open_browser("http://127.0.0.1:8188", app_mode=True)
    return True


def find_legacy_llama(cfg):
    """Find only same-user processes with the exact known llama-server executable."""
    exe = binary_path(cfg)
    matches = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        if pid in (os.getpid(), os.getppid()):
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            actual = (proc / "exe").resolve()
            if actual != exe:
                continue
            ticks = process_start_ticks(pid)
            if ticks is None:
                continue
            matches.append((pid, ticks, process_cmdline(pid)))
        except (OSError, ValueError):
            continue
    return matches


def stop_legacy_llama(cfg):
    """Explicitly stop exact executable matches, rechecking PID and start ticks."""
    current = read_json(SERVER_STATE)
    owned_pid = current.get("pid") if process_owned(current, "llama") else None
    old = [x for x in find_legacy_llama(cfg) if x[0] != owned_pid]
    if not old:
        say("Неуправляемых llama-server с известным исполняемым файлом не найдено.")
        return
    say("Обнаружены старые llama-server (возможен активный бенчмарк):")
    for pid, ticks, cmd in old:
        say(f"  PID={pid} · {cmd[:180]}")
    answer = input("Для остановки ЭТИХ процессов введи 'ОСТАНОВИТЬ СТАРЫЕ': ").strip()
    if answer != "ОСТАНОВИТЬ СТАРЫЕ":
        say("Неуправляемые серверы не тронуты.")
        return
    for pid, ticks, cmd in old:
        if process_start_ticks(pid) != ticks:
            say(f"Пропускаю изменившийся PID {pid}")
            continue
        try:
            if Path(f"/proc/{pid}/exe").resolve() != binary_path(cfg):
                continue
            os.kill(pid, signal.SIGTERM)
            say(f"SIGTERM → PID={pid}")
        except (OSError, ProcessLookupError):
            pass


def stop_all(cfg, include_legacy=False):
    say("=== Остановка управляемых сервисов ===")
    stop_owned(SERVER_STATE, "llama")
    stop_owned(COMFY_STATE, "comfy")
    stop_office()
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "stop", "open-webui.service"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        say("Open WebUI: отправлена команда остановки systemd user-service")
    if include_legacy:
        stop_legacy_llama(cfg)
    if port_busy(8080):
        say("⚠ Порт 8080 по-прежнему занят. Проверь список процессов через status.")
    say("Не закрываю Pi/OpenCode: их работа могла быть несохранена.")

def gpu_info():
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    p = subprocess.run([smi, "--query-gpu=utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4)
    return p.stdout.strip().splitlines()[0] if p.returncode == 0 and p.stdout.strip() else None


def status():
    meta = read_json(SERVER_STATE)
    if process_owned(meta, "llama"):
        say(f"llama.cpp: PID={meta['pid']} · alias={meta.get('alias')} · ctx={meta.get('ctx')}")
    else:
        say("llama.cpp: нет подтверждённого процесса AI Lab v2")
    props = http_json(API + "/props") if port_busy(8080) else None
    if props:
        context = (props.get("default_generation_settings") or {}).get("n_ctx", props.get("n_ctx"))
        say(f"8080: alias={props.get('model_alias')} · контекст={context}")
    elif port_busy(8080):
        say("8080: занят, но API /props недоступен")
    else:
        say("8080: свободен")
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:")):
                k, value = line.split(":", 1)
                mem[k] = int(value.split()[0]) / (1024 ** 2)
        if "MemTotal" in mem and "MemAvailable" in mem:
            say(f"RAM: занято ~{mem['MemTotal']-mem['MemAvailable']:.1f} / {mem['MemTotal']:.1f} GiB")
        if "SwapTotal" in mem and "SwapFree" in mem:
            say(f"Swap: занято ~{mem['SwapTotal']-mem['SwapFree']:.1f} / {mem['SwapTotal']:.1f} GiB")
    except OSError:
        pass
    say("WebUI 3000: " + ("работает" if port_busy(3000) else "не отвечает"))
    say("ComfyUI 8188: " + ("работает" if port_busy(8188) else "не отвечает"))
    url = find_office_url()
    say("Agent Office: " + (url or "адрес не определён"))
    gpu = gpu_info()
    if gpu:
        say("GPU (util%, MiB used, MiB total, W, °C): " + gpu)


def quick_speed_test():
    props = http_json(API + "/props")
    if not props:
        error("Сервер на 8080 не отвечает. Сначала запусти модель.")
        return False
    say("Быстрый локальный speed-test: не является официальным benchmark качества.")
    payload = {"model":props.get("model_alias", "local"),"messages":[{"role":"user",
         "content":"Кратко перечисли 15 практических рекомендаций по архитектуре Android на Kotlin, по одному предложению на пункт."}],
         "stream":False,"temperature":0,"max_tokens":256}
    t0 = time.monotonic()
    reply = http_json(API + "/v1/chat/completions", payload, timeout=240)
    elapsed = time.monotonic() - t0
    if not reply or "choices" not in reply:
        error("Нет корректного ответа от /v1/chat/completions")
        return False
    usage = reply.get("usage") or {}
    output = usage.get("completion_tokens")
    input_tokens = usage.get("prompt_tokens")
    timings = reply.get("timings") or {}
    say(f"Время ответа: {elapsed:.2f} с")
    say(f"Prompt tokens: {input_tokens}; generated tokens: {output}")
    if isinstance(output, (int, float)) and elapsed:
        say(f"Выходные токены / полное время: {output/elapsed:.2f} tok/s (включая prefill)")
    if timings:
        say(f"Тайминги llama.cpp: {timings}")
    result = {"timestamp":datetime.datetime.now().astimezone().isoformat(),
              "alias":props.get("model_alias"),"context":(props.get("default_generation_settings") or {}).get("n_ctx"),
              "elapsed_s":round(elapsed,3),"input_tokens":input_tokens,"output_tokens":output,
              "timings":timings,"gpu_info":gpu_info()}
    ensure_state()
    dest = STATE / "benchmarks" / f"speed_{result['alias']}_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    atomic_json(dest, result)
    say(f"Сохранено: {dest}")
    return True


def list_gguf(cfg):
    root = model_root(cfg)
    if not root.is_dir():
        error(f"Не найден каталог {root}")
        return
    allfiles = sorted(x for x in root.rglob("*.gguf") if x.is_file() and "mmproj" not in x.name.lower())
    say(f"Найдено GGUF: {len(allfiles)} (ещё не зарегистрированные модели не запускаются автоматически)")
    for path in allfiles:
        say(" • " + str(path.relative_to(root)))


def doctor(cfg):
    say(f"Сервер: {binary_path(cfg)} {'OK' if binary_path(cfg).is_file() else 'НЕ НАЙДЕН'}")
    for prof in cfg["models"]:
        try:
            path = choose_file(cfg, prof)
            extra = prof.get("mmproj")
            if extra and not (model_root(cfg) / extra).is_file():
                raise RuntimeError("mmproj отсутствует")
            say(f"✅ {prof['id']:18} {prof['context']:>6} tokens  {path}")
        except RuntimeError as e:
            say(f"⚠ {prof['id']:18} {e}")
    say("\nПроверка Pi (только чтение):")
    for prof in cfg["models"]:
        pi_warnings(prof)
    say("\nСостояние сервисов:")
    status()


def menu_after_model(cfg, alias):
    while True:
        say("\n========== AI MODEL LAB ==========")
        say(f"Модель: {alias} | API: {API}/v1")
        say("1) Открыть Open WebUI")
        say("2) Открыть Agent Office")
        say("3) Открыть WebUI + Agent Office")
        say("4) Запустить OpenCode (текущая модель)")
        say("5) Завершить текущую модель")
        say("6) Завершить все управляемые AI-сервисы")
        say("a) Завершить также старые llama-server (с отдельным подтверждением)")
        say("7) Статус GPU, памяти, серверов")
        say("8) Быстрый замер скорости API")
        say("9) Показать журнал сервера")
        say("0) Закрыть окно, оставить сервер в фоне")
        try:
            choice = input("Выбор: ").strip()
        except (KeyboardInterrupt, EOFError):
            say("\nОкно закрывается, сервер остаётся работать.")
            return
        if choice == "0":
            say("Сервер остаётся в фоне.")
            return
        if choice == "1": start_webui()
        elif choice == "2": start_office()
        elif choice == "3": start_webui(); start_office()
        elif choice == "4":
            exe = shutil.which("opencode")
            if not exe:
                error("Не найден opencode")
            else:
                say(f"Запускаю OpenCode с local/{alias}; проверь модель в конфигурации OpenCode.")
                subprocess.run([exe, "--model", "local/"+alias])
        elif choice == "5":
            stop_owned(SERVER_STATE, "llama")
            return
        elif choice == "6":
            if input("Подтвердить остановку всех управляемых сервисов? [да/нет]: ").strip().lower() == "да":
                stop_all(cfg); return
        elif choice == "a":
            stop_legacy_llama(cfg)
        elif choice == "7": status()
        elif choice == "8": quick_speed_test()
        elif choice == "9":
            meta = read_json(SERVER_STATE)
            if meta and meta.get("log") and Path(meta["log"]).is_file():
                for line in Path(meta["log"]).read_text(errors="replace").splitlines()[-35:]:
                    say(line)
            else: say("Журнал не найден")
        else:
            say("Неизвестный пункт")


def main_menu(cfg):
    while True:
        say("\n========= AI MODEL LAB v2 =========")
        for i, p in enumerate(cfg["models"], 1):
            say(f"{i}) {p['name']} [{p['id']}]")
        say("s) Статус  d) Диагностика  v) Speed-test  w) WebUI  o) Agent Office")
        say("c) ComfyUI  f) Поиск GGUF  x) Стоп текущей модели  X) Стоп всех сервисов")
        say("L) Остановить старые llama-server (двойное подтверждение)")
        say("0) Выход (серверы останутся в фоне)")
        try:
            choice = input("Выбор: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if choice == "0": return
        if choice.isdigit() and 1 <= int(choice) <= len(cfg["models"]):
            alias = cfg["models"][int(choice)-1]["id"]
            if start_llama(cfg, alias):
                menu_after_model(cfg, alias)
        elif choice == "s": status()
        elif choice == "d": doctor(cfg)
        elif choice == "v": quick_speed_test()
        elif choice == "w": start_webui()
        elif choice == "o": start_office()
        elif choice == "c": start_comfy()
        elif choice == "f": list_gguf(cfg)
        elif choice == "x": stop_owned(SERVER_STATE, "llama")
        elif choice == "L": stop_legacy_llama(cfg)
        elif choice == "X":
            if input("Ввести 'да' для остановки всех управляемых сервисов: ").strip().lower() == "да":
                stop_all(cfg)
        else:
            say("Неверный пункт меню")


def main():
    parser = argparse.ArgumentParser(description="AI Model Lab v2 — CachyOS, локальные модели")
    parser.add_argument("action", nargs="?", default="menu", choices=[
        "menu", "start", "stop", "stop-all", "status", "doctor", "webui", "office", "comfy", "speed", "discover"])
    parser.add_argument("model", nargs="?")
    parser.add_argument("--menu", action="store_true", help="показать меню после запуска модели")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ask", action="store_true", help="потребовать подтверждение остановки всех")
    parser.add_argument("--force", action="store_true", help="SIGKILL только своему управляемому процессу после ожидания")
    parser.add_argument("--include-legacy", action="store_true", help="После управляемых предложить остановить старые llama-server")
    args = parser.parse_args()
    try:
        cfg = load_config()
        if args.action == "menu": main_menu(cfg)
        elif args.action == "start":
            if not args.model: parser.error("Для start укажи alias")
            succeeded = start_llama(cfg, args.model, args.dry_run)
            if succeeded and args.menu and not args.dry_run:
                menu_after_model(cfg, args.model)
            elif args.menu and not args.dry_run and sys.stdin.isatty():
                input("Нажми Enter, чтобы закрыть окно...")
        elif args.action == "stop": stop_owned(SERVER_STATE, "llama", args.force)
        elif args.action == "stop-all":
            if not args.ask or input("Остановить все управляемые AI-сервисы? Напиши 'да': ").strip().lower() == "да":
                stop_all(cfg, args.include_legacy)
        elif args.action == "status": status()
        elif args.action == "doctor": doctor(cfg)
        elif args.action == "webui": start_webui()
        elif args.action == "office": start_office()
        elif args.action == "comfy": start_comfy()
        elif args.action == "speed": quick_speed_test()
        elif args.action == "discover": list_gguf(cfg)
    except (RuntimeError, OSError, ValueError) as e:
        error(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
