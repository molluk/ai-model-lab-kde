"""Actual Qt startup regression for a real models.json with an 88-character alias.

This test is skipped in the stdlib-only CI matrix and executed in the dedicated
PySide6/offscreen job. No processes/models are started and no user data is read.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 not installed")
class QtStartupSmokeTest(unittest.TestCase):
    def test_window_opens_with_invalid_legacy_alias(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        import core
        import custom_services
        import gui
        import multi

        app = QApplication.instance() or QApplication(["ai-model-lab-test"])
        bad = "uncensored-" + "very-long-ai-model-name-" * 5
        self.assertGreater(len(bad), 80)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "models.json"
            config.write_text(json.dumps({
                "version": "3.7",
                "model_root": str(root),
                "server_bin": "/does-not-exist/llama-server",
                "models": [
                    {"id": bad, "name": "Previously imported invalid model",
                     "path": str(root / "not-present.gguf"),
                     "context": 32768, "port": 8081,
                     "purpose": "Импортирован из Uncensored"},
                    {"id": "normal-model", "name": "Working profile",
                     "path": str(root / "valid.gguf"), "context": 32768,
                     "port": 8082, "purpose": "Code"}
                ],
            }), encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text('{"language":"ru","logs_retention_days":0,"reports_retention_days":0}',
                                encoding="utf-8")
            data = root / "data"
            with mock.patch.object(core, "MODELS", config), \
                 mock.patch.object(core, "SETTINGS", settings), \
                 mock.patch.object(core, "DATA", data), \
                 mock.patch.object(core, "LOGS", data / "logs"), \
                 mock.patch.object(core, "REPORTS", data / "reports"), \
                 mock.patch.object(multi, "INSTANCES", data / "instances"), \
                 mock.patch.object(custom_services, "STATE_DIR", data / "custom_services"):
                window = gui.Window()
                try:
                    models = list(window.iter_model_items())
                    self.assertEqual(len(models), 2)
                    aliases = [item.data(0, Qt.ItemDataRole.UserRole)
                               for item in models]
                    self.assertIn(bad, aliases)
                    invalid_item = models[aliases.index(bad)]
                    self.assertIn("Исправить ID", invalid_item.text(2))
                    self.assertIsNotNone(invalid_item.parent())
                    window.refresh_status()
                finally:
                    window.exit_requested = True
                    window.close()
                    window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
