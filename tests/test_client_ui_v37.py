"""v3.7 regressions that run without a Qt installation."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
import release_preflight


class TestClientPreference(unittest.TestCase):
    def test_update_client_without_running_model(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            source = home / 'models.json'
            source.write_text(json.dumps({
                'models': [
                    {'id': 'blend-q4', 'name': 'Blend', 'context': 131072},
                    {'id': 'coder-30b', 'name': 'Coder', 'preferred_client': 'pi'}
                ]}), encoding='utf-8')
            with mock.patch.object(core, 'DATA', home/'data'), \
                 mock.patch.object(core, 'LOGS', home/'data/logs'), \
                 mock.patch.object(core, 'REPORTS', home/'data/reports'), \
                 mock.patch.object(core, 'MODELS', source):
                updated = core.update_model_client_preference('blend-q4', 'opencode')
                self.assertEqual(updated['models'][0]['preferred_client'], 'opencode')
                self.assertEqual(updated['models'][1]['preferred_client'], 'pi')
                again = core.load_json(source)
                self.assertEqual(again, updated)
                self.assertTrue(list((home/'data/backups').glob('models_client_*.json')))
                with self.assertRaises(ValueError):
                    core.update_model_client_preference('blend-q4', 'invalid')
                with self.assertRaises(ValueError):
                    core.update_model_client_preference('no-such-model', 'pi')

    def test_real_css_renders_selected_background(self):
        result = release_preflight.check_source(ROOT)
        self.assertIn('QTreeWidget::item:selected { background:#235b94', result)
        self.assertIn('QTreeWidget::item:selected:!active { background:#285176', result)

    def test_gui_separate_button_and_combo(self):
        tree = ast.parse((ROOT/'gui.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Window')
        methods = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
        for name in ('on_client_preference_changed', 'open_model_client',
                     'show_missing_client_help', 'open_webui', 'open_office'):
            self.assertIn(name, methods)
        source = (ROOT/'gui.py').read_text()
        self.assertIn('self.client_combo = QComboBox()', source)
        self.assertIn("btn('⌘ Открыть в', self.open_preferred_client", source)
        self.assertNotIn('self.client_menu_button = QToolButton()', source)
        self.assertIn('core.update_model_client_preference(alias, client)', source)
        self.assertIn('self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)', source)


if __name__ == '__main__':
    unittest.main()
