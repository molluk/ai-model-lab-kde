"""One-click service open, preference persistence, and safe browser dispatch."""
import ast
import http.server
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest import mock

import core
import service_browser as sb

ROOT = Path(__file__).resolve().parents[1]


class TestBrowserPreferences(unittest.TestCase):
    def test_defaults_and_invalid_values(self):
        self.assertEqual(sb.get_mode('webui', {}), 'tab')
        self.assertEqual(sb.get_mode('office', {sb.PREFERENCE_KEY: {'office': 'window'}}), 'window')
        self.assertEqual(sb.get_mode('office', {sb.PREFERENCE_KEY: {'office': 'app'}}), 'app')
        self.assertEqual(sb.get_mode('office', {sb.PREFERENCE_KEY: {'office': 'bad'}}), 'tab')
        with self.assertRaises(ValueError):
            sb.get_mode('unknown', {})

    def test_save_does_not_replace_other_settings(self):
        with tempfile.TemporaryDirectory() as td:
            saved = Path(td) / 'settings.json'
            core.atomic_json(saved, {'language': 'en', 'webui_service': 'custom.service'})
            with mock.patch.object(core, 'SETTINGS', saved), mock.patch.object(core, 'settings', side_effect=lambda: core.load_json(saved, {})):
                sb.set_mode('webui', 'window')
                sb.set_mode('office', 'app')
            obj = core.load_json(saved, {})
            self.assertEqual(obj['language'], 'en')
            self.assertEqual(obj['webui_service'], 'custom.service')
            self.assertEqual(obj[sb.PREFERENCE_KEY], {'webui': 'window', 'office': 'app'})

    def test_only_loopback_service_urls(self):
        for url in ('https://127.0.0.1:3000', 'http://evil.example:3000',
                    'http://user:pass@localhost:3000', 'file:///etc/passwd'):
            with self.assertRaises(ValueError, msg=url):
                sb.validate_local_url(url)
        self.assertEqual(sb.validate_local_url('http://127.0.0.1:3000'), 'http://127.0.0.1:3000')


class TestReadiness(unittest.TestCase):
    def test_http_ready_and_wait(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
            def log_message(self, *_):
                pass
        with socketserver.TCPServer(('127.0.0.1', 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = 'http://127.0.0.1:%d' % server.server_address[1]
            self.assertTrue(sb.http_ready(url))
            self.assertEqual(sb.wait_http_ready(lambda: url, timeout=1.0), url)
            server.shutdown()
            worker.join(timeout=2)

    def test_webui_started_only_when_port_is_free(self):
        with mock.patch.object(sb, 'http_ready', side_effect=[False, True]), \
             mock.patch.object(core, 'port_open', return_value=False), \
             mock.patch.object(core, 'webui_start') as start, \
             mock.patch.object(sb, 'wait_http_ready', return_value='http://127.0.0.1:3000'):
            self.assertEqual(sb.ensure_ready('webui'), 'http://127.0.0.1:3000')
            start.assert_called_once()
        with mock.patch.object(sb, 'http_ready', return_value=True), \
             mock.patch.object(core, 'webui_start') as start:
            self.assertEqual(sb.ensure_ready('webui'), 'http://127.0.0.1:3000')
            start.assert_not_called()

    def test_office_address_is_resolved_after_start(self):
        with mock.patch.object(core, 'office_url', side_effect=['', 'http://127.0.0.1:4242']), \
             mock.patch.object(core, 'verified', return_value=None), \
             mock.patch.object(core, 'office_start') as start, \
             mock.patch.object(sb, 'wait_http_ready', side_effect=lambda callback, **kwargs: callback()):
            self.assertEqual(sb.ensure_ready('office'), 'http://127.0.0.1:4242')
            start.assert_called_once()


class TestBrowserLaunch(unittest.TestCase):
    def test_tab_dispatch(self):
        with mock.patch.object(sb.webbrowser, 'open_new_tab', return_value=True) as start:
            result = sb.open_browser('http://127.0.0.1:3000', 'tab')
        self.assertIn('вкладка', result)
        start.assert_called_once_with('http://127.0.0.1:3000')

    def test_window_uses_argv_not_shell(self):
        with mock.patch.object(sb, '_preferred_window_browser', return_value='/usr/bin/firefox'), \
             mock.patch.object(sb.subprocess, 'Popen') as popen:
            sb.open_browser('http://127.0.0.1:3000', 'window')
        args = popen.call_args.args[0]
        self.assertEqual(args, ['/usr/bin/firefox', '--new-window', 'http://127.0.0.1:3000'])
        self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def test_window_never_silently_falls_back_to_tab(self):
        with mock.patch.object(sb, '_preferred_window_browser', return_value=None), \
             mock.patch.object(sb.webbrowser, 'open_new_tab') as tab:
            with self.assertRaises(RuntimeError):
                sb.open_browser('http://127.0.0.1:3000', 'window')
            tab.assert_not_called()

    def test_app_window_uses_chromium_app_switch_without_shell(self):
        with mock.patch.object(sb, '_preferred_app_browser', return_value='/usr/bin/chromium'), \
             mock.patch.object(sb.subprocess, 'Popen') as popen:
            result = sb.open_browser('http://127.0.0.1:3000', 'app')
        self.assertIn('без панелей', result)
        self.assertEqual(popen.call_args.args[0],
                         ['/usr/bin/chromium', '--app=http://127.0.0.1:3000'])
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_app_window_does_not_fall_back_to_browser_tab(self):
        with mock.patch.object(sb, '_preferred_app_browser', return_value=None), \
             mock.patch.object(sb.webbrowser, 'open_new_tab') as tab, \
             mock.patch.object(sb.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'Chromium'):
                sb.open_browser('http://127.0.0.1:3000', 'app')
            tab.assert_not_called()
            popen.assert_not_called()

    def test_app_browser_selection_skips_firefox_and_follows_default(self):
        binaries = {'xdg-settings': '/usr/bin/xdg-settings',
                    'firefox': '/usr/bin/firefox',
                    'chromium': '/usr/bin/chromium',
                    'brave-browser': '/usr/bin/brave-browser'}
        result = mock.Mock(returncode=0, stdout='brave-browser.desktop')
        with mock.patch.object(sb.shutil, 'which', side_effect=binaries.get), \
             mock.patch.object(sb.subprocess, 'run', return_value=result):
            self.assertEqual(sb._preferred_app_browser(), '/usr/bin/brave-browser')
        result.stdout = 'firefox.desktop'
        with mock.patch.object(sb.shutil, 'which', side_effect=binaries.get), \
             mock.patch.object(sb.subprocess, 'run', return_value=result):
            self.assertEqual(sb._preferred_app_browser(), '/usr/bin/chromium')

    def test_gui_offers_three_distinct_modes(self):
        source = (ROOT / 'gui.py').read_text(encoding='utf-8')
        for line in ("combo.addItem(T('Во вкладке'), 'tab')",
                     "combo.addItem(T('В отдельном окне браузера'), 'window')",
                     "combo.addItem(T('В отдельном окне без панелей'), 'app')"):
            self.assertIn(line, source)

    def test_gui_uses_async_start_and_per_service_mode(self):
        source = (ROOT / 'gui.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        window = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'Window')
        methods = {x.name for x in window.body if isinstance(x, ast.FunctionDef)}
        for name in ('open_webui', 'open_office', 'open_service', 'create_browser_mode_combo', 'change_browser_mode'):
            self.assertIn(name, methods)
        self.assertIn('service_browser.ensure_ready(sid)', source)
        self.assertIn('service_browser.set_mode(sid, mode)', source)
        self.assertIn('service_browser.open_browser(url.strip(), mode)', source)


class TestWebUIFallback(unittest.TestCase):
    def test_cli_fallback_after_missing_systemd_unit(self):
        from types import SimpleNamespace
        failure = SimpleNamespace(returncode=1, stderr='Unit open-webui.service not found')
        fake_process = SimpleNamespace(pid=91234, poll=lambda: None)
        with mock.patch.object(core, 'verified', return_value=None), \
             mock.patch.object(core, 'port_open', return_value=False), \
             mock.patch.object(core, 'settings', return_value={'webui_service': 'open-webui.service'}), \
             mock.patch.object(core.shutil, 'which', return_value='/usr/bin/systemctl'), \
             mock.patch.object(core.subprocess, 'run', return_value=failure), \
             mock.patch.object(core, '_webui_cli', return_value='/home/test/.local/bin/open-webui'), \
             mock.patch.object(core, 'spawn', return_value=(fake_process, Path('/tmp/webui.log'))) as spawn:
            result = core.webui_start()
        self.assertIn('91234', result)
        self.assertEqual(spawn.call_args.args[0], 'webui')
        self.assertEqual(spawn.call_args.args[1], [
            '/home/test/.local/bin/open-webui', 'serve', '--host', '127.0.0.1', '--port', '3000'])

    def test_managed_cli_webui_is_stopped_on_full_exit(self):
        import shutdown_manager
        import multi
        import custom_services
        visits = []
        def owned(name):
            if name == 'webui':
                visits.append(name)
                return {'pid': 812} if len(visits) == 1 else None
            return None
        with mock.patch.object(multi, 'active_instances', return_value={}), \
             mock.patch.object(multi, 'all_states', return_value={}), \
             mock.patch.object(core, 'verified', side_effect=owned), \
             mock.patch.object(core, 'port_open', return_value=False), \
             mock.patch.object(custom_services, 'list_profiles', return_value=[]), \
             mock.patch.object(custom_services, 'STATE_DIR', Path('/tmp/nonexistent-ai-lab-custom-53713')), \
             mock.patch.object(shutdown_manager, '_unit_active', return_value=False), \
             mock.patch.object(core, 'webui_stop', return_value='webui: stopped') as stop:
            result = shutdown_manager.stop_all_managed()
        self.assertTrue(result['success'])
        self.assertIn('Open WebUI (managed CLI)', result['stopped'])
        stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
