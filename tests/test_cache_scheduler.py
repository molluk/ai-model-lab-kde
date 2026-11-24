"""Unit tests for configurable, persistent, cache-only cleanup scheduling."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cache_scheduler


class CacheSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "AI-Model-Lab"
        self.root.mkdir()
        (self.root / "core.py").write_text("# fixture")
        (self.root / "gui.py").write_text("# fixture")
        (self.root / "models.json").write_text('{"models":[{"id":"qwen"}]}')
        (self.root / "settings.json").write_text('{"language":"ru"}')
        (self.root / "services.json").write_text('{"services":[]}')
        self.cache = self.create("data/cache/tempfile.bin", b"cache")
        self.python_cache = self.create("__pycache__/gui.cpython-312.pyc", b"bytecode")
        self.log = self.create("data/logs/model.log", b"model-log")
        self.backup = self.create("data/backups/release/gui.py", b"old code")
        self.report = self.create("data/reports/task/summary.json", b'{"ok":true}')
        self.client = self.create("data/clients/pi/models.json", b'{"pi":true}')
        self.weights = self.create("data/models/weights.gguf", b"GGUF001")

    def create(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_disabled_does_not_delete_or_write_schedule(self):
        self.assertEqual(cache_scheduler.run_due(self.root, 0, now=1000), {
            "status": "disabled"})
        self.assertTrue(self.cache.exists())
        self.assertFalse((self.root / "data/auto_cache_cleanup_state.json").exists())

    def test_invalid_intervals_rejected(self):
        for value in (-1, 721, 1.5, True, "24", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    cache_scheduler.validate_hours(value)

    def test_schedule_initialization_and_due_are_persisted(self):
        first = cache_scheduler.configure(self.root, 6, now=1000)
        self.assertEqual(first["schedule"]["next_due_ts"], 1000 + 6 * 3600)
        self.assertEqual(cache_scheduler.run_due(self.root, 6, now=1500)["status"],
                         "not_due")
        # Reinitialization of a second app instance must not reset the timer.
        later = cache_scheduler.configure(self.root, 6, now=2500)
        self.assertEqual(later["status"], "unchanged")
        state = cache_scheduler.status(self.root, 6, now=2500)
        self.assertEqual(state["next_due_ts"], 1000 + 6 * 3600)
        self.assertTrue(self.cache.exists())

    def test_run_once_when_overdue_and_preserve_non_cache(self):
        cache_scheduler.configure(self.root, 1, now=100)
        self.assertEqual(cache_scheduler.run_due(
            self.root, 1, now=3701, busy=True)["status"], "busy")
        self.assertTrue(self.cache.exists())
        result = cache_scheduler.run_due(self.root, 1, now=3701)
        self.assertEqual(result["status"], "cleaned")
        self.assertEqual(result["count"], 2)
        self.assertFalse(self.cache.exists())
        self.assertFalse(self.python_cache.exists())
        self.assertEqual(cache_scheduler.run_due(
            self.root, 1, now=3702)["status"], "not_due")
        status = cache_scheduler.status(self.root, 1, now=3702)
        self.assertEqual(status["last_count"], 2)
        self.assertEqual(status["last_run_ts"], 3701)
        self.assertEqual(status["next_due_ts"], 3701 + 3600)
        for file in (self.log, self.backup, self.report, self.client,
                     self.weights, self.root / "settings.json",
                     self.root / "models.json", self.root / "services.json"):
            self.assertTrue(file.exists(), str(file))
        self.assertIn("Следующая очистка", cache_scheduler.next_run_label(
            self.root, 1, now=3702))

    def test_missed_interval_catches_up_on_next_start(self):
        cache_scheduler.configure(self.root, 24, now=1000)
        self.assertEqual(cache_scheduler.status(
            self.root, 24, now=1000 + 3 * 86400)["status"], "due")
        result = cache_scheduler.run_due(self.root, 24, now=1000 + 3 * 86400)
        self.assertEqual(result["status"], "cleaned")
        self.assertEqual(cache_scheduler.status(
            self.root, 24, now=1000 + 3 * 86400)["status"], "scheduled")

    def test_changing_hours_resets_schedule_without_deleting(self):
        cache_scheduler.configure(self.root, 24, now=1000)
        cache_scheduler.configure(self.root, 2, now=1100)
        state = cache_scheduler.status(self.root, 2, now=1100)
        self.assertEqual(state["next_due_ts"], 1100 + 7200)
        self.assertTrue(self.cache.exists())
        cache_scheduler.configure(self.root, 0, now=1200)
        self.assertEqual(cache_scheduler.status(self.root, 0)["status"], "disabled")
        self.assertTrue(self.cache.exists())
        cache_scheduler.configure(self.root, 2, now=1300)
        self.assertEqual(cache_scheduler.status(self.root, 2)["next_due_ts"],
                         1300 + 7200)

    def test_corrupt_state_is_reinitialized_without_deleting(self):
        statefile = self.root / "data/auto_cache_cleanup_state.json"
        statefile.write_text("NOT JSON")
        self.assertEqual(cache_scheduler.run_due(self.root, 1, now=2000)["status"],
                         "scheduled")
        self.assertTrue(self.cache.exists())
        self.assertEqual(cache_scheduler.status(self.root, 1, now=2000)["status"],
                         "scheduled")

    def test_error_has_cooldown_and_does_not_delete_anything(self):
        cache_scheduler.configure(self.root, 1, now=0)
        with mock.patch.object(cache_scheduler.artifact_cleanup, "preview",
                               side_effect=OSError("disk unavailable")):
            result = cache_scheduler.run_due(self.root, 1, now=3602)
        self.assertEqual(result["status"], "error")
        self.assertTrue(self.cache.exists())
        self.assertEqual(cache_scheduler.status(
            self.root, 1, now=3603)["status"], "scheduled")
        self.assertIn("disk unavailable", cache_scheduler.next_run_label(
            self.root, 1, now=3603))

    def test_lock_prevents_concurrent_cleanup(self):
        cache_scheduler.configure(self.root, 1, now=0)
        with cache_scheduler._lock(self.root) as acquired:
            self.assertTrue(acquired)
            # flock is per-process, so use a second process-independent file
            # descriptor in the same process, which should still contend.
            self.assertEqual(cache_scheduler.run_due(
                self.root, 1, now=4000)["status"], "busy")
            self.assertTrue(self.cache.exists())
        self.assertEqual(cache_scheduler.run_due(
            self.root, 1, now=4000)["status"], "cleaned")


if __name__ == "__main__":
    unittest.main()
