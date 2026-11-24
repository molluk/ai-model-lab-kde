"""Real PySide6 offscreen integration of model folders and column sorting/filters."""
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


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 missing")
class QtModelFoldersTest(unittest.TestCase):
    def test_folder_crud_sorting_and_simultaneous_seven_filters(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
        import core
        import custom_services
        import gui
        import model_folders
        import multi

        app = QApplication.instance() or QApplication(["ai-lab-folder-integration"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_file = root / "models.json"
            models_file.write_text(json.dumps({
                "version": "3.7",
                "model_root": "/mnt/Games/AI/Censored",
                "server_bin": "/tmp/no-llama-server",
                "models": [
                    {"id": "blend", "name": "Blend Q4",
                     "path": "/mnt/Games/AI/Censored/Blend/model.gguf",
                     "context": 131072, "port": 8080, "purpose": "Android TV"},
                    {"id": "qwen", "name": "[Uncensored] Qwen3.8",
                     "path": "/mnt/Games/AI/Uncensored/Qwen/model.gguf",
                     "context": 32768, "port": 8081, "purpose": "Эксперименты"},
                ]
            }, ensure_ascii=False), encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text('{"language":"ru","logs_retention_days":0,"reports_retention_days":0}',
                                encoding="utf-8")
            data = root / "data"
            with mock.patch.object(core, "MODELS", models_file), \
                 mock.patch.object(core, "SETTINGS", settings), \
                 mock.patch.object(core, "DATA", data), \
                 mock.patch.object(core, "LOGS", data / "logs"), \
                 mock.patch.object(core, "REPORTS", data / "reports"), \
                 mock.patch.object(core, "port_open", return_value=False), \
                 mock.patch.object(multi, "INSTANCES", data / "instances"), \
                 mock.patch.object(custom_services, "STATE_DIR", data / "custom"):
                window = gui.Window()
                try:
                    self.assertEqual(window.tree.topLevelItemCount(), 2)
                    self.assertEqual(len(window.model_filter_edits), 7)
                    self.assertIn("Censored", model_folders.list_folders(window.cfg))
                    self.assertIn("Uncensored", model_folders.list_folders(window.cfg))
                    self.assertEqual(window.folder_selector.count(), 4)

                    window.tree.sortItems(2, Qt.SortOrder.AscendingOrder)
                    self.assertEqual(window.tree.topLevelItem(0).data(
                        0, Qt.ItemDataRole.UserRole), "qwen")
                    window.tree.sortItems(4, Qt.SortOrder.DescendingOrder)
                    self.assertEqual(window.tree.topLevelItem(0).data(
                        0, Qt.ItemDataRole.UserRole), "qwen")

                    # All seven filters restrict the same row at once.
                    predicates = ["qwen", "не запущена", "32k", "авто",
                                  "8081", "—", "эксперименты"]
                    for field, search in zip(window.model_filter_edits, predicates):
                        field.setText(search)
                    visible = [window.tree.topLevelItem(i) for i in range(2)
                               if not window.tree.topLevelItem(i).isHidden()]
                    self.assertEqual(len(visible), 1)
                    self.assertEqual(visible[0].data(
                        0, Qt.ItemDataRole.UserRole), "qwen")
                    window.model_filter_edits[4].setText("9999")
                    self.assertTrue(all(window.tree.topLevelItem(i).isHidden()
                                        for i in range(2)))
                    window.model_filter_edits[4].setText("8081")

                    with mock.patch.object(gui.QInputDialog, "getText",
                                           return_value=("Проекты", True)):
                        window.create_model_folder()
                    self.assertIn("Проекты", model_folders.list_folders(window.cfg))
                    self.assertEqual(json.loads(models_file.read_text())["model_folders"],
                                     model_folders.list_folders(window.cfg))
                    self.assertTrue((data / "backups").is_dir())

                    # Change folder selection back to the model's original folder.
                    ix = window.folder_selector.findData("Uncensored")
                    window.folder_selector.setCurrentIndex(ix)
                    qwen = next(window.tree.topLevelItem(i) for i in range(2)
                                if window.tree.topLevelItem(i).data(
                                    0, Qt.ItemDataRole.UserRole) == "qwen")
                    window.tree.setCurrentItem(qwen)
                    with mock.patch.object(gui.QInputDialog, "getItem",
                                           return_value=("Проекты", True)):
                        window.move_selected_model_folder()
                    saved = json.loads(models_file.read_text())
                    moved = next(p for p in saved["models"] if p["id"] == "qwen")
                    self.assertEqual(moved["folder"], "Проекты")
                    self.assertEqual(moved["context"], 32768)
                    self.assertEqual(moved["port"], 8081)
                    self.assertEqual(len(saved["models"]), 2)

                    with mock.patch.object(gui.QInputDialog, "getText",
                                           return_value=("Android проекты", True)):
                        window.rename_model_folder()
                    self.assertIn("Android проекты", model_folders.list_folders(window.cfg))
                    with mock.patch.object(gui.QMessageBox, "question",
                                           return_value=QMessageBox.StandardButton.Yes):
                        window.delete_model_folder()
                    final = json.loads(models_file.read_text())
                    self.assertEqual(len(final["models"]), 2)
                    qwen = next(p for p in final["models"] if p["id"] == "qwen")
                    self.assertEqual(qwen["folder"], model_folders.UNFILED)
                    self.assertEqual(qwen["path"],
                                     "/mnt/Games/AI/Uncensored/Qwen/model.gguf")
                    window.refresh_status()
                finally:
                    window.exit_requested = True
                    window.close()
                    window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
