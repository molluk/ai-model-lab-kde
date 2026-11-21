"""Cross-platform smoke tests for the first Windows portability milestone."""
from pathlib import Path
import importlib
import os
import tempfile
import unittest

import platform_paths
from platform_lock import exclusive_lock


class PathsTest(unittest.TestCase):
    def test_linux_preserves_existing_user_state_layout(self):
        existing = Path('/home/example/AI/AI-Model-Lab')
        self.assertEqual(platform_paths.user_root(existing, platform_name='posix'), existing)

    def test_windows_user_data_outside_bundle(self):
        folder = platform_paths.user_root(
            Path('C:/Program Files/AI-Model-Lab'),
            platform_name='nt',
            environ={'LOCALAPPDATA': r'C:\Users\tester\AppData\Local'},
            home=Path('C:/Users/tester')
        )
        self.assertEqual(folder.name, 'AI-Model-Lab')
        self.assertIn('Local', str(folder))
        self.assertNotIn('Program Files', str(folder))

    def test_windows_fallback_when_localappdata_missing(self):
        folder = platform_paths.user_root(
            Path('ignored'), platform_name='nt', environ={},
            home=Path('fake-home'))
        self.assertEqual(folder, Path('fake-home/AppData/Local/AI-Model-Lab'))

    def test_lock_context_is_usable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'model.lock'
            with path.open('a+b') as handle:
                with exclusive_lock(handle):
                    handle.seek(0, os.SEEK_END)
                    handle.write(b'X')

    def test_non_qt_modules_import_on_windows_and_linux(self):
        for name in ('core', 'multi', 'custom_services', 'service_browser',
                     'client_launcher', 'shutdown_manager'):
            with self.subTest(name=name):
                importlib.import_module(name)

    def test_existing_config_names_not_changed(self):
        import core
        self.assertEqual(core.MODELS.name, 'models.json')
        self.assertEqual(core.SETTINGS.name, 'settings.json')
        self.assertEqual(core.DATA.name, 'data')
        if os.name == 'nt':
            self.assertEqual(core.USER_ROOT.name, 'AI-Model-Lab')
        else:
            self.assertEqual(core.USER_ROOT, core.ROOT)


if __name__ == '__main__':
    unittest.main()
