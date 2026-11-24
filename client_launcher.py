#!/usr/bin/env python3
"""Launch OpenCode or Pi against a *specific* running AI Model Lab instance.

No global OpenCode/Pi config is changed. Local per-model Pi configurations are
written only under this application's data/clients directory. Tools exposed
inside an interactive agent are governed by the agent's own permission config.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import core
import multi
import pi_bridge_manager
import offline_client

CLIENTS = ('opencode', 'pi')


def preferred_client(profile):
    """Return preferred client for a profile, with a legacy-safe fallback."""
    profile = profile or {}
    choice = profile.get('preferred_client')
    if choice in CLIENTS:
        return choice
    alias = str(profile.get('id', '')).lower()
    return 'opencode' if 'coder' in alias or 'devstral' in alias else 'pi'


def find_executable(name):
    resolved = shutil.which(name)
    candidates = [resolved, core.HOME / '.local/bin' / name,
                  core.HOME / '.opencode/bin' / name,
                  core.HOME / '.local/share/mise/installs' / name / 'bin' / name]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FileNotFoundError(f'Не найдена команда {name}. Проверь установку и PATH рабочего стола.')


def effective_instance(alias):
    multi.validate_alias(alias)
    state = multi.inspect(alias)
    if not state.get('managed') or state.get('state') != 'running':
        raise RuntimeError(f'{alias}: модель должна быть запущена и готова к ответам')
    profile = multi.profile_by_id(alias)
    if not profile:
        raise RuntimeError(f'{alias}: профиль отсутствует в models.json')
    port = int(state.get('port', profile.get('port', 8080)))
    props = core.json_api(f'http://127.0.0.1:{port}/props', timeout=1.5) or {}
    if props.get('model_alias') != alias:
        raise RuntimeError(f'{alias}: на порту {port} не подтверждён нужный alias (данные /props)')
    settings = props.get('default_generation_settings') or {}
    ctx = settings.get('n_ctx') or props.get('n_ctx') or state.get('context') or profile['context']
    ctx = int(ctx)
    if ctx < 4096:
        raise RuntimeError('Сервер сообщил слишком маленький контекст')
    return {'alias': alias, 'name': profile.get('name', alias), 'port': port,
            'context': ctx, 'mmproj': bool(profile.get('mmproj')),
            'url': f'http://127.0.0.1:{port}/v1'}


def workspace_dir(settings=None):
    cfg = settings or core.settings()
    chosen = str(cfg.get('client_workspace') or str(core.HOME)).strip()
    resolved = Path(chosen).expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError('Рабочая папка клиента не существует: ' + str(resolved))
    return resolved


def output_limit(info):
    return max(512, min(8192, info['context'] // 4))


def opencode_v1_config(info):
    provider = 'ai-model-lab'
    return {'provider': {provider: {
        'npm': '@ai-sdk/openai-compatible',
        'name': 'AI Model Lab — local',
        'options': {'baseURL': info['url'], 'apiKey': 'local'},
        'models': {info['alias']: {'name': info['name'],
                                   'limit': {'context': info['context'], 'output': output_limit(info)}}}
    }}, 'model': f"{provider}/{info['alias']}"}


def opencode_v2_config(info):
    provider = 'ai-model-lab'
    return {'providers': {provider: {
        'name': 'AI Model Lab — local',
        'package': '@opencode/ai/providers/openai-compatible',
        'settings': {'baseURL': info['url'], 'apiKey': 'local'},
        'models': {info['alias']: {'name': info['name']}}
    }}, 'model': f"{provider}/{info['alias']}"}


def opencode_major(executable):
    result = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=5)
    raw = (result.stdout + ' ' + result.stderr).strip()
    match = re.search(r'(?<!\d)([12])\.(\d+)\.(\d+)', raw)
    if not match:
        raise RuntimeError('Не распознана версия OpenCode (ожидается 1.x или 2.x): ' + raw[:140])
    return int(match.group(1))


def pi_global_matches(info):
    """Reuse user's regular Pi setup only when endpoint+model+context match."""
    pi = core.load_json(core.HOME / '.pi/agent/models.json', {}) or {}
    provider = (pi.get('providers') or {}).get('local-lab') or {}
    actual_url = str(provider.get('baseUrl') or '').rstrip('/')
    if actual_url != info['url'].rstrip('/'):
        return False
    for item in provider.get('models', []):
        if item.get('id') == info['alias'] and int(item.get('contextWindow', 0)) == info['context']:
            return True
    return False


def isolated_pi_config(info):
    return {'providers': {'ai-model-lab': {
        'baseUrl': info['url'], 'api': 'openai-completions', 'apiKey': 'local',
        'models': [{'id': info['alias'], 'name': info['name'],
                    'contextWindow': info['context'], 'maxTokens': output_limit(info),
                    'reasoning': False, 'input': ['text', 'image'] if info['mmproj'] else ['text'],
                    'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]
    }}}


def safe_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # atomic_json may call prepare() and is intentionally restricted to app paths.
    if not path.resolve().is_relative_to((core.DATA / 'clients').resolve()):
        raise ValueError('Нельзя записывать конфигурацию вне AI Model Lab/data/clients')
    core.atomic_json(path, data)


def build_command(info, client, executable, version=None):
    env = os.environ.copy()
    if client == 'opencode':
        major = version if version is not None else opencode_major(executable)
        if major not in (1, 2):
            raise RuntimeError('Поддерживаются OpenCode 1.x и 2.x')
        cfg = opencode_v1_config(info) if major == 1 else opencode_v2_config(info)
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps(cfg, ensure_ascii=False)
        argv = [executable]
        if major == 2:
            argv.append('--standalone')  # V2 shared service may ignore per-invocation overrides.
        argv += ['--model', f"ai-model-lab/{info['alias']}"]
        return argv, env, f'OpenCode {major}.x (отдельная сессия)'
    if client == 'pi':
        argv = [executable]
        if pi_global_matches(info):
            provider = 'local-lab'
            env.pop('PI_CODING_AGENT_DIR', None)  # Use the verified ~/.pi/agent/models.json.
            name = 'Pi — существующий local-lab'
        else:
            provider = 'ai-model-lab'
            agent_dir = core.DATA / 'clients' / 'pi' / info['alias'] / str(info['port'])
            safe_write_json(agent_dir / 'models.json', isolated_pi_config(info))
            env['PI_CODING_AGENT_DIR'] = str(agent_dir.resolve())
            name = 'Pi — отдельная локальная конфигурация (без глобальных расширений)'
        agent_dir = Path(env.get('PI_CODING_AGENT_DIR') or core.HOME / '.pi' / 'agent')
        if pi_bridge_manager.needs_explicit_extension(agent_dir):
            argv += ['--extension', str(pi_bridge_manager.bridge_file())]
        argv += ['--provider', provider, '--model', info['alias'], '--thinking', 'off']
        return argv, env, name
    raise ValueError('Неизвестный клиент: ' + str(client))


def execute(client, alias):
    if client not in CLIENTS:
        raise ValueError('Доступно только: ' + ', '.join(CLIENTS))
    info = effective_instance(alias)
    executable = find_executable(client)
    workspace = workspace_dir()
    argv, env, label = build_command(info, client, executable)
    print(f'AI Model Lab → {label}', flush=True)
    print(f"Модель: {alias} | API: {info['url']} | контекст: {info['context']}", flush=True)
    print(f'Рабочий каталог: {workspace}', flush=True)
    print('Важно: доступ к файловой системе и инструментам контролируется самим клиентом.', flush=True)
    profile = multi.profile_by_id(alias) or {}
    if offline_client.mode(profile) == 'offline':
        # No silent fallback: missing bwrap or failed namespace setup must
        # leave Pi/OpenCode unlaunched rather than leaking network access.
        print('🔒 Сеть клиента: ОФЛАЙН. Интернет в новом сетевом пространстве '
              'отсутствует; локальный API доступен через Unix bridge.', flush=True)
        print('Это ограничение не относится к отдельным запущенным сессиям, '
              'самому llama-server, D-Bus или другому ПО пользователя.', flush=True)
        return offline_client.run_isolated(
            args=argv, env=env, port=info['port'], workspace=workspace,
            app_data=core.DATA)
    print('🌐 Сеть клиента: обычный доступ системы.', flush=True)
    os.chdir(workspace)
    os.execvpe(argv[0], argv, env)


def main():
    parser = argparse.ArgumentParser(description='AI Model Lab — запуск клиента для конкретной модели')
    parser.add_argument('--client', choices=CLIENTS, required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    try:
        return execute(args.client, args.model) or 0
    except Exception as exc:
        print(f'ОШИБКА: {exc}', file=sys.stderr, flush=True)
        try:
            input('Нажми Enter для закрытия окна…')
        except (EOFError, KeyboardInterrupt):
            pass
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
