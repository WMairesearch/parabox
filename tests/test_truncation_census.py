import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.truncation_census import main


class TruncationCensusTest(unittest.TestCase):
    def test_roots_are_required(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main([])
        self.assertEqual(raised.exception.code, 2)

    def test_missing_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main([str(Path(directory) / "missing")])
        self.assertEqual(raised.exception.code, 2)

    def test_empty_explicit_root(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(output):
                main([directory])
        self.assertIn("TOTAL {}", output.getvalue())
