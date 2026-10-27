import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.adapters.execution import import_execution
from parabox.records.schema import validate

from tests.records.records_fixture import ExecutionAdapterFixture, canonical, measurements


class ExecutionAdapterTests(ExecutionAdapterFixture):
    def test_complete_saved_output_and_distinct_acceptance(self):
        result, records = self.load()
        self.assertEqual(result["metadata"]["counts"],
                         {"planned": 4, "ledger_entries": 3, "completed": 3, "saved_ends": 3})
        self.assertEqual(records["wiki-first"]["model"], "actual-stored-model")
        values = measurements(records["core-first"])
        self.assertEqual(values["task.accepted_submission_count"]["value"], 1)
        self.assertFalse(values["task.accepted"]["value"])
        self.assertEqual(values["resources.saved_tool_records"]["value"], 3)
        self.assertEqual(values["resources.turns_used"]["value"], 3)
        self.assertEqual([event["attributes"]["native"]["ignored"]
                          for event in records["core-first"]["events"]
                          if "ignored" in event["attributes"]["native"]], [2, 0])

    def test_ungraded_submission_is_not_acceptance_or_private_violation(self):
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertTrue(values["choice.submitted"]["value"])
        self.assertEqual(values["task.reward"]["status"], "not_measured")
        self.assertIsNone(values["task.code_score"]["value"])
        self.assertNotIn("task.accepted", values)
        self.assertNotIn("behavior.accepted_invalid", values)
        self.assertFalse(records["wiki-next"]["status"]["started"])
        self.assertFalse(records["wiki-next"]["status"]["ended"])

    def test_core_budget_and_actual_turns_have_separate_bound_sources(self):
        result, records = self.load()
        record = records["core-first"]
        self.assertEqual(record["assignment"]["turns"], 50)
        self.assertEqual(measurements(record)["resources.turns_used"]["value"], 3)
        self.assertTrue(any(source["path"].endswith("core-first/meta/spec.json")
                            for source in result["sources"]))

    def test_core_invalid_counter_or_changed_budget_rejected(self):
        for used, limit in ((51, 50), (-1, 50), (True, 50), (3, 49)):
            with self.subTest(used=used, limit=limit):
                self.save("execution/sessions/core-first/meta/spec.json",
                          {**self.rows[0], "turns": limit})
                self.save("execution/sessions/core-first/end.json",
                          {**self.rows[0], "turns": used, "normal": True})
                with self.assertRaisesRegex(ValueError, "budget|assignment"):
                    self.load()

    def test_recorded_delivery_distinct_from_planned_or_read(self):
        result, records = self.load()
        self.assertEqual([relation["kind"] for relation in result["relations"]].count("planned_handoff"), 2)
        self.assertEqual([relation["kind"] for relation in result["relations"]].count("recorded_handoff"), 1)
        self.assertEqual(records["core-next"]["events"][-1]["kind"], "saved_handoff_transition")
        self.assertEqual(records["wiki-next"]["events"], [])

    def test_negative_reward_remains_separate_from_code_score(self):
        end = json.loads((self.root / "execution/sessions/wiki-first/end.json").read_text())
        self.save("execution/sessions/wiki-first/grading.json", {
            "actor": "wiki-first", "end_sha256": canonical(end),
            "earned_score": -1, "qualified": True, "final_score": {"code_score": 1},
        })
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertEqual(values["task.reward"]["value"], -1)
        self.assertEqual(values["task.code_score"]["value"], 1)
        self.assertTrue(values["task.qualified"]["value"])

    def test_grading_wrong_actor_or_binding_rejected(self):
        for actor, checksum in (("other", "a" * 64), ("wiki-first", "b" * 64)):
            with self.subTest(actor=actor):
                self.save("execution/sessions/wiki-first/grading.json",
                          {"actor": actor, "end_sha256": checksum})
                with self.assertRaisesRegex(ValueError, "grading"):
                    self.load()

    def test_saved_binding_changes_rejected(self):
        self.manifest["models"]["config.json"]["model"] = "changed"
        self.save("manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.load()

    def test_plan_change_rejected(self):
        self.plan["sessions"][0]["role"] = "changed"
        self.save("plan.json", self.plan)
        with self.assertRaisesRegex(ValueError, "Plan"):
            self.load()

    def test_roster_and_missing_completed_terminal_rejected(self):
        (self.root / "execution/sessions/core-first/end.json").unlink()
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.load()
        self.execution["states"]["extra"] = {"state": "completed"}
        self.save("execution/end.json", self.execution)
        with self.assertRaisesRegex(ValueError, "roster"):
            self.load()

    def test_failed_runner_is_not_false_participant_outcome(self):
        self.execution["states"]["wiki-next"] = {"state": "technical_failure"}
        self.execution["ledger"].append({"key": "wiki-next", "state": "failed"})
        self.save("execution/end.json", self.execution)
        _, records = self.load()
        record = records["wiki-next"]
        self.assertTrue(record["status"]["started"])
        self.assertIsNone(record["status"]["ended"])
        self.assertIsNone(record["status"]["normal"])
        self.assertEqual(record["measurements"], [])

    def test_duplicate_transcript_not_counted(self):
        path = self.root / "execution/sessions/core-first/meta/transcript.jsonl"
        path.write_text(path.read_text() + json.dumps({"turn": 1, "tool": "submit"}) + "\n")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.load()

    def test_authorization_binding_and_count_rejected(self):
        self.execution["planned"] = 5
        self.save("execution/end.json", self.execution)
        with self.assertRaisesRegex(ValueError, "count"):
            self.load()
        self.authorization["session_cap"] = 5
        self.save("execution/authorization.json", self.authorization)
        with self.assertRaisesRegex(ValueError, "authorization"):
            self.load()

    def test_no_submissions_means_unknown_final_acceptance(self):
        self.save("execution/sessions/core-first/meta/submissions.json", [])
        _, records = self.load()
        value = measurements(records["core-first"])["task.accepted"]
        self.assertIsNone(value["value"])
        self.assertEqual(value["status"], "unknown")

    def test_symlinked_evidence_cannot_escape_explicit_suite(self):
        with tempfile.TemporaryDirectory() as external:
            path = self.root / "execution/sessions/core-first/meta/submissions.json"
            target = Path(external) / "submissions.json"
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "within the suite"):
                self.load()

    def test_symlinked_manifest_cannot_escape_explicit_suite(self):
        with tempfile.TemporaryDirectory() as external:
            path = self.root / "manifest.json"
            target = Path(external) / "manifest.json"
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "within the suite"):
                self.load()

    def test_unknown_component_is_not_treated_as_wiki(self):
        self.rows[0]["component"] = "unrecognized"
        self.save("plan.json", self.plan)
        self.manifest["plan_sha256"] = canonical(self.plan)
        self.save("manifest.json", self.manifest)
        self.authorization["manifest_sha256"] = canonical(self.manifest)
        self.save("execution/authorization.json", self.authorization)
        self.execution["manifest_sha256"] = canonical(self.manifest)
        self.execution["authorization_sha256"] = canonical(self.authorization)
        self.save("execution/end.json", self.execution)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.load()

    def test_empty_delivery_is_not_evidence_of_reading(self):
        self.save("execution/waves/core-next.json", {
            "wave": self.plan["waves"][0], "records": [{
                "chain": "core", "actors": ["core-next"],
                "transition": {"incoming": {}, "lineage": []}, "outgoing": {},
            }],
        })
        bundle, records = self.load()
        relation = next(item for item in bundle["relations"] if item["kind"] == "recorded_handoff")
        self.assertEqual(relation["attributes"]["delivered_file_count"], 0)
        self.assertNotIn("behavior.read", measurements(records["core-next"]))
