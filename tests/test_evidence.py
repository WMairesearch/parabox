import tempfile
import unittest
from pathlib import Path

from parabox.evidence import delivery_problems, validate_run
from parabox.studies.transmission.run import shared_digest
from parabox.util import save, sha256


class EvidenceTest(unittest.TestCase):
    def test_binary_delivery_uses_original_digest_not_lossy_preview_roundtrip(self):
        expected = {"shared/cache.pyc": b"\xff\x00\xfe"}
        delivered = {"shared_sha256": shared_digest(expected),
                     "files": {"shared/cache.pyc": expected["shared/cache.pyc"].decode("utf-8", "replace")}}
        self.assertEqual(delivery_problems(delivered, expected), [])
        delivered["shared_sha256"] = shared_digest({"shared/cache.pyc": b"different"})
        self.assertEqual(delivery_problems(delivered, expected), ["delivery-byte-digest-mismatch"])
        delivered["shared_sha256"] = shared_digest(expected)
        delivered["files"] = {}
        self.assertEqual(delivery_problems(delivered, expected), ["delivery-preview-mismatch"])

    def test_invalid_actor_is_not_counted_as_completed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save(root / "plan.json", {"actors": [{"actor": "../outside"}]})
            result = validate_run(root)
        self.assertFalse(result["complete"])
        self.assertEqual(result["normal"], 0)

    def test_incomplete_does_not_pass_even_without_status_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save(root / "plan.json", {"actors": [{"actor": "a1"}]})
            result = validate_run(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["a1"])

    def test_submission_tampering_and_unknown_audit_fail_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save(root / "plan.json", {"actors": [{"actor": "a1"}]})
            session = root / "sessions/a1"
            save(session / "end.json", {"actor": "a1", "normal": True, "accepted": 1})
            save(session / "meta/requests/t01.json", {"messages": []})
            save(session / "meta/submissions.json", [{"turn": 1, "accepted": True, "sha256": sha256("original")}])
            save(session / "meta/audit/session.json", {"violation": None, "turns": [{"turn": 1}]})
            result = validate_run(root)
        self.assertTrue(result["complete"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["audit_unknown"], ["a1"])
        self.assertIn("submission-digest-mismatch", [item["kind"] for item in result["problems"]])


if __name__ == "__main__":
    unittest.main()
