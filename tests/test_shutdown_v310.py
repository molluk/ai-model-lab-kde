"""Shutdown contract tests without Qt or CUDA."""
import ast
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
import multi
import custom_services
import shutdown_manager


class TestFullShutdown(unittest.TestCase):
    def baseline(self):
        return [
            mock.patch.object(multi, 'active_instances', return_value={}),
            mock.patch.object(multi, 'all_states', return_value={}),
            mock.patch.object(core, 'verified', return_value=None),
            mock.patch.object(core, 'port_open', return_value=False),
            mock.patch.object(custom_services, 'list_profiles', return_value=[]),
            mock.patch.object(custom_services, 'STATE_DIR', Path('/tmp/ai-model-lab-tests-nonexistent-state-18c98bb')),
            mock.patch.object(shutdown_manager, '_unit_active', return_value=False),
        ]

    def test_no_managed_instances(self):
        with self.baseline()[0], self.baseline()[1], self.baseline()[2], self.baseline()[3], self.baseline()[4], self.baseline()[5], self.baseline()[6]:
            result = shutdown_manager.stop_all_managed()
            self.assertEqual(result, {'success': True, 'stopped': [], 'failed': [], 'external': []})

    def test_two_models_one_stays_alive_reports_failure(self):
        patches = self.baseline()
        with patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
             mock.patch.object(multi, 'active_instances', return_value={'blend-q4': {}, 'coder-30b': {}}), \
             mock.patch.object(multi, 'stop', return_value='SIGTERM sent') as stop, \
             mock.patch.object(multi, 'inspect', side_effect=lambda a: {'managed': True, 'alive': a == 'coder-30b'}):
            result = shutdown_manager.stop_all_managed()
        self.assertEqual(stop.call_count, 2)
        self.assertFalse(result['success'])
        self.assertEqual(len(result['stopped']), 1)
        self.assertIn('coder-30b', result['failed'][0])

    def test_external_port_is_never_killed(self):
        patches = self.baseline()
        with patches[0], patches[2], patches[4], patches[5], patches[6], \
             mock.patch.object(core, 'port_open', side_effect=lambda p: p == 3000), \
             mock.patch.object(multi, 'all_states', return_value={'foreign': {'state': 'external', 'port': 8083}}), \
             mock.patch.object(core, 'webui_stop') as stop_webui, \
             mock.patch.object(multi, 'stop') as stop_llama:
            result = shutdown_manager.stop_all_managed()
        self.assertTrue(result['success'])
        self.assertTrue(result['external'])
        stop_webui.assert_not_called()
        stop_llama.assert_not_called()

    def test_gui_fourth_action_and_nonblocking_worker(self):
        source = (ROOT / 'gui.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
        methods = {n.name for n in window.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'closeEvent', 'request_full_exit', 'on_shutdown_finished'}.issubset(methods))
        self.assertIn("T('Закрыть и остановить все')", source)
        self.assertIn('shutdown_manager.stop_all_managed()', source)
        self.assertIn('job = Worker(', source)


if __name__ == '__main__':
    unittest.main()
