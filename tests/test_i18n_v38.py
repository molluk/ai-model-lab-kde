"""No-Qt tests for file-based Russian/English localization."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
import i18n

class TestLocalization(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('ru')

    def test_catalogs_and_menu(self):
        choices = dict(i18n.available_languages())
        self.assertIn('ru', choices)
        self.assertIn('en', choices)
        self.assertTrue((ROOT / 'locales/en.json').is_file())
        catalog = json.loads((ROOT / 'locales/en.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(catalog['translations']), 280)

    def test_translation_and_unknown_fallback(self):
        i18n.set_language('en')
        self.assertEqual(i18n.T('🧠 Модели'), '🧠 Models')
        self.assertEqual(i18n.T('⚙ Управление'), '⚙ Services')
        self.assertEqual(i18n.T('Логика / арифметика (3 задачи)'), 'Logic / arithmetic (3 tasks)')
        self.assertEqual(i18n.T('AI Model Lab — KDE · работающих моделей: 2'), 'AI Model Lab — KDE · running models: 2')
        self.assertEqual(i18n.T('Без перевода xyz'), 'Без перевода xyz')
        i18n.set_language('ru')
        self.assertEqual(i18n.T('⚙ Управление'), '⚙ Управление')

    def test_language_setting_persists_without_erasing_other_settings(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / 'settings.json'
            settings.write_text(json.dumps({'model_root': '/somewhere', 'tool_budget': 24}), encoding='utf-8')
            with mock.patch.object(core, 'SETTINGS', settings), mock.patch.object(core, 'DATA', Path(td)/'data'), mock.patch.object(core, 'LOGS', Path(td)/'data/logs'), mock.patch.object(core, 'REPORTS', Path(td)/'data/reports'):
                saved = core.settings()
                saved['language'] = 'en'
                core.atomic_json(core.SETTINGS, saved)
                self.assertEqual(core.settings()['language'], 'en')
                self.assertEqual(core.settings()['tool_budget'], 24)

    def test_gui_language_menu_and_packaging(self):
        source = (ROOT / 'gui.py').read_text(encoding='utf-8')
        installer = (ROOT / 'install.sh').read_text(encoding='utf-8')
        self.assertIn('self.language_combo = QComboBox()', source)
        self.assertIn('def switch_language(self, _index)', source)
        self.assertIn('state[\'language\'] = language', source)
        self.assertIn('i18n.py', installer)
        self.assertIn('locales', installer)

if __name__ == '__main__':
    unittest.main()
