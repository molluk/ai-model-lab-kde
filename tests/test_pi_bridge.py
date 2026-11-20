"""Global/isolated Pi bridge installation and launcher regression tests."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import client_launcher
import core
import pi_bridge_manager as manager

INFO = {'alias': 'blend-q4', 'name': 'Blend Q4', 'port': 8081, 'context': 131072,
        'url': 'http://127.0.0.1:8081/v1', 'mmproj': False}


class TestPiBridge(unittest.TestCase):
    def test_extension_events_headless(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js not installed')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, 'tests/pi_bridge_runtime.test.mjs'],
                                cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_optional_global_symlink_safe_install_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            src = Path(tmp) / 'program' / 'extensions' / 'pi-office-bridge.js'
            src.parent.mkdir(parents=True)
            src.write_text('// trusted fixture')
            with mock.patch.object(core, 'HOME', home), mock.patch.object(core, 'ROOT', src.parents[1]):
                self.assertTrue(manager.needs_explicit_extension())
                target = manager.install_global()
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), src)
                self.assertTrue(manager.is_bridge_installed())
                self.assertFalse(manager.needs_explicit_extension())
                self.assertEqual(manager.install_global(), target)
                self.assertTrue(manager.uninstall_global())
                self.assertFalse(target.exists())
                target.write_text('existing user extension')
                with self.assertRaises(FileExistsError):
                    manager.install_global()
                with self.assertRaises(FileExistsError):
                    manager.uninstall_global()
                self.assertEqual(target.read_text(), 'existing user extension')

    def test_pi_launcher_includes_extension_for_isolated_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(client_launcher, 'pi_global_matches', return_value=False), \
                 mock.patch.object(core, 'DATA', Path(tmp) / 'data'):
                argv, env, _ = client_launcher.build_command(INFO, 'pi', '/usr/bin/pi')
            self.assertEqual(argv[:2], ['/usr/bin/pi', '--extension'])
            self.assertEqual(Path(argv[2]).name, 'pi-office-bridge.js')
            self.assertIn('PI_CODING_AGENT_DIR', env)
            self.assertEqual(argv[3:5], ['--provider', 'ai-model-lab'])

    def test_pi_launcher_avoids_duplicate_when_extension_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            global_dir = home / '.pi' / 'agent' / 'extensions'
            global_dir.mkdir(parents=True)
            (global_dir / manager.BRIDGE_FILENAME).write_text('existing observer')
            with mock.patch.object(core, 'HOME', home), \
                 mock.patch.object(client_launcher, 'pi_global_matches', return_value=True):
                argv, env, _ = client_launcher.build_command(INFO, 'pi', '/usr/bin/pi')
            self.assertNotIn('--extension', argv)
            self.assertEqual(argv[1:3], ['--provider', 'local-lab'])


if __name__ == '__main__':
    unittest.main()
