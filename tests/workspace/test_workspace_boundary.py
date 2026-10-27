import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parabox.execution.merge import snapshot_shared
from parabox.tasks.base import SessionState
from parabox.tasks.code import verify
from parabox.tasks.code.task import CodeTask
from parabox.workspace import list_directory


class NoExecution:
    def exec(self, *args, **kwargs):
        raise AssertionError("unsafe workspace must be rejected before container execution")


class WorkspaceIntegrationTest(unittest.TestCase):
    def test_submit_never_snapshots_a_host_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            outside = parent / "private"
            outside.write_bytes(b"private host bytes")
            (root / "solution.py").symlink_to(outside)
            state = SessionState("double", root, parent / "meta", False, turn=1)
            reply = CodeTask().call(NoExecution(), "submit", {}, state)
            self.assertIn("unsafe file", reply)
            self.assertEqual(state.submissions, [])
            self.assertFalse(state.meta.exists())
            self.assertEqual(outside.read_bytes(), b"private host bytes")

    def test_hidden_tests_cannot_overwrite_a_host_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            (root / "tests").mkdir(parents=True)
            outside = parent / "private"
            outside.write_bytes(b"keep")
            (root / verify.HIDDEN_TEST).symlink_to(outside)
            with self.assertRaises(OSError):
                verify.install_hidden_tests(root, "second_item")
            verify.remove_hidden_tests(root)
            self.assertEqual(outside.read_bytes(), b"keep")

    def test_cleanup_cannot_follow_cache_directory_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            (root / "tests").mkdir(parents=True)
            outside = parent / "private"
            outside.mkdir()
            (outside / "test_hidden-secret.pyc").write_bytes(b"keep")
            (root / "tests/__pycache__").symlink_to(outside, target_is_directory=True)
            (root / ".pytest_cache").symlink_to(outside, target_is_directory=True)
            verify.remove_hidden_tests(root)
            self.assertEqual((outside / "test_hidden-secret.pyc").read_bytes(), b"keep")

    def test_population_and_chain_do_not_inherit_external_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            shared = parent / "session/workspace/shared"
            shared.mkdir(parents=True)
            (parent / "private").write_bytes(b"private")
            (shared / "link").symlink_to(parent / "private")
            (shared / "directory").symlink_to(parent, target_is_directory=True)
            (shared / "safe.txt").write_bytes(b"safe")
            expected = {"shared/safe.txt": b"safe"}
            self.assertEqual(snapshot_shared(parent / "session"), expected)

    def test_tool_access_rechecks_parents_after_path_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            root = parent / "workspace"
            root.mkdir()
            outside = parent / "private"
            outside.mkdir()
            (outside / "file").write_bytes(b"keep")
            (root / "swapped").symlink_to(outside, target_is_directory=True)
            state = SessionState("double", root, parent / "meta", False)
            task = CodeTask()
            with patch.object(verify, "workspace_file", return_value=root / "swapped/file"):
                for name, args in (("read_file", {"path": "swapped/file"}),
                                   ("write_file", {"path": "swapped/file", "content": "overwrite"})):
                    reply = task.call(NoExecution(), name, args, state)
                    self.assertIn("unsafe file", reply)
            self.assertEqual((outside / "file").read_bytes(), b"keep")
            with self.assertRaises(OSError):
                list_directory(root, "swapped")

    def test_visible_test_symlink_is_rejected_by_static_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "solution.py").write_bytes(b"def double(value): return value * 2")
            (root / "tests").mkdir()
            outside = root / "original"
            outside.write_text(verify.test_source("double"))
            (root / "tests/test_solution.py").symlink_to(outside)
            self.assertEqual(verify.static_check(root, "double")["stage"], "unsafe_workspace")


if __name__ == "__main__":
    unittest.main()
