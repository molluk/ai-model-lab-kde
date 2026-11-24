"""Installer regression: every local GUI import must be packaged."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestInstallerModules(unittest.TestCase):
    def test_gui_local_imports_are_installed(self):
        """Catch missing runtime modules even when release_preflight succeeds."""
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        module_names = {p.stem for p in ROOT.glob("*.py")}
        local_imports = {
            name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import)
            for alias in node.names
            for name in [alias.name.split(".")[0]]
            if name in module_names
        }
        local_imports.update(
            node.module.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in module_names
        )
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        package_lines = [
            line for line in installer.splitlines()
            if line.strip().startswith("for name in ") and '"$DEST/$name"' not in line
        ]
        self.assertTrue(package_lines, "missing file packaging list")
        install_list = next(
            (line for line in package_lines if "gui.py" in line and "core.py" in line), ""
        )
        self.assertTrue(install_list, "missing runtime module installer list")
        packaged = {entry[:-3] for entry in install_list.split()
                    if entry.endswith(".py")}
        self.assertEqual(sorted(local_imports - packaged), [],
                         "GUI imports missing from installation")

    def test_actual_install_can_import_maintenance_and_preserves_profiles(self):
        """Execute the real installer in isolated temporary HOME; no Qt required."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            dest = home / "AI" / "AI-Model-Lab"
            home.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["AI_MODEL_LAB_HOME"] = str(dest)
            # This is an offline install; no GPU/model files are accessed.
            subprocess.run(["bash", str(ROOT / "install.sh")],
                           cwd=ROOT, env=env, check=True,
                           capture_output=True, text=True, timeout=45)
            self.assertTrue((dest / "model_maintenance.py").is_file())
            self.assertTrue((dest / "model_catalog.py").is_file())
            self.assertTrue((dest / "gui.py").is_file())
            subprocess.run(
                [sys.executable, "-c", "import model_catalog; import model_maintenance"],
                cwd=dest, env={**env, "PYTHONPATH": str(dest)},
                capture_output=True, text=True, check=True, timeout=15)
            original = dest / "models.json"
            data = json.loads(original.read_text(encoding="utf-8"))
            data["models"].append({"id": "test-local-profile",
                                   "path": "/tmp/none.gguf"})
            original.write_text(json.dumps(data), encoding="utf-8")
            subprocess.run(["bash", str(ROOT / "install.sh")],
                           cwd=ROOT, env=env, check=True,
                           capture_output=True, text=True, timeout=45)
            after = json.loads(original.read_text(encoding="utf-8"))
            self.assertEqual(after, data)


if __name__ == "__main__":
    unittest.main()
