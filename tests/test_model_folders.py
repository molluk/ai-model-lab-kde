"""Virtual-folder behavior and multi-column filtering without Qt or disk changes."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import model_folders


class ModelFoldersTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "model_root": "/mnt/Games/AI/Censored",
            "models": [
                {"id": "blend", "name": "Blend",
                 "path": "/mnt/Games/AI/Censored/Blend/Blend-Q4_K_M.gguf",
                 "context": 131072, "port": 8080, "purpose": "Android"},
                {"id": "huihui", "name": "[Uncensored] Huihui",
                 "path": "/mnt/Games/AI/Uncensored/Huihui/Qwen-Q4_K_M.gguf",
                 "context": 32768, "port": 8081, "purpose": "Experiment"},
                {"id": "manual", "name": "Custom", "path": "/mnt/elsewhere/model.gguf",
                 "context": 16384, "port": 8082, "purpose": "Review"}
            ],
            "server_bin": "/custom/llama-server",
            "preserve": {"flags": ["x", "y"]},
        }

    def test_inferred_and_unfiled_groups_without_writes(self):
        before = copy.deepcopy(self.config)
        self.assertEqual(model_folders.effective_folder(
            self.config["models"][0], self.config), "Censored")
        self.assertEqual(model_folders.effective_folder(
            self.config["models"][1], self.config), "Uncensored")
        self.assertEqual(model_folders.effective_folder(
            self.config["models"][2], self.config), model_folders.UNFILED)
        self.assertEqual(model_folders.list_folders(self.config),
                         ["Censored", "Uncensored"])
        self.assertEqual(model_folders.folder_counts(self.config),
                         {"Censored": 1, "Uncensored": 1,
                          model_folders.UNFILED: 1})
        self.assertEqual(self.config, before)

    def test_empty_folder_is_persistent_and_can_move_model(self):
        original = copy.deepcopy(self.config)
        added = model_folders.create_folder(self.config, "Android TV")
        self.assertIn("Android TV", model_folders.list_folders(added))
        self.assertEqual(model_folders.folder_counts(added).get("Android TV", 0), 0)
        moved = model_folders.move_model(added, "huihui", "Android TV")
        self.assertEqual(model_folders.effective_folder(moved["models"][1], moved),
                         "Android TV")
        self.assertEqual(moved["models"][1]["context"], 32768)
        self.assertEqual(moved["models"][1]["path"],
                         original["models"][1]["path"])
        self.assertEqual(moved["preserve"], original["preserve"])
        self.assertEqual(self.config, original)

    def test_rename_inferred_folder_does_not_regroup_back(self):
        renamed = model_folders.rename_folder(self.config, "Censored", "Основные")
        self.assertEqual(model_folders.effective_folder(renamed["models"][0], renamed),
                         "Основные")
        self.assertNotIn("Censored", model_folders.list_folders(renamed))
        self.assertIn("Основные", model_folders.list_folders(renamed))
        self.assertEqual(renamed["models"][0]["id"], "blend")

    def test_delete_inferred_folder_keeps_models_unfiled(self):
        result = model_folders.delete_folder(self.config, "Uncensored")
        self.assertEqual(len(result["models"]), len(self.config["models"]))
        self.assertNotIn("Uncensored", model_folders.list_folders(result))
        self.assertEqual(result["models"][1]["folder"], model_folders.UNFILED)
        self.assertEqual(model_folders.effective_folder(result["models"][1], result),
                         model_folders.UNFILED)

    def test_unfiled_override_of_inferred_group(self):
        changed = model_folders.move_model(self.config, "blend", model_folders.UNFILED)
        self.assertEqual(model_folders.effective_folder(changed["models"][0], changed),
                         model_folders.UNFILED)
        self.assertIn("Uncensored", model_folders.list_folders(changed))

    def test_duplicate_and_invalid_folder_names(self):
        for bad in ("", "  ", "A/B", "A\\B", "\n", "x" * 65,
                    model_folders.UNFILED):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    model_folders.create_folder(self.config, bad)
        with self.assertRaises(ValueError):
            model_folders.create_folder(self.config, "censored")
        with self.assertRaises(ValueError):
            model_folders.rename_folder(self.config, "Censored", "Uncensored")
        with self.assertRaises(ValueError):
            model_folders.move_model(self.config, "unknown", "Censored")
        with self.assertRaises(ValueError):
            model_folders.move_model(self.config, "blend", "unknown folder")

    def test_prefix_name_not_inferred(self):
        p = {"id": "x", "path": "/mnt/Games/AI/Uncensored-demo/model.gguf"}
        self.assertEqual(model_folders.effective_folder(p, self.config),
                         model_folders.UNFILED)

    def test_all_seven_column_filters_combine_and_casefold(self):
        row = ["Huihui Qwen3.8 27B", "○ Не запущена", "32K", "GPU-abc",
               "8081", "—", "Альтернативный анализ"]
        matches = ["qWeN", "зАпУщЕ", "32k", "gpu", "8081", "", "АЛЬТЕРНАТИВНЫЙ"]
        self.assertTrue(model_folders.matches_row("Uncensored", "Uncensored", row, matches))
        self.assertFalse(model_folders.matches_row("Uncensored", "Censored", row, matches))
        self.assertTrue(model_folders.matches_row("Uncensored", None, row, matches))
        changed = matches.copy()
        changed[4] = "8082"
        self.assertFalse(model_folders.matches_row("Uncensored", None, row, changed))
        with self.assertRaises(ValueError):
            model_folders.matches_row("Uncensored", None, row[:6], changed)

    def test_does_not_move_weights(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "model.gguf"
            file.write_bytes(b"GGUF_KEEP_WEIGHTS")
            cfg = copy.deepcopy(self.config)
            cfg["models"][0]["path"] = str(file)
            folder_cfg = model_folders.create_folder(cfg, "Test")
            moved = model_folders.move_model(folder_cfg, "blend", "Test")
            deleted = model_folders.delete_folder(moved, "Test")
            self.assertTrue(file.is_file())
            self.assertEqual(file.read_bytes(), b"GGUF_KEEP_WEIGHTS")
            self.assertEqual(deleted["models"][0]["path"], str(file))


if __name__ == "__main__":
    unittest.main()
