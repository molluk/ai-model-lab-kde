"""No-Qt release checks for service UX and licensing."""
from pathlib import Path
import ast
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ServicesUITest(unittest.TestCase):
    def test_single_builtin_toggle_and_custom_controls(self):
        source = (ROOT / 'gui.py').read_text(encoding='utf-8')
        code = ast.parse(source)
        window = next(n for n in code.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
        method_names = {n.name for n in window.body if isinstance(n, ast.FunctionDef)}
        for name in ('toggle_builtin_service', 'update_builtin_services', 'toggle_custom_service',
                     'edit_service_dialog', 'add_custom_service', 'edit_custom_service',
                     'delete_custom_service', 'refresh_custom_services'):
            self.assertIn(name, method_names)
        self.assertIn('self.service_buttons[sid] = toggle', source)
        self.assertIn('self.refresh_custom_services()', source)

    def test_polyform_license_and_required_notice(self):
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        notice = (ROOT / 'NOTICE').read_text(encoding='utf-8')
        self.assertIn('PolyForm Noncommercial License 1.0.0', license_text)
        self.assertIn('Noncommercial Purposes', license_text)
        self.assertTrue(any(line.startswith('Required Notice:') for line in notice.splitlines()))
        self.assertTrue((ROOT / 'docs' / 'LICENSING_HISTORY.md').is_file())

    def test_install_preserves_custom_profiles(self):
        install = (ROOT / 'install.sh').read_text(encoding='utf-8')
        self.assertIn('custom_services.py', install)
        self.assertIn('if [[ ! -f "$DEST/services.json" ]]', install)
        self.assertTrue((ROOT / 'services.example.json').is_file())
        example = json.loads((ROOT / 'services.example.json').read_text(encoding='utf-8'))
        self.assertEqual(example['services'], [])

if __name__ == '__main__':
    unittest.main()
