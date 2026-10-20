import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from parabox.tasks.wiki import episode


class PortableTaskTests(unittest.TestCase):
    def test_relocated_package_without_research_imports(self):
        package = Path(episode.__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "parabox"
            target.mkdir()
            for name in ("__init__.py", "util.py", "sandbox.py", "workspace.py"):
                shutil.copyfile(package / name, target / name)
            shutil.copytree(package / "model", target / "model",
                            ignore=shutil.ignore_patterns("__pycache__"))
            (target / "tasks").mkdir()
            shutil.copyfile(package / "tasks/__init__.py", target / "tasks/__init__.py")
            shutil.copytree(package / "tasks/wiki", target / "tasks/wiki",
                            ignore=shutil.ignore_patterns("__pycache__"))
            command = """
import importlib.abc
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
class RejectResearch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "scripts" or fullname.startswith("scripts."):
            raise AssertionError("Research import attempted")
sys.meta_path.insert(0, RejectResearch())
from parabox.tasks.wiki import budget, episode, evaluator, fixture, grader, prompts, scoring, service
assert episode.BUDGET == 60 and budget.BUDGET == 20
assert len(fixture.cases("events")) == 100
assert b"Execution budget: 20 units." in budget.workspace_files("events", 30)["README.md"]
assert scoring.submission_score([{"passed": True}] * 100, True)["qualified"]
assert grader.normalize_image("1" * 64) == "sha256:" + "1" * 64
for name, module in tuple(sys.modules.items()):
    if name == "parabox" or name.startswith("parabox."):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
print("portable")
"""
            environment = {key: value for key, value in os.environ.items()
                           if key not in ("PYTHONPATH", "PYTHONHOME")}
            result = subprocess.run([sys.executable, "-I", "-c", command, str(root)],
                                    cwd=root, env=environment, capture_output=True, text=True,
                                    timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "portable")


if __name__ == "__main__":
    unittest.main()
