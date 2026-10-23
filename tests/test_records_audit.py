import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.adapters.execution import import_execution
from parabox.records.schema import validate

from tests.records_fixture import ExecutionAdapterFixture, canonical, measurements


class AuditEvidenceTests(ExecutionAdapterFixture):
    def test_core_missing_audit_is_not_clean(self):
        _, records = self.load()
        value = measurements(records["core-first"])["behavior.accepted_invalid"]
        self.assertEqual(value["status"], "not_measured")
        self.assertIsNone(value["value"])

    def test_core_all_accepted_audits_mixed_unknown_not_false_clean(self):
        self.core_audit([False, None], verdict=False)
        _, records = self.load()
        record = records["core-first"]
        value = measurements(record)["behavior.accepted_invalid"]
        self.assertEqual(value["status"], "unknown")
        self.assertIsNone(value["value"])
        self.assertFalse(record["attributes"]["task_audit_coverage"]["complete"])
        self.assertEqual(record["attributes"]["saved_task_audit"]["violation"], False)

    def test_core_positive_with_unknown_other_audit_stays_positive(self):
        self.core_audit([True, None], verdict=True, incomplete=True)
        _, records = self.load()
        record = records["core-first"]
        self.assertTrue(measurements(record)["behavior.accepted_invalid"]["value"])
        self.assertFalse(record["attributes"]["task_audit_coverage"]["complete"])

    def test_core_complete_clean_audits_and_no_accepted_are_distinct(self):
        self.core_audit([False, False], verdict=False)
        _, records = self.load()
        self.assertIs(measurements(records["core-first"])["behavior.accepted_invalid"]["value"], False)
        self.core_audit([], verdict=None)
        _, records = self.load()
        value = measurements(records["core-first"])["behavior.accepted_invalid"]
        self.assertEqual(value["status"], "not_applicable")
        self.assertIsNone(value["value"])

    def test_core_missing_accepted_turn_cannot_be_clean(self):
        self.core_audit([False, False], verdict=False)
        self.save("execution/sessions/core-first/meta/audit/session.json", {
            "violation": False, "turns": [{"turn": 1, "violation": False}],
        })
        _, records = self.load()
        self.assertIsNone(measurements(records["core-first"])["behavior.accepted_invalid"]["value"])

    def test_unknown_submission_acceptance_is_not_no_accepted(self):
        self.save("execution/sessions/core-first/meta/submissions.json",
                  [{"turn": 1, "accepted": None}])
        _, records = self.load()
        value = measurements(records["core-first"])["behavior.accepted_invalid"]
        self.assertEqual(value["status"], "unknown")
        self.assertIsNone(value["value"])

    def test_bound_grading_can_supply_task_audit_without_executing_grader(self):
        self.core_audit([True], verdict=True)
        path = self.root / "execution/sessions/core-first/meta/audit/session.json"
        audit = json.loads(path.read_text())
        path.unlink()
        end = json.loads((self.root / "execution/sessions/core-first/end.json").read_text())
        self.save("execution/sessions/core-first/grading.json", {
            "actor": "core-first", "end_sha256": canonical(end), "task_audit": audit,
        })
        _, records = self.load()
        value = measurements(records["core-first"])["behavior.accepted_invalid"]
        self.assertTrue(value["value"])
        self.assertEqual(value["evidence"][0]["pointer"], "/task_audit")

    def test_conflicting_saved_and_embedded_audits_rejected(self):
        self.core_audit([False], verdict=False)
        end = json.loads((self.root / "execution/sessions/core-first/end.json").read_text())
        self.save("execution/sessions/core-first/grading.json", {
            "actor": "core-first", "end_sha256": canonical(end),
            "task_audit": {"violation": True, "turns": [{"turn": 1, "violation": True}]},
        })
        with self.assertRaisesRegex(ValueError, "differs"):
            self.load()
