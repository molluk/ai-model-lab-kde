"""Regression: bad imported aliases must not crash runtime or silently alter files."""
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
import core
import model_catalog
import model_maintenance
import multi


class InvalidAliasRecovery(unittest.TestCase):
    def test_generator_never_exceeds_runtime_limit(self):
        paths = [
            "Uncensored/" + "Qwen3.8-27B-super-extra-long-model-name-" * 5,
            "Uncensored/" + "Qwen3.8-27B-super-extra-long-model-name-" * 5 + "Q5",
            "Сверхдлинное-название-" * 12,
            "model",
        ]
        used = set()
        names = [model_catalog._unique_alias(path, used) for path in paths]
        names += [model_catalog._unique_alias(paths[0], used) for _ in range(4)]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertIs(name, name.strip())
            self.assertLessEqual(len(name), 80)
            self.assertEqual(multi.validate_alias(name), name)

    def test_real_discovery_long_name_can_be_launched_by_alias_validator(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / ("long-model-name-" * 8)
            folder.mkdir()
            gguf = folder / (("very-long-gguf-filename-" * 5) + "Q4_K_M.gguf")
            gguf.write_bytes(b"GGUF")
            plan = model_catalog.plan_import(
                {"model_root": str(root), "models": []}, [root])
            self.assertEqual(len(plan["added"]), 1)
            alias = plan["added"][0]["id"]
            self.assertLessEqual(len(alias), 80)
            self.assertEqual(multi.validate_alias(alias), alias)
            self.assertEqual(plan["added"][0]["path"], str(gguf.resolve()))

    def test_existing_invalid_alias_visible_in_all_states_and_never_launches(self):
        bad = "uncensored-" + "very-long-ai-model-name-" * 5
        self.assertGreater(len(bad), 80)
        profile = {"id": bad, "name": "Broken imported profile",
                   "context": 32768, "port": 8081, "path": "/not/real.gguf"}
        with tempfile.TemporaryDirectory() as td:
            instances = Path(td) / "instances"
            with mock.patch.object(core, "config", return_value={"models": [profile]}), \
                 mock.patch.object(multi, "INSTANCES", instances):
                states = multi.all_states()
                self.assertIn(bad, states)
                self.assertEqual(states[bad]["state"], "invalid_profile")
                self.assertFalse(states[bad]["managed"])
                self.assertIsNone(multi.log_path(bad))
                with self.assertRaises(ValueError):
                    multi.launch(bad)
                self.assertEqual(list(instances.glob("*")) if instances.exists() else [], [])

    def test_invalid_alias_migrates_via_preview_and_backup(self):
        long_prefix = "uncensored-" + "long-model-family-name-" * 5
        self.assertGreater(len(long_prefix), 80)
        p1 = {"id": long_prefix, "name": "[Uncensored] Test Model",
              "path": "/not-mountable-drive/model-a.gguf",
              "context": 32768, "purpose": "Импортирован из Uncensored",
              "port": 8082}
        p2 = copy.deepcopy(p1)
        p2["id"] = long_prefix + "-q5"
        p2["path"] = "/not-mountable-drive/model-b.gguf"
        p2["port"] = 8083
        original = {"model_root": "/not-mountable-drive", "models": [p1, p2],
                    "extra_user_setting": "preserve"}
        # Keep unmounted profiles, and repair aliases without touching weights.
        report = model_maintenance.plan_maintenance(original, roots=[
            Path("/not-mountable-drive")], hardware={"uuid": None, "vram_gib": 22.0})
        self.assertEqual(len(report["config"]["models"]), 2)
        self.assertEqual(len(report["changes"]), 2)
        new_ids = [p["id"] for p in report["config"]["models"]]
        self.assertEqual(len(set(new_ids)), 2)
        for alias in new_ids:
            self.assertEqual(alias, multi.validate_alias(alias))
        self.assertEqual(original["models"][0]["id"], p1["id"])
        self.assertEqual(original["extra_user_setting"], "preserve")

        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "models.json"
            file.write_text(json.dumps(original), encoding="utf-8")
            backup = model_catalog.save_config(file, report["config"])
            self.assertEqual(json.loads(backup.read_text()), original)
            self.assertEqual(json.loads(file.read_text()), report["config"])

        again = model_maintenance.plan_maintenance(
            report["config"], roots=[Path("/not-mountable-drive")],
            hardware={"uuid": None, "vram_gib": 22.0})
        self.assertEqual([p["id"] for p in again["config"]["models"]], new_ids)
        self.assertFalse(again["changes"])

    def test_gui_displays_invalid_ids_instead_of_crashing(self):
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertIn("'invalid_profile': (T('⚠ Исправить ID')", source)


if __name__ == "__main__":
    unittest.main()
