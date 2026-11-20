"""Launch local service UIs in a browser, starting their service if needed.

UI-free helpers allow headless testing. Never run browser/service commands
through a shell. Local service endpoints are restricted to loopback hosts.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import core

OPEN_MODES = ('tab', 'window')
SERVICES = ('webui', 'office', 'comfy')
PREFERENCE_KEY = 'browser_open_modes'

# Commands for browsers that support an explicit new-window flag.
_BROWSER_NAMES = (
    'firefox', 'firefox-developer-edition', 'librewolf', 'floorp', 'waterfox',
    'zen-browser', 'chromium', 'chromium-browser', 'google-chrome',
    'google-chrome-stable', 'brave-browser', 'brave', 'vivaldi',
    'vivaldi-stable', 'microsoft-edge', 'falkon',
)


def validate_local_url(url: str) -> str:
    """Only open already configured local HTTP services; never probe remote URLs."""
    parsed = urllib.parse.urlsplit(url or '')
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('URL сервиса должен использовать http://localhost или http://127.0.0.1')
    if parsed.username or parsed.password or parsed.port is None:
        raise ValueError('Укажи локальный URL с портом и без учётных данных')
    return url


def get_mode(service_id: str, settings: dict | None = None) -> str:
    if service_id not in SERVICES:
        raise ValueError(f'Неизвестный сервис: {service_id}')
    cfg = core.settings() if settings is None else settings
    saved = cfg.get(PREFERENCE_KEY, {})
    selected = saved.get(service_id) if isinstance(saved, dict) else None
    return selected if selected in OPEN_MODES else 'tab'


def set_mode(service_id: str, mode: str) -> dict:
    if service_id not in SERVICES or mode not in OPEN_MODES:
        raise ValueError('Неподдерживаемый сервис или режим открытия')
    cfg = core.settings()
    entries = cfg.get(PREFERENCE_KEY, {})
    entries = dict(entries) if isinstance(entries, dict) else {}
    entries[service_id] = mode
    cfg[PREFERENCE_KEY] = entries
    core.atomic_json(core.SETTINGS, cfg)
    return cfg


def http_ready(url: str, timeout: float = 1.5) -> bool:
    validate_local_url(url)
    # Ignore HTTP_PROXY and environment proxy configuration for local services.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, method='GET'), timeout=timeout) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError as exc:
        return 400 <= exc.code < 500  # Login/authorization may require a browser.
    except (OSError, ValueError, TimeoutError):
        return False


def wait_http_ready(url_provider, timeout: float = 75.0, interval: float = 0.8) -> str:
    """Poll for a ready local web service without blocking the Qt event loop.

    Caller must invoke this from a worker thread. URL can change as a server
    starts and emits its chosen port in logs (Agent Office).
    """
    end = time.monotonic() + timeout
    last_url = ''
    while True:
        url = url_provider() if callable(url_provider) else url_provider
        if url:
            validate_local_url(url)
            last_url = url
            if http_ready(url):
                return url
        if time.monotonic() >= end:
            break
        time.sleep(min(interval, max(0.0, end - time.monotonic())))
    raise TimeoutError(
        f'Сервис не открыл HTTP-интерфейс за {timeout:g} с. '
        f'Адрес: {last_url or "не определён"}. Проверь журнал сервиса, порт и настройки URL.'
    )


def ensure_ready(service_id: str) -> str:
    """Start a stopped supported service and return only after HTTP is ready."""
    if service_id == 'webui':
        url = 'http://127.0.0.1:3000'
        if http_ready(url):
            return url
        if not core.port_open(3000):
            try:
                core.webui_start()
            except Exception as exc:
                raise RuntimeError(
                    'Не удалось запустить Open WebUI. Установи и настрой службу '
                    'systemd --user (параметр «Служба WebUI»). '
                    'Инструкция: https://docs.openwebui.com/getting-started/quick-start/\n'
                    f'Причина: {exc}'
                ) from exc
        return wait_http_ready(url, timeout=90)

    if service_id == 'office':
        url = core.office_url()
        if url and http_ready(url):
            return url
        if not core.verified('office'):
            try:
                core.office_start()
            except Exception as exc:
                raise RuntimeError(
                    'Не удалось запустить Agent Office. Проверь каталог Agent Office '
                    'и файл run.py. Инструкция: https://github.com/NosytLabs/agent-office\n'
                    f'Причина: {exc}'
                ) from exc
        try:
            return wait_http_ready(core.office_url, timeout=60)
        except TimeoutError as exc:
            raise RuntimeError(
                'Agent Office запущен, но адрес интерфейса не определён или не отвечает. '
                'Укажи параметр «URL Agent Office» в настройках программы.\n'
                f'{exc}'
            ) from exc

    if service_id == 'comfy':
        url = 'http://127.0.0.1:8188'
        if http_ready(url):
            return url
        if not core.port_open(8188):
            try:
                core.comfy_start()
            except Exception as exc:
                raise RuntimeError(f'Не удалось запустить ComfyUI. Проверь путь и venv: {exc}') from exc
        return wait_http_ready(url, timeout=90)

    raise ValueError(f'Неизвестный сервис: {service_id}')


def _preferred_window_browser():
    """Try the KDE/default .desktop browser first, then supported installed browsers."""
    preferred = ''
    if shutil.which('xdg-settings'):
        try:
            proc = subprocess.run(['xdg-settings', 'get', 'default-web-browser'],
                                  text=True, capture_output=True, timeout=2)
            if proc.returncode == 0:
                preferred = proc.stdout.strip().lower()
        except (OSError, subprocess.TimeoutExpired):
            pass
    for name in _BROWSER_NAMES:
        if name in preferred and shutil.which(name):
            return shutil.which(name)
    for name in _BROWSER_NAMES:
        if shutil.which(name):
            return shutil.which(name)
    return None


def open_browser(url: str, mode: str) -> str:
    """Open as a browser tab or explicitly request a new browser window.

    Tabs depend on the default browser's desktop integration and settings.
    Windows require a supported installed browser; never silently use a tab.
    """
    validate_local_url(url)
    if mode == 'tab':
        if not webbrowser.open_new_tab(url):
            raise RuntimeError('Не удалось открыть вкладку в браузере по умолчанию')
        return 'Открыто в браузере (запрошена новая вкладка)'
    if mode == 'window':
        executable = _preferred_window_browser()
        if not executable:
            raise RuntimeError(
                'Для отдельного окна не найден поддерживаемый браузер. '
                'Установи Firefox, Chromium, Brave или другой поддерживаемый браузер.'
            )
        subprocess.Popen([executable, '--new-window', url],
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return 'Открыто отдельное окно: ' + executable
    raise ValueError('Неизвестный режим открытия браузера')
