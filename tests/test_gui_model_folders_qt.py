"""Offscreen GUI integration: context folders, favorites and header filters."""
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
    def test_tree_favorites_header_filter_and_folder_crud(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtCore import Qt, QRect, QPoint, QPointF, QMimeData
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QPushButton
        import core
        import custom_services
        import gui
        import model_folders
        import multi

        app = QApplication.instance() or QApplication(["ai-lab-tree-integration"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_file = root / "models.json"
            profiles = [
                {"id": "blend", "name": "Blend Q4",
                 "path": "/mnt/Games/AI/Censored/Blend/model.gguf",
                 "context": 131072, "port": 8080, "purpose": "Android TV"},
                {"id": "qwen", "name": "[Uncensored] Qwen3.8",
                 "path": "/mnt/Games/AI/Uncensored/Qwen/model.gguf",
                 "context": 32768, "port": 8081, "purpose": "Эксперименты"},
            ]
            models_file.write_text(json.dumps({
                "version": "3.7",
                "model_root": "/mnt/Games/AI/Censored",
                "server_bin": "/tmp/no-llama-server",
                "models": profiles,
            }, ensure_ascii=False), encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text(
                '{"language":"ru","logs_retention_days":0,"reports_retention_days":0}',
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
                    window.show()
                    app.processEvents()
                    self.assertEqual(window.tree.topLevelItemCount(), 2)
                    self.assertEqual(len(list(window.iter_model_items())), 2)
                    self.assertFalse(hasattr(window, "folder_selector"))
                    self.assertFalse(hasattr(window, "model_filter_edits"))
                    self.assertTrue(window.tree.rootIsDecorated())

                    # At the smallest supported window, buttons must not overlap
                    # the model tree or each other (previous screenshot regression).
                    window.resize(980, 680)
                    app.processEvents()
                    tree_rect = QRect(window.tree.mapToGlobal(QPoint(0, 0)),
                                      window.tree.size())
                    actions = [button for button in window.tree.parentWidget().findChildren(QPushButton)
                               if button.text() in ('＋ Добавить', '⧉ Клонировать',
                                                    '－ Удалить', '✎ Изменить',
                                                    '🔎 Найти GGUF', '🛠 Профили')]
                    self.assertEqual(len(actions), 6)
                    areas = [QRect(button.mapToGlobal(QPoint(0, 0)), button.size())
                             for button in actions]
                    for area in areas:
                        self.assertFalse(area.intersects(tree_rect),
                                         'Model toolbar overlaps the list')
                    for idx, rect in enumerate(areas):
                        for another in areas[idx + 1:]:
                            self.assertFalse(rect.intersects(another),
                                             'Model toolbar buttons overlap')

                    self.assertIn("Censored", model_folders.list_folders(window.cfg))
                    self.assertIn("Uncensored", model_folders.list_folders(window.cfg))
                    self.assertIsNotNone(window.first_visible_model_item())

                    # Numerical sorting is per-folder, and both model rows remain.
                    window.tree.sortItems(2, Qt.SortOrder.AscendingOrder)
                    self.assertEqual(len(list(window.iter_model_items())), 2)
                    # Header-popup filtering, not seven permanent text fields.
                    for col, value in enumerate(
                            ["[Uncensored] Qwen3.8", "Не запущена", "32K", "авто",
                             "8081", "—", "Эксперименты"]):
                        values = {item.text(col) for item in window.iter_model_items()}
                        if value == "Не запущена":
                            match_value = next(v for v in values if "Не запущена" in v)
                        else:
                            match_value = value
                        self.assertIn(match_value, values)
                        with mock.patch.object(gui, "ColumnFilterPopup") as pop:
                            obj = pop.return_value
                            obj.exec.return_value = QDialog.DialogCode.Accepted
                            obj.selected_values.return_value = {match_value}
                            obj.sort_order = None
                            window.open_model_column_filter(col)
                        self.assertEqual(window.column_filters[col], {match_value})
                    visible = [item for item in window.iter_model_items()
                               if not item.isHidden() and not item.parent().isHidden()]
                    self.assertEqual(len(visible), 1)
                    self.assertEqual(visible[0].data(
                        0, Qt.ItemDataRole.UserRole), "qwen")
                    self.assertIn("●", window.tree.headerItem().text(0))
                    window.column_filters.clear()
                    window.apply_model_filters()

                    # Favorite indicator + persistent metadata.
                    window.toggle_model_favorite("blend")
                    saved = json.loads(models_file.read_text(encoding="utf-8"))
                    self.assertTrue(next(p for p in saved["models"]
                                         if p["id"] == "blend")["favorite"])
                    blend_item = next(item for item in window.iter_model_items()
                                      if item.data(0, Qt.ItemDataRole.UserRole) == "blend")
                    self.assertTrue(blend_item.text(0).startswith("★ "))

                    # Create folder, drag/drop handler, rename, delete via context actions.
                    with mock.patch.object(gui.QInputDialog, "getText",
                                           return_value=("Проекты", True)):
                        window.create_model_folder()
                    self.assertIn("Проекты", model_folders.list_folders(window.cfg))
                    # Exercise real tree.dropEvent using a synthetic Qt drop.
                    source = next(item for item in window.iter_model_items()
                                  if item.data(0, Qt.ItemDataRole.UserRole) == "qwen")
                    window.tree.setCurrentItem(source)
                    target_root = next(window.tree.topLevelItem(i)
                                       for i in range(window.tree.topLevelItemCount())
                                       if window.tree.topLevelItem(i).data(
                                           0, gui.FOLDER_ROLE) == "Проекты")
                    window.tree.scrollToItem(target_root)
                    app.processEvents()
                    drop_position = window.tree.visualItemRect(target_root).center()
                    drop_event = QDropEvent(
                        QPointF(drop_position), Qt.DropAction.MoveAction,
                        QMimeData(), Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
                    window.tree.dropEvent(drop_event)
                    self.assertTrue(drop_event.isAccepted())
                    moved = next(p for p in window.cfg["models"] if p["id"] == "qwen")
                    self.assertEqual(moved["folder"], "Проекты")
                    self.assertEqual(moved["context"], 32768)
                    self.assertEqual(moved["port"], 8081)

                    with mock.patch.object(gui.QInputDialog, "getText",
                                           return_value=("Android проекты", True)):
                        window.rename_model_folder("Проекты")
                    self.assertIn("Android проекты", model_folders.list_folders(window.cfg))
                    with mock.patch.object(gui.QMessageBox, "question",
                                           return_value=QMessageBox.StandardButton.Yes):
                        window.delete_model_folder("Android проекты")
                    final = json.loads(models_file.read_text(encoding="utf-8"))
                    self.assertEqual(len(final["models"]), 2)
                    qwen = next(p for p in final["models"] if p["id"] == "qwen")
                    self.assertEqual(qwen["folder"], model_folders.UNFILED)
                    self.assertEqual(qwen["path"], profiles[1]["path"])
                    self.assertTrue((data / "backups").is_dir())
                    window.refresh_status()
                finally:
                    window.exit_requested = True
                    window.close()
                    window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
