import tempfile
import io
import tarfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.release_check import inspect_archive, inspect_worktree, scan_bytes


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

    def test_source_archive_enforces_document_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "MANIFEST.in").write_text("include docs/usage.md\n")
            archive = root / "parabox-0.2.0.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                for name in ("docs/usage.md", "docs/unlisted.md", "runs/private.json"):
                    entry = tarfile.TarInfo("parabox-0.2.0/" + name)
                    entry.size = 2
                    package.addfile(entry, io.BytesIO(b"{}"))
            result = inspect_archive(root, archive)
        self.assertEqual(result["files_checked"], 3)
        self.assertEqual(result["findings"], [
            {"path": "docs/unlisted.md", "kind": "unlisted-document"},
            {"path": "runs/private.json", "kind": "private-evidence-or-env"},
        ])

    def test_wheel_scans_content_without_printing_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "MANIFEST.in").write_text("")
            archive = root / "parabox-0.2.0-py3-none-any.whl"
            secret = b"sk-" + b"z" * 32
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("parabox/assets/seed.json", secret)
                package.writestr("../escape", b"not extracted")
            result = inspect_archive(root, archive)
        self.assertEqual(result["findings"], [
            {"path": "parabox/assets/seed.json", "kind": "provider-key"},
            {"path": "../escape", "kind": "unsafe-archive-entry"},
        ])
        self.assertNotIn(secret.decode(), repr(result))


if __name__ == "__main__":
    unittest.main()
