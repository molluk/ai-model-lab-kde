"""Safe model profile cleanup/tuning tests: no CUDA or Qt required."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import model_maintenance as maintenance
import model_catalog


class TestModelMaintenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.censored = self.home / "Censored"
        self.uncensored = self.home / "Uncensored"
        self.censored.mkdir()
        self.uncensored.mkdir()

    def add_model(self, directory, family, filename):
        parent = directory / family
        parent.mkdir(exist_ok=True, parents=True)
        file = parent / filename
        file.write_bytes(b"GGUF" + b"x" * 64)
        return file

    def settings(self, profiles):
        return {
            "model_root": str(self.censored),
            "models": copy.deepcopy(profiles),
            "server_bin": "~/bin/llama-server",
            "unchanged": {"value": 200},
        }

    def test_imported_profiles_receive_meaningful_purpose_and_start_preset(self):
        file = self.add_model(self.uncensored, "Unsloth Qwen3.8-27B",
                              "Qwen3.8-27B-Q5_K_M.gguf")
        imported = {
            "id": "uncensored-unsloth-q5",
            "name": "[Uncensored] Unsloth Qwen3.8-27B",
            "purpose": "Импортирован из Uncensored; параметры проверить перед запуском",
            "path": str(file),
            "port": 8089,
            "context": 32768,
            "ngl": 99,
            "preferred_client": "pi",
            "extra_args": ["--some-existing-setting"],
        }
        original = self.settings([imported])
        with mock.patch.object(maintenance, "_size_gib", return_value=20.2):
            plan = maintenance.plan_maintenance(
                original, roots=[self.censored, self.uncensored],
                hardware={"uuid": "GPU-1234", "vram_gib": 22.0})
        result = plan["config"]["models"][0]
        self.assertIn("Unsloth", result["name"])
        self.assertIn("Q5_K_M", result["name"])
        self.assertIn("Android/Kotlin", result["purpose"])
        self.assertNotIn("Импортирован", result["purpose"])
        self.assertEqual(result["context"], 16384)
        self.assertEqual(result["ngl"], 24)
        self.assertEqual(result["batch"], 512)
        self.assertEqual(result["ubatch"], 128)
        self.assertEqual(result["gpu"], "GPU-1234")
        self.assertTrue(result["no_kv_offload"])
        self.assertEqual(result["cache_type_k"], "q8_0")
        self.assertFalse(result["reasoning_off"])
        self.assertEqual(result["port"], 8089)
        self.assertEqual(result["extra_args"], ["--some-existing-setting"])
        self.assertEqual(original["models"][0], imported)
        self.assertEqual(plan["config"]["unchanged"], {"value": 200})

    def test_legacy_profile_context_and_custom_purpose_are_not_overwritten(self):
        file = self.add_model(self.censored, "Blend", "Blend-Q4_K_M.gguf")
        profile = {"id": "blend-q4", "name": "JetBrains Blend Q4 (128K)",
                   "path": str(file), "context": 131072, "ngl": 19,
                   "purpose": "Мой собственный режим", "port": 8080}
        plan = maintenance.plan_maintenance(
            self.settings([profile]), roots=[self.censored],
            hardware={"uuid": None, "vram_gib": 22.0})
        self.assertEqual(plan["config"]["models"][0], profile)
        self.assertFalse(plan["changes"])

    def test_duplicate_is_proposed_but_not_removed_without_explicit_selection(self):
        file = self.add_model(self.censored, "Qwen", "Qwen3.8-27B-Q4_K_M.gguf")
        a = {"id": "first", "name": "First context", "path": str(file),
             "context": 32768, "purpose": "User chosen", "port": 8080}
        b = {"id": "second", "name": "Second context", "path": str(file),
             "context": 131072, "purpose": "User chosen", "port": 8081}
        plan = maintenance.plan_maintenance(
            self.settings([a, b]), roots=[self.censored],
            hardware={"uuid": None, "vram_gib": 22.0})
        self.assertEqual([x["id"] for x in plan["config"]["models"]], ["first", "second"])
        self.assertEqual(plan["suggested"][0]["type"], "duplicate")
        self.assertEqual(len(maintenance.apply_selection(plan)["models"]), 2)
        self.assertEqual(len(maintenance.apply_selection(plan, remove_duplicates=True)["models"]), 1)

    def test_unmounted_directory_never_marks_a_model_missing(self):
        path = self.home / "missing-drive" / "model.gguf"
        profile = {"id": "protected", "path": str(path), "name": "Protected"}
        plan = maintenance.plan_maintenance(
            self.settings([profile]), roots=[self.home / "missing-drive"],
            hardware={"uuid": None})
        self.assertEqual(plan["statuses"][0]["state"], "unmounted")
        self.assertEqual(plan["suggested"], [])
        self.assertEqual(plan["config"]["models"], [profile])

    def test_missing_profile_only_removed_after_opt_in(self):
        not_present = self.censored / "no-such-file.gguf"
        profile = {"id": "obsolete", "path": str(not_present),
                   "name": "Qwen3-Coder 30B UD"}
        plan = maintenance.plan_maintenance(
            self.settings([profile]), roots=[self.censored],
            hardware={"uuid": None})
        self.assertEqual(plan["suggested"][0]["type"], "missing")
        self.assertEqual(len(maintenance.apply_selection(plan)["models"]), 1)
        self.assertEqual(len(maintenance.apply_selection(plan, remove_missing=True)["models"]), 0)

    def test_multiple_quantizations_are_not_duplicate(self):
        a = self.add_model(self.uncensored, "Unsloth", "Qwen-Q4_K_M.gguf")
        b = self.add_model(self.uncensored, "Unsloth", "Qwen-Q5_K_M.gguf")
        profiles = [{"id": "q4", "name": "[Uncensored] Unsloth Q4",
                     "purpose": "Импортирован из Uncensored", "path": str(a)},
                    {"id": "q5", "name": "[Uncensored] Unsloth Q5",
                     "purpose": "Импортирован из Uncensored", "path": str(b)}]
        with mock.patch.object(maintenance, "_size_gib", return_value=16):
            plan = maintenance.plan_maintenance(
                self.settings(profiles), roots=[self.uncensored],
                hardware={"uuid": None, "vram_gib": 22.0})
        self.assertFalse(plan["suggested"])
        self.assertEqual(len(plan["config"]["models"]), 2)
        self.assertNotEqual(plan["config"]["models"][0]["name"],
                            plan["config"]["models"][1]["name"])

    def test_vision_projector_resolved_without_overwriting_model_weights(self):
        model = self.add_model(self.censored, "Qwen3-VL-30B",
                               "Qwen3-VL-30B-Q4_K_M.gguf")
        projector = self.add_model(self.censored, "Qwen3-VL-30B",
                                   "mmproj-Qwen3-VL-f16.gguf")
        old = {"id": "qwen3-vl-30b", "name": "Qwen3-VL 30B",
               "path": str(model), "mmproj": "replace-with-mmproj.gguf",
               "purpose": "Изображения, интерфейсы, дизайн", "context": 32768}
        plan = maintenance.plan_maintenance(
            self.settings([old]), roots=[self.censored],
            hardware={"uuid": None, "vram_gib": 22.0})
        new = plan["config"]["models"][0]
        self.assertEqual(new["mmproj"], str(projector.resolve()))
        self.assertEqual(new["path"], str(model))
        self.assertIn("UI", new["purpose"])
        self.assertEqual(model.read_bytes()[:4], b"GGUF")

    def test_source_changed_only_after_explicit_backup_save(self):
        file = self.add_model(self.uncensored, "Huihui", "Qwen3.8-27B-Q4_K_M.gguf")
        profile = {"id": "huihui", "name": "[Uncensored] Huihui Qwen3.8",
                   "purpose": "Импортирован из Uncensored", "path": str(file)}
        config = self.settings([profile])
        config_file = self.home / "models.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        original = config_file.read_bytes()
        original_model = file.read_bytes()
        plan = maintenance.plan_maintenance(
            config, roots=[self.uncensored], hardware={"uuid": None})
        self.assertEqual(config_file.read_bytes(), original)
        self.assertEqual(file.read_bytes(), original_model)
        modified = maintenance.apply_selection(plan)
        backup = model_catalog.save_config(config_file, modified)
        self.assertEqual(json.loads(backup.read_text()), config)
        self.assertEqual(json.loads(config_file.read_text()), modified)
        self.assertEqual(file.read_bytes(), original_model)


class TestCloseErrorUI(unittest.TestCase):
    def test_close_after_failed_shutdown_offers_safe_option(self):
        gui = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertIn("Закрыть только интерфейс (сервисы оставить)", gui)
        self.assertIn("if dialog.clickedButton() == gui_only:", gui)
        self.assertIn("self.exit_requested = True", gui)
        self.assertIn("self.close()", gui)


if __name__ == "__main__":
    unittest.main()
