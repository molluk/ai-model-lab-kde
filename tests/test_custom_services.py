"""Custom service management regression tests (no PySide6 required)."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
import custom_services as cs


class CustomServicesTest(unittest.TestCase):
    def test_validation_and_no_shell(self):
        p = cs.validate({
            'id': 'example-ai', 'name': 'Example AI',
            'command': "python3 -u 'server file.py' --port 8090",
            'health_url': 'http://127.0.0.1:8090/health',
        })
        self.assertEqual(p['command'], ['python3', '-u', 'server file.py', '--port', '8090'])
        for bad in ('', '../other', 'llama', 'office', 'name; rm -rf /'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    cs.validate({**p, 'id': bad})
        with self.assertRaises(ValueError):
            cs.validate({**p, 'health_url': 'https://example.com/check'})

    def test_config_persists_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cs, 'FILE', Path(tmp) / 'services.json'):
                example = {'id': 'local', 'name': 'Local', 'command': ['python3', '--version']}
                cs.save_profiles([example])
                self.assertEqual(cs.list_profiles()[0]['name'], 'Local')
                with self.assertRaises(ValueError):
                    cs.save_profiles([example, example])

    def test_unowned_pid_is_never_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cs, 'STATE_DIR', Path(tmp)):
                core.atomic_json(cs.meta_path('foreign'), {
                    'pid': 123456, 'ticks': 23, 'exe': '/bin/python3',
                    'argv': ['python3', '-u', 'foo.py'], 'state': 'running',
                })
                self.assertIn('nothing stopped', cs.stop('foreign'))

    def test_real_process_start_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = {
                'id': 'sleeper', 'name': 'Test Sleeper',
                'command': [sys.executable, '-u', '-c', 'import time; time.sleep(10)'],
                'cwd': tmp,
            }
            with patch.object(cs, 'FILE', root / 'services.json'), \
                 patch.object(cs, 'STATE_DIR', root / 'instances'), \
                 patch.object(core, 'LOGS', root / 'logs'), \
                 patch.object(core, 'DATA', root / 'data'):
                cs.save_profiles([profile])
                cs.start('sleeper')
                self.assertTrue(cs.inspect('sleeper')['managed'])
                msg = cs.stop('sleeper')
                self.assertIn('stopped', msg)
                self.assertFalse(cs.inspect('sleeper')['managed'])


if __name__ == '__main__':
    unittest.main()
