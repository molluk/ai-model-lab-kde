"""Build provenance must reflect the installed source, not the current working tree."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import version_info as vi


class TestVersionInfo(unittest.TestCase):
    def test_no_git_and_no_manifest_does_not_invent_commit(self):
        with tempfile.TemporaryDirectory() as td:
            info = vi.read_build_info(Path(td))
            self.assertEqual(info["version"], vi.APP_VERSION)
            self.assertIsNone(info["commit"])
            self.assertIn("SHA: —", vi.short_label(info))

    def test_installed_manifest_preserves_full_commit(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "build_info.json"
            sha = "c" * 40
            target.write_text(json.dumps({"version": "3.10+dev", "commit": sha, "dirty": False}))
            with mock.patch.object(vi, "_git", side_effect=AssertionError("Git should not run")):
                info = vi.read_build_info(Path(td))
            self.assertEqual(info["commit"], sha)
            self.assertIn("cccccccc", vi.short_label(info))
            self.assertIn(sha, vi.detail_label(info))
            self.assertIn("Version", vi.detail_label(info, lambda s: {"Версия": "Version"}.get(s, s)))

    def test_malformed_manifest_does_not_provide_fake_sha(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / vi.MANIFEST
            path.write_text(json.dumps({"version": "3.10+dev", "commit": "fake"}))
            info = vi.read_build_info(Path(td))
            self.assertIsNone(info["commit"])

    def test_generate_manifest_from_real_checkout_and_track_dirty(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "source"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("hello")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=CI",
                            "-c", "user.email=ci@example.test", "commit", "-qm",
                            "test source"], check=True)
            expected = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            destination = Path(td) / "installed" / vi.MANIFEST
            result = vi.write_manifest(destination, repo)
            self.assertEqual(result["commit"], expected)
            self.assertFalse(result["dirty"])
            self.assertEqual(vi.read_build_info(destination.parent)["commit"], expected)
            tracked.write_text("changed")
            self.assertTrue(vi.source_build_info(repo)["dirty"])
            vi.write_manifest(destination, repo)
            self.assertTrue(vi.read_build_info(destination.parent)["dirty"])

    def test_parent_repo_not_mistaken_for_installed_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            nested = root / "installed"
            nested.mkdir()
            self.assertIsNone(vi.source_build_info(nested)["commit"])

    def test_gui_has_persistent_footer_and_installer_writes_manifest(self):
        root = Path(__file__).resolve().parents[1]
        gui = (root / "gui.py").read_text(encoding="utf-8")
        installer = (root / "install.sh").read_text(encoding="utf-8")
        self.assertIn("version_info.short_label(build)", gui)
        self.assertIn("version_info.detail_label(build, T)", gui)
        self.assertIn('footer.addWidget(self.version_label)', gui)
        self.assertIn('version_info.py" --write "$DEST/build_info.json"', installer)
        self.assertIn("version_info.py", installer)


if __name__ == "__main__":
    unittest.main()
