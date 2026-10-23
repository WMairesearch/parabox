import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageBoundaryTest(unittest.TestCase):
    def test_public_components_do_not_import_studies(self):
        paths = (path for directory in ("parabox", "scripts", "tests")
                 for path in (ROOT / directory).rglob("*.py")
                 if not path.is_relative_to(ROOT / "parabox/studies"))
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or "").startswith("parabox.studies"))
                        self.assertFalse(node.module == "parabox" and any(
                            alias.name == "studies" for alias in node.names))
                    elif isinstance(node, ast.Import):
                        self.assertFalse(any(alias.name.startswith("parabox.studies")
                                             for alias in node.names))


if __name__ == "__main__":
    unittest.main()
