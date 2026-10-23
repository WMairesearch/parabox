import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageBoundaryTest(unittest.TestCase):
    def test_framework_does_not_import_studies(self):
        for path in (ROOT / "parabox").rglob("*.py"):
            if "studies" in path.relative_to(ROOT / "parabox").parts:
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or "").startswith("parabox.studies"))
                    elif isinstance(node, ast.Import):
                        self.assertFalse(any(alias.name.startswith("parabox.studies")
                                             for alias in node.names))


if __name__ == "__main__":
    unittest.main()
