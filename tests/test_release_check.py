import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.release_check import inspect_worktree, scan_bytes


class ReleaseScanTest(unittest.TestCase):
    def test_key_detection_does_not_return_value(self):
        candidate = b"sk-" + b"x" * 32
        self.assertEqual(scan_bytes(candidate), ["provider-key"])
        self.assertNotIn(candidate.decode(), repr(scan_bytes(candidate)))

    def test_environment_variable_name_is_not_a_key(self):
        self.assertEqual(scan_bytes(b'{"api_key_env": "PARABOX_API_KEY"}'), [])

    def test_ignored_credentials_are_not_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("example")
            (root / ".env").write_text("PRIVATE=do-not-read")
            with patch("scripts.release_check.git", return_value=b"README.md\0"):
                result = inspect_worktree(root)
        self.assertEqual(result, {"files_checked": 1, "findings": []})


if __name__ == "__main__":
    unittest.main()
