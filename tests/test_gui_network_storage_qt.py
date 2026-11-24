"""Actual Qt smoke: per-model network mode and user-approved storage cleanup."""
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
class NetworkAndStorageGuiTest(unittest.TestCase):
    def test_network_toggle_and_storage_cleanup_preserve_config(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
        import core
        import custom_services
        import gui
        import multi

        app = QApplication.instance() or QApplication(["ai-lab-security-smoke"])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Model-Lab"
            root.mkdir()
            (root / "gui.py").write_text("# marker\n")
            (root / "core.py").write_text("# marker\n")
            model_path = root / "models.json"
            model_path.write_text(json.dumps({
                "version": "3.7",
                "model_root": str(root),
                "server_bin": "/not/installed/llama-server",
                "models": [{
                    "id": "my-model", "name": "Test model",
                    "context": 32768, "port": 8084, "gpu": "",
                    "path": str(root / "absent.gguf"),
                    "purpose": "Testing", "favorite": False
                }]
            }), encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text(json.dumps({"language": "ru",
                                            "logs_retention_days": 0,
                                            "reports_retention_days": 0}),
                                encoding="utf-8")
            cache = root / "data/cache/old.cache"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"CACHE")
            log = root / "data/logs/test.log"
            log.parent.mkdir(parents=True)
            log.write_bytes(b"LOG")
            saved_report = root / "data/reports/task1/summary.json"
            saved_report.parent.mkdir(parents=True)
            saved_report.write_text("{}")
            with mock.patch.object(core, "ROOT", root), \
                 mock.patch.object(core, "MODELS", model_path), \
                 mock.patch.object(core, "SETTINGS", settings), \
                 mock.patch.object(core, "DATA", root / "data"), \
                 mock.patch.object(core, "LOGS", root / "data/logs"), \
                 mock.patch.object(core, "REPORTS", root / "data/reports"), \
                 mock.patch.object(core, "port_open", return_value=False), \
                 mock.patch.object(multi, "INSTANCES", root / "data/instances"), \
                 mock.patch.object(custom_services, "STATE_DIR", root / "data/custom"):
                window = gui.Window()
                try:
                    window.show()
                    app.processEvents()
                    selected = window.selected_alias()
                    self.assertEqual(selected, "my-model")
                    self.assertIn("интернет разрешён", window.model_network_btn.text())

                    # Confirm actual UI toggle, preserve all other profile fields.
                    original = json.loads(model_path.read_text())
                    with mock.patch.object(gui.QMessageBox, "question",
                                           return_value=QMessageBox.StandardButton.Yes):
                        window.toggle_selected_client_network()
                    updated = json.loads(model_path.read_text())
                    self.assertEqual(updated["models"][0]["client_network"], "offline")
                    self.assertEqual(updated["models"][0]["context"], 32768)
                    self.assertEqual(updated["models"][0]["port"], 8084)
                    self.assertEqual(updated["models"][0]["path"],
                                     original["models"][0]["path"])
                    self.assertIn("интернет выключен", window.model_network_btn.text())

                    with mock.patch.object(gui.QMessageBox, "question",
                                           return_value=QMessageBox.StandardButton.Yes):
                        window.toggle_selected_client_network()
                    self.assertEqual(json.loads(model_path.read_text())["models"][0][
                        "client_network"], "online")

                    # Cleanup defaults to cache only. The dialog is accepted
                    # without turning on log or backup deletion.
                    def async_inline(_label, fn, after=None):
                        result = fn()
                        if after:
                            after(True, result)
                    with mock.patch.object(gui.QDialog, "exec",
                                           return_value=QDialog.DialogCode.Accepted), \
                         mock.patch.object(gui.QMessageBox, "question",
                                           return_value=QMessageBox.StandardButton.Yes), \
                         mock.patch.object(gui.QMessageBox, "information"), \
                         mock.patch.object(window, "async_call",
                                           side_effect=async_inline):
                        window.open_storage_cleanup()

                    self.assertFalse(cache.exists())
                    self.assertTrue(log.exists())
                    self.assertTrue(settings.exists())
                    self.assertTrue(model_path.exists())
                    self.assertTrue(saved_report.exists())
                    self.assertEqual(json.loads(model_path.read_text())["models"][0][
                        "client_network"], "online")
                finally:
                    window.exit_requested = True
                    window.close()
                    window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
