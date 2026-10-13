import os
import tempfile
import unittest
from pathlib import Path

from parabox.workspace import read_regular, remove_tree, snapshot_regular, unlink_regular, write_regular


class WorkspaceBoundaryTest(unittest.TestCase):
    def test_snapshot_excludes_links_and_special_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            (parent / "private").write_bytes(b"private")
            (root / "linked-file").symlink_to(parent / "private")
            (root / "linked-dir").symlink_to(parent, target_is_directory=True)
            os.mkfifo(root / "fifo")
            write_regular(root, "sub/file", b"safe")
            self.assertEqual(snapshot_regular(root), {"sub/file": b"safe"})
            with self.assertRaises(OSError):
                snapshot_regular(root / "linked-dir")

    def test_snapshot_limits_bound_tree_traversal_and_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_regular(root, "sub/file", b"1234")
            for limits in ({"max_entries": 1}, {"max_bytes": 3}, {"max_depth": 0}):
                with self.subTest(limits=limits), self.assertRaises(ValueError):
                    snapshot_regular(root, **limits)

    def test_cleanup_unlinks_directory_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            outside = parent / "private"
            outside.mkdir()
            (outside / "keep").write_bytes(b"private")
            (root / ".pytest_cache").symlink_to(outside, target_is_directory=True)
            remove_tree(root, ".pytest_cache")
            self.assertEqual((outside / "keep").read_bytes(), b"private")
            write_regular(root, ".pytest_cache/nested/file", b"cache")
            remove_tree(root, ".pytest_cache")
            self.assertFalse((root / ".pytest_cache").exists())

    def test_normal_file_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_regular(root, "shared/file.txt", b"long content")
            write_regular(root, "shared/file.txt", b"new")
            self.assertEqual(read_regular(root, "shared/file.txt"), b"new")
            unlink_regular(root, "shared/file.txt")
            self.assertFalse((root / "shared/file.txt").exists())

    def test_file_link_cannot_read_or_overwrite_host_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            outside = parent / "outside"
            outside.write_bytes(b"private")
            (root / "solution.py").symlink_to(outside)
            with self.assertRaises(OSError):
                read_regular(root, "solution.py")
            with self.assertRaises(OSError):
                write_regular(root, "solution.py", b"replacement")
            self.assertEqual(outside.read_bytes(), b"private")
            unlink_regular(root, "solution.py")
            self.assertTrue(outside.exists())

    def test_directory_link_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            (root / "tests").symlink_to(parent, target_is_directory=True)
            with self.assertRaises(OSError):
                write_regular(root, "tests/test_hidden.py", b"test")
            self.assertFalse((parent / "test_hidden.py").exists())
            with self.assertRaises(ValueError):
                write_regular(root, "../outside", b"test")

    def test_fifo_does_not_block_and_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.mkfifo(root / "fifo")
            with self.assertRaises(ValueError):
                read_regular(root, "fifo")
            (root / "large").write_bytes(b"12345")
            with self.assertRaises(ValueError):
                read_regular(root, "large", limit=4)


if __name__ == "__main__":
    unittest.main()
