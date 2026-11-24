"""Offline non-destructive GGUF discovery / profile import tests (no Qt or GPU)."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_catalog


class TestLocalModelCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.censored = self.root / "Censored"
        self.uncensored = self.root / "Uncensored"
        self.censored.mkdir()
        self.uncensored.mkdir()

    def model(self, root, folder, filename):
        directory = root / folder
        directory.mkdir(parents=True, exist_ok=True)
        result = directory / filename
        result.write_bytes(b"GGUF test fixture")
        return result

    def config(self):
        return {
            "model_root": str(self.censored),
            "server_bin": "~/llama.cpp/build/bin/llama-server",
            "models": [{
                "id": "old-blend",
                "name": "Keep me",
                "context": 131072,
                "path": "Blend/Blend-Q4_K_M.gguf",
                "port": 8080,
                "extra_args": ["--keep-this"],
            }],
            "other_setting": {"do_not_change": True},
        }

    def test_two_roots_existing_profiles_untouched_and_idempotent(self):
        self.model(self.censored, "Blend", "Blend-Q4_K_M.gguf")
        model = self.model(self.uncensored, "Huihui Qwen", "Qwen3.8-27B-IQ4_XS.gguf")
        original = self.config()
        prior = copy.deepcopy(original["models"][0])
        report = model_catalog.plan_import(original, [self.censored, self.uncensored])
        self.assertEqual(report["found"], 2)
        self.assertEqual(len(report["existing"]), 1)
        self.assertEqual(len(report["added"]), 1)
        self.assertEqual(report["config"]["models"][0], prior)
        self.assertEqual(original["models"][0], prior)
        self.assertEqual(report["config"]["other_setting"], original["other_setting"])
        imported = report["added"][0]
        self.assertEqual(imported["path"], str(model.resolve()))
        self.assertEqual(imported["context"], 32768)
        self.assertNotEqual(imported["port"], 8080)
        self.assertIn("Uncensored", imported["name"])
        self.assertEqual(imported["cache_type_k"], "q8_0")
        self.assertTrue(imported["no_kv_offload"])
        again = model_catalog.plan_import(report["config"], [self.censored, self.uncensored])
        self.assertEqual(again["added"], [])
        self.assertEqual(len(again["existing"]), 2)

    def test_shards_projector_and_comfy_ignored(self):
        self.model(self.censored, "Qwen3-VL", "Qwen3-VL-Q4_K_M-00001-of-00002.gguf")
        self.model(self.censored, "Qwen3-VL", "Qwen3-VL-Q4_K_M-00002-of-00002.gguf")
        projector = self.model(self.censored, "Qwen3-VL", "mmproj-Qwen3-VL-f16.gguf")
        self.model(self.censored, "ComfyUI/checkpoints", "not-a-llm.gguf")
        report = model_catalog.plan_import({"models": [], "model_root": str(self.censored)},
                                            [self.censored])
        self.assertEqual(report["found"], 1)
        self.assertEqual(len(report["added"]), 1)
        self.assertEqual(report["added"][0]["mmproj"], str(projector.resolve()))
        self.assertFalse(report["warnings"])

    def test_multiple_quantizations_ports_and_no_existing_change(self):
        a = self.model(self.uncensored, "Unsloth Qwen", "Qwen3.8-27B-Q4_K_M.gguf")
        b = self.model(self.uncensored, "Unsloth Qwen", "Qwen3.8-27B-Q5_K_M.gguf")
        report = model_catalog.plan_import({"models": []}, [self.uncensored])
        self.assertEqual({p["path"] for p in report["added"]},
                         {str(a.resolve()), str(b.resolve())})
        self.assertEqual(len({p["port"] for p in report["added"]}), 2)
        self.assertEqual(len({p["id"] for p in report["added"]}), 2)

    def test_missing_folder_safe_and_no_automatic_removal(self):
        c = self.config()
        report = model_catalog.plan_import(c, [self.root / "missing"])
        self.assertEqual(report["added"], [])
        self.assertEqual(report["config"], c)
        self.assertEqual(len(report["missing_roots"]), 1)

    def test_save_creates_backup_without_overwriting_prior_profiles(self):
        config_path = self.root / "models.json"
        original = self.config()
        config_path.write_text(json.dumps(original), encoding="utf-8")
        new = copy.deepcopy(original)
        new["models"].append({"id": "new", "path": "/tmp/not-executed.gguf"})
        backup = model_catalog.save_config(config_path, new)
        self.assertTrue(backup.is_file())
        self.assertEqual(json.loads(backup.read_text()), original)
        self.assertEqual(json.loads(config_path.read_text()), new)
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_cli_dry_run_does_not_write(self):
        model = self.model(self.uncensored, "Huihui", "Qwen3.8-27B-Q4_K_M.gguf")
        config = self.root / "models.json"
        config.write_text(json.dumps({"models": []}), encoding="utf-8")
        before = config.read_bytes()
        self.assertEqual(model_catalog.main(["--config", str(config),
                                             "--root", str(self.uncensored)]), 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(model.is_file())


if __name__ == "__main__":
    unittest.main()
