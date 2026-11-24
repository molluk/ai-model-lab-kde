"""Release and compatibility checks independent of Qt GUI bindings."""
import tempfile
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import client_launcher
import core
import release_preflight


class TestRelease(unittest.TestCase):
    def test_css_fstring_is_valid_and_rendered(self):
        style = release_preflight.check_source(ROOT)
        self.assertIn('QPushButton#Danger { background:', style)
        self.assertIn('QPushButton#Slim { padding:', style)
        self.assertNotIn('{{', style)

    def test_css_regression_detects_invalid_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ('gui.py', 'core.py', 'multi.py', 'model_catalog.py', 'version_info.py', 'bench.py', 'client_launcher.py', 'pi_bridge_manager.py', 'custom_services.py', 'shutdown_manager.py', 'service_browser.py'):
                (root / name).write_text((ROOT / name).read_text())
            path = root / 'gui.py'
            path.write_text(path.read_text().replace(
                'QPushButton#Danger {{ background:#63333b;border:1px solid #ae5364; }}',
                'QPushButton#Danger { background:#63333b;border:1px solid #ae5364; }'))
            with self.assertRaises(RuntimeError):
                release_preflight.check_source(root)

    def test_preferred_client_defaults_for_legacy_profiles(self):
        self.assertEqual(client_launcher.preferred_client({'id':'blend-q4'}), 'pi')
        self.assertEqual(client_launcher.preferred_client({'id':'coder-30b'}), 'opencode')
        self.assertEqual(client_launcher.preferred_client({'id':'devstral-24b'}), 'opencode')
        self.assertEqual(client_launcher.preferred_client({'id':'coder-30b','preferred_client':'pi'}), 'pi')
        self.assertEqual(client_launcher.preferred_client({'id':'blend-q4','preferred_client':'opencode'}), 'opencode')
        self.assertEqual(client_launcher.preferred_client({'id':'blend-q4','preferred_client':'unknown'}), 'pi')
        self.assertEqual(client_launcher.preferred_client(None), 'pi')

    def test_new_profiles_use_explicit_preference(self):
        example_profiles=core.load_json(ROOT / 'models.example.json', {})['models']
        for profile in example_profiles:
            self.assertIn(profile['preferred_client'], client_launcher.CLIENTS)
        coder = next((p for p in example_profiles if p['id']=='coder-30b'), None)
        if coder:
            self.assertEqual(coder['preferred_client'], 'opencode')

    def test_public_examples_exist(self):
        self.assertTrue((ROOT / 'models.example.json').is_file())
        self.assertTrue((ROOT / 'settings.example.json').is_file())


if __name__ == '__main__':
    unittest.main()
