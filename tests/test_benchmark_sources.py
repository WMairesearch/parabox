from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark.selftest import selftest
from parabox.benchmark.sources import BUNDLE, BUNDLE_SHA256, export_wiki, initial_payload
from parabox.util import save, sha256


class BenchmarkSourcesTests(unittest.TestCase):
    def test_packaged_first_author_bytes_and_provenance(self):
        self.assertEqual(sha256(BUNDLE.read_bytes()), BUNDLE_SHA256)
        for block, entries in enumerate((3, 5, 4)):
            full = initial_payload(block, "full_wiki")
            self.assertEqual(len(full["files"]), entries)
            self.assertEqual(full["checkpoint_author"], 0)
            self.assertEqual(
                full["provenance"]["source_files"],
                {name: sha256(raw) for name, raw in full["files"].items()},
            )
            self.assertEqual(full["provenance"]["checkpoint_actor"], f"source-{block:02d}-00")
            empty = initial_payload(block, "empty_wiki")
            self.assertEqual(empty["files"], {})
            artifacts = initial_payload(block, "artifacts_only")
            expected = dict(full["files"])
            expected.pop("shared/wiki/NOTES.md", None)
            self.assertEqual(artifacts["files"], expected)
        self.assertNotIn("shared/wiki/NOTES.md", initial_payload(2, "full_wiki")["files"])

    def test_invalid_checkpoint_and_changed_bundle_fail(self):
        for block, condition, checkpoint in (
            (True, "full_wiki", 0), (3, "full_wiki", 0),
            (0, "unknown", 0), (0, "full_wiki", 1),
        ):
            with self.subTest(block=block, condition=condition, checkpoint=checkpoint):
                with self.assertRaises(ValueError):
                    initial_payload(block, condition, checkpoint)
        with patch("parabox.benchmark.sources.BUNDLE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "digest"):
                initial_payload(0, "full_wiki")

    def test_export_uses_archived_bytes_and_actual_deletions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = b"corrected"
            digest = sha256(raw)
            destination = root / "meta/artifacts" / digest
            destination.parent.mkdir(parents=True)
            destination.write_bytes(raw)
            end = {"normal": True, "shutdown_verified": True,
                   "outgoing": {"files": {"NOTES.md": digest}}}
            save(root / "end.json", end)
            self.assertEqual(export_wiki(root), (end, {"shared/wiki/NOTES.md": raw}))
            end["outgoing"]["files"] = {}
            save(root / "end.json", end)
            self.assertEqual(export_wiki(root)[1], {})
            end["outgoing"]["files"] = {"../outside": digest}
            save(root / "end.json", end)
            with self.assertRaises(ValueError):
                export_wiki(root)

    def test_selftest_uses_real_assets_without_paid_or_container_calls(self):
        with patch("parabox.model.Client", side_effect=AssertionError("No provider")), \
                patch("subprocess.run", side_effect=AssertionError("No container")):
            result = selftest()
        self.assertEqual(result, {
            "ok": True, "planned_sessions": 108, "source_blocks": 3,
            "model_calls": 0, "containers_started": 0,
        })


if __name__ == "__main__":
    unittest.main()
