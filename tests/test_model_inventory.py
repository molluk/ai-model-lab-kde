"""Read-only local weights inventory and model profile comparison tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "AI"
        self.censored = self.root / "Censored"
        self.uncensored = self.root / "Uncensored"
        self.censored.mkdir(parents=True)
        self.uncensored.mkdir(parents=True)

    def write(self, directory, name, data=b"GGUFtest"):
        directory.mkdir(exist_ok=True, parents=True)
        path = directory / name
        path.write_bytes(data)
        return path

    def test_scan_nested_model_projector_shards_invalid_and_safetensors(self):
        model = self.write(self.censored / "Blend", "Blend-Q4_K_M.gguf", b"GGUF" + b"x" * 12)
        bad = self.write(self.censored / "Broken", "broken.gguf", b"NOPE")
        projector = self.write(self.censored / "VL", "mmproj-vision.gguf")
        first = self.write(self.uncensored / "split", "model-Q5_K_M-00001-of-00003.gguf")
        self.write(self.uncensored / "split", "model-Q5_K_M-00003-of-00003.gguf")
        other = self.write(self.uncensored / "Weights", "model.safetensors", b"not-a-gguf")
        self.write(self.uncensored / "Weights" / ".git", "no.gguf")
        model_before = model.read_bytes()
        result = model_inventory.scan_weights(self.root)
        self.assertEqual(len(result["weights"]), 6)
        self.assertEqual(len(result["split_groups"]), 1)
        self.assertEqual(result["split_groups"][0]["missing"], [2])
        self.assertIn(str(model), result["by_path"])
        self.assertFalse(result["by_path"][str(bad)]["magic_ok"])
        self.assertEqual(result["by_path"][str(projector)]["kind"], "projector")
        self.assertEqual(result["by_path"][str(other)]["extension"], ".safetensors")
        self.assertEqual(model_before, model.read_bytes())

    def test_comparison_exact_matches_ports_dupes_and_orphans(self):
        model = self.write(self.censored / "Blend", "Blend-Q4_K_M.gguf")
        orphan = self.write(self.uncensored / "Qwen", "Qwen-Q4_K_M.gguf")
        config = {
            "model_root": str(self.censored),
            "models": [
                {"id": "blend", "name": "Blend", "path": str(model),
                 "port": 8080, "favorite": True, "context": 32768},
                {"id": "same-weight-different-context", "name": "Blend 128k",
                 "path": str(model), "port": 8080},
                {"id": "not-here", "path": str(self.censored / "gone.gguf"),
                 "port": 8083},
            ]
        }
        scan = model_inventory.scan_weights(self.root)
        comp = model_inventory.analyze_profiles(config, scan)
        self.assertEqual(len(comp["profiles"]), 3)
        self.assertEqual(comp["profiles"][0]["status"], "PATH_OK")
        self.assertTrue(comp["profiles"][0]["favorite"])
        self.assertEqual(comp["profiles"][2]["status"], "PATH_MISSING")
        self.assertEqual(comp["unassigned_gguf"], [str(orphan)])
        self.assertEqual(comp["shared_profile_files"], {str(model): [
            "blend", "same-weight-different-context"]})
        self.assertEqual(comp["shared_ports"], {"8080": [
            "blend", "same-weight-different-context"]})

    def test_glob_profile_resolves_only_in_configured_root(self):
        model = self.write(self.censored / "X", "unique-Q4_K_M.gguf")
        self.write(self.uncensored / "X", "unique-Q4_K_M.gguf")
        scanned = model_inventory.scan_weights(self.root)
        conf = {"model_root": str(self.censored),
                "models": [{"id": "old", "match": "unique-Q4_K_M.gguf", "port": 8080}]}
        comp = model_inventory.analyze_profiles(conf, scanned)
        self.assertEqual(comp["profiles"][0]["status"], "MATCH_OK")
        self.assertEqual(comp["profiles"][0]["resolved"], str(model))

    def test_absent_roots_and_missing_config_report_without_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "NoAI"
            missing_config = Path(td) / "no-config.json"
            report = model_inventory.build_report(root, missing_config)
            output = model_inventory.render_report(report)
            self.assertIn("ТОЛЬКО ЧТЕНИЕ", output)
            self.assertEqual(len(report["inventory"]["missing_roots"]), 2)
            self.assertIsNone(report["comparison"])
            self.assertFalse(root.exists())

    def test_actual_report_does_not_change_weights_or_config(self):
        file = self.write(self.uncensored / "Qwen", "Qwen-Q4_K_M.gguf")
        config = self.root / "models.json"
        config.write_text(json.dumps({
            "model_root": str(self.censored),
            "models": [{"id": "qwen", "path": str(file), "port": 8090}]
        }), encoding="utf-8")
        before = file.read_bytes(), config.read_bytes()
        report = model_inventory.build_report(self.root, config)
        txt = model_inventory.render_report(report)
        self.assertIn("PATH_OK", txt)
        self.assertIn("Uncensored", txt)
        self.assertEqual((file.read_bytes(), config.read_bytes()), before)
        self.assertEqual(report["comparison"]["unassigned_gguf"], [])

    def test_symlink_never_followed(self):
        real = self.write(self.uncensored / "real", "real.gguf")
        link = self.uncensored / "fake.gguf"
        link.symlink_to(real)
        result = model_inventory.scan_weights(self.root)
        self.assertEqual(len(result["weights"]), 1)
        self.assertIn(str(link), result["skipped_symlinks"])

    def test_long_invalid_alias_detected(self):
        file = self.write(self.censored / "X", "x.gguf")
        data = {"model_root": str(self.censored),
                "models": [{"id": "bad" * 40, "path": str(file)}]}
        row = model_inventory.analyze_profiles(data, model_inventory.scan_weights(self.root))["profiles"][0]
        self.assertFalse(row["id_valid"])


if __name__ == "__main__":
    unittest.main()
