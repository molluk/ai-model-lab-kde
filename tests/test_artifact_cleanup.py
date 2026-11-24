"""Security-oriented storage cleanup regression tests (no user files touched)."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import artifact_cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "AI-Model-Lab"
        self.root.mkdir()
        for name in ("core.py", "gui.py"):
            (self.root / name).write_text("# test\n")
        self.config = self.add("models.json", "models - DO NOT DELETE")
        self.settings = self.add("settings.json", "settings - DO NOT DELETE")
        self.services = self.add("services.json", "services - DO NOT DELETE")
        self.report = self.add("data/reports/run/summary.json", "report - DO NOT DELETE")
        self.client_settings = self.add("data/clients/pi/demo/models.json",
                                        "client models - DO NOT DELETE")
        self.log = self.add("data/logs/old.log", "log")
        self.active_log = self.add("data/logs/active.log", "active")
        self.cache = self.add("data/cache/work.cache", "cache")
        self.python_cache = self.add("__pycache__/gui.pyc", "bytecode")
        self.backup = self.add("data/backups/release-2026/gui.py", "old code")
        self.backup_models = self.add("data/backups/release-2026/models.json",
                                      "archived settings snapshot")
        self.exterior = Path(self.tmp.name) / "outside.gguf"
        self.exterior.write_bytes(b"GGUFsecret")
        shortcut = self.root / "data/cache/shortcut"
        shortcut.symlink_to(self.exterior)
        external_directory = Path(self.tmp.name) / "outside"
        external_directory.mkdir()
        (external_directory / "donttouch.txt").write_text("intact")
        (self.root / "data/cache/external-link").symlink_to(
            external_directory, target_is_directory=True)
        self.external_directory = external_directory

    def add(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_preview_never_mutates_and_does_not_find_configs(self):
        info = artifact_cleanup.preview(self.root, protected=[self.active_log])
        self.assertEqual(info["categories"]["logs"]["count"], 1)
        self.assertEqual(info["categories"]["cache"]["count"], 2)
        self.assertEqual(info["categories"]["backups"]["count"], 2)
        entries = [row[0] for cat in info["categories"].values()
                   for row in cat["entries"]]
        self.assertNotIn("models.json", entries)
        self.assertNotIn("settings.json", entries)
        self.assertNotIn("data/logs/active.log", entries)
        self.assertTrue(self.cache.is_file())
        self.assertTrue(self.backup.is_file())
        self.assertTrue(self.exterior.is_file())

    def test_only_cache_selected_cannot_touch_settings_gguf_logs_backups(self):
        plan = artifact_cleanup.preview(self.root, selected=("cache",))
        result = artifact_cleanup.apply(plan)
        self.assertEqual(result["cache"]["removed"], 2)
        self.assertFalse(self.cache.exists())
        self.assertTrue(self.log.is_file())
        self.assertTrue(self.backup.is_file())
        for file in (self.config, self.settings, self.services,
                     self.report, self.client_settings, self.exterior):
            self.assertTrue(file.exists(), str(file))
        self.assertEqual((self.external_directory / "donttouch.txt").read_text(),
                         "intact")

    def test_logs_skip_active_at_apply_time(self):
        plan = artifact_cleanup.preview(self.root, selected=("logs",))
        outcome = artifact_cleanup.apply(plan, protected=[self.active_log])
        self.assertEqual(outcome["logs"]["removed"], 1)
        self.assertEqual(outcome["logs"]["skipped"], 1)
        self.assertFalse(self.log.exists())
        self.assertTrue(self.active_log.exists())

    def test_backups_are_only_removed_when_explicitly_selected(self):
        plan = artifact_cleanup.preview(self.root, selected=("backups",))
        outcome = artifact_cleanup.apply(plan)
        self.assertEqual(outcome["backups"]["removed"], 2)
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.backup_models.exists())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.settings.exists())

    def test_changed_inode_not_removed_after_preview(self):
        plan = artifact_cleanup.preview(self.root, selected=("logs",))
        self.log.unlink()
        self.log.write_text("new log written after preview")
        outcome = artifact_cleanup.apply(plan)
        self.assertGreaterEqual(outcome["logs"]["skipped"], 1)
        self.assertTrue(self.log.exists())
        self.assertEqual(self.log.read_text(), "new log written after preview")

    def test_reject_unknown_category_and_root(self):
        with self.assertRaises(ValueError):
            artifact_cleanup.preview(self.root, selected=("weights",))
        with self.assertRaises(ValueError):
            artifact_cleanup.preview(Path("/"))
        with self.assertRaises(ValueError):
            artifact_cleanup.apply({
                "root": str(self.root),
                "categories": {"models": {"entries": [], "dirs": []}},
            })

    def test_root_symlink_refused(self):
        other = Path(self.tmp.name) / "app-link"
        other.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            artifact_cleanup.preview(other)


if __name__ == "__main__":
    unittest.main()
