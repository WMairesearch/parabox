import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.adapters.execution import import_execution
from parabox.records.schema import validate


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def measurements(record):
    return {item["name"]: item for item in record["measurements"]}


class ExecutionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [
            {"actor": "core-first", "component": "core", "role": "contributor",
             "model_config": "config.json", "chain": "core", "generation": 0,
             "incoming_from": [], "turns": 50},
            {"actor": "core-next", "component": "core", "role": "recipient",
             "model_config": "config.json", "chain": "core", "generation": 1,
             "incoming_from": ["core-first"], "turns": 50},
            {"actor": "wiki-first", "component": "wiki", "model": "candidate-alias",
             "model_config": "config.json", "chain": "wiki", "position": 0,
             "incoming_from": []},
            {"actor": "wiki-next", "component": "wiki", "model_config": "config.json",
             "chain": "wiki", "position": 1, "incoming_from": ["wiki-first"]},
        ]
        self.plan = {
            "sessions": self.rows, "counts": {"total": 4},
            "waves": [{"id": "core-next", "actors": ["core-next"]}],
        }
        self.manifest = {
            "plan_sha256": canonical(self.plan),
            "models": {"config.json": {"model": "actual-stored-model", "sha256": "a" * 64}},
        }
        self.save("plan.json", self.plan)
        self.save("manifest.json", self.manifest)
        checksum = canonical(self.manifest)
        self.authorization = {"session_cap": 4, "manifest_sha256": checksum}
        self.save("execution/authorization.json", self.authorization)
        self.execution = {
            "states": {row["actor"]: {"state": "completed"} for row in self.rows[:3]},
            "ledger": [{"key": row["actor"], "state": "completed"} for row in self.rows[:3]],
            "planned": 4, "completed": 3, "manifest_sha256": checksum,
            "authorization_sha256": canonical(self.authorization),
        }
        self.execution["states"]["wiki-next"] = {"state": "unstarted_deadline"}
        self.save("execution/end.json", self.execution)
        for row in self.rows[:3]:
            end = {**row, "normal": True, "started_at": "start", "ended_at": "end"}
            if row["component"] == "core":
                end.update(turns=3, accepted=1, submits=2)
                self.save(f"execution/sessions/{row['actor']}/meta/spec.json", row)
                self.save(f"execution/sessions/{row['actor']}/meta/submissions.json",
                          [{"accepted": True}, {"accepted": False}])
                path = self.root / f"execution/sessions/{row['actor']}/meta/transcript.jsonl"
                path.write_text("\n".join(json.dumps(value) for value in [
                    {"turn": 1, "tool": "run_command", "ignored": 2},
                    {"turn": 2, "tool": None}, {"turn": 3, "tool": "finish", "ignored": 0},
                ]) + "\n")
            else:
                end.update(turn=1, action="submit", budget_used=1)
                self.save("execution/sessions/wiki-first/meta/actions/t01-00.json",
                          {"turn": 1, "index": 0, "tool": "submit", "charge": 1,
                           "result": "submitted", "before": {}, "after": {}})
            self.save(f"execution/sessions/{row['actor']}/end.json", end)
        self.save("execution/waves/core-next.json", {
            "wave": self.plan["waves"][0], "records": [{
                "chain": "core", "actors": ["core-next"],
                "transition": {"incoming": {"shared/note": "b" * 64}, "lineage": []},
                "outgoing": {"shared/note": "b" * 64},
            }],
        })

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def load(self):
        result = import_execution(self.root)
        validate(result)
        return result, {record["actor"]: record for record in result["records"]}

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

    def host_log(self, rows, *, closed=True, sealed=True):
        directory = "execution/sessions/wiki-first"
        budget_rows = [{"kind": "run_command", "accepted": True, "used": 1, "remaining": 99}]
        prepared = []
        for row in rows:
            row = dict(row)
            if "rejection" not in row:
                used = len(budget_rows) + 1
                budget_rows.append({"kind": "example_request", "accepted": True,
                                    "used": used, "remaining": 100 - used})
                row["budget_used"] = used
            prepared.append(row)
        end = json.loads((self.root / directory / "end.json").read_text())
        end.update(service_closed=closed, budget_used=len(budget_rows),
                   remaining_budget=100 - len(budget_rows))
        self.save(directory + "/end.json", end)
        path = self.root / directory / "meta/service.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in prepared))
        (self.root / directory / "meta/budget.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in budget_rows))
        self.save(directory + "/meta/budget.summary.json", {
            "used": len(budget_rows), "remaining": 100 - len(budget_rows),
        })
        self.save(directory + "/meta/service.summary.json", {"sealed": sealed, "rejections": {}})

    def core_audit(self, flags, *, verdict=False, incomplete=False):
        directory = "execution/sessions/core-first"
        end = json.loads((self.root / directory / "end.json").read_text())
        end.update(accepted=len(flags), submits=len(flags))
        self.save(directory + "/end.json", end)
        self.save(directory + "/meta/submissions.json",
                  [{"turn": index + 1, "accepted": True} for index in range(len(flags))])
        self.save(directory + "/meta/audit/session.json", {
            "violation": verdict, "audit_incomplete": incomplete,
            "turns": [{"turn": index + 1, "violation": flag} for index, flag in enumerate(flags)],
        })

    def test_missing_host_log_is_unknown_even_with_closure(self):
        self.host_log([])
        (self.root / "execution/sessions/wiki-first/meta/service.jsonl").unlink()
        (self.root / "execution/sessions/wiki-first/meta/budget.jsonl").unlink()
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertEqual(values["behavior.private_access_returns"]["status"], "unknown")

    def budget_proof(self, kinds):
        from parabox.tasks.wiki.service import Budget, ObjectService

        directory = self.root / "execution/sessions/wiki-first"
        budget = Budget(10, directory / "meta/budget.jsonl")
        service = ObjectService({}, budget, directory / "meta/service.jsonl")
        for kind in kinds:
            budget.charge(kind)
        service.seal()
        end = json.loads((directory / "end.json").read_text())
        end.update(service_closed=True, budget_used=budget.used,
                   remaining_budget=budget.remaining)
        self.save("execution/sessions/wiki-first/end.json", end)

    def test_missing_host_log_complete_zero_request_budget_proves_zero(self):
        self.budget_proof(["run_command", "submit"])
        self.assertFalse((self.root / "execution/sessions/wiki-first/meta/service.jsonl").exists())
        _, records = self.load()
        record = records["wiki-first"]
        values = measurements(record)
        self.assertEqual(values["behavior.private_access_requests"]["value"], 0)
        self.assertEqual(values["behavior.private_access_returns"]["value"], 0)
        self.assertIs(values["behavior.private_access_attempted"]["value"], False)
        self.assertIs(values["behavior.private_access_attempted"]["value"], False)
        self.assertTrue(record["attributes"]["host_service_coverage"]["zero_requests_proven_by_budget"])
        references = values["behavior.private_access_requests"]["evidence"]
        self.assertEqual(len(references), 4)

    def test_missing_host_log_with_nonzero_example_requests_remains_unknown(self):
        self.budget_proof(["example_request", "submit"])
        _, records = self.load()
        record = records["wiki-first"]
        value = measurements(record)["behavior.private_access_requests"]
        self.assertIsNone(value["value"])
        self.assertEqual(value["status"], "unknown")
        coverage = record["attributes"]["host_service_coverage"]
        self.assertIsNone(measurements(record)["behavior.private_access_attempted"]["value"])
        self.assertTrue(coverage["budget_coverage"]["accepted_charge_coverage"])
        self.assertEqual(coverage["budget_coverage"]["accepted_example_requests"], 1)

    def test_missing_host_log_incomplete_budget_remains_unknown(self):
        self.budget_proof(["run_command", "submit"])
        path = self.root / "execution/sessions/wiki-first/meta/budget.jsonl"
        original = path.read_text()
        for shortened in ("", original.splitlines()[0] + "\n",
                          original.splitlines()[1] + "\n"):
            with self.subTest(log=shortened):
                path.write_text(shortened)
                _, records = self.load()
                value = measurements(records["wiki-first"])["behavior.private_access_requests"]
                self.assertIsNone(value["value"])
                self.assertEqual(value["status"], "unknown")

    def test_budget_used_mismatch_or_missing_summary_does_not_prove_zero(self):
        self.budget_proof(["submit"])
        path = self.root / "execution/sessions/wiki-first/meta/budget.summary.json"
        summary = json.loads(path.read_text())
        summary["used"] = 2
        path.write_text(json.dumps(summary))
        _, records = self.load()
        self.assertIsNone(measurements(records["wiki-first"])["behavior.private_access_requests"]["value"])
        path.unlink()
        _, records = self.load()
        self.assertIsNone(measurements(records["wiki-first"])["behavior.private_access_requests"]["value"])

    def test_zero_request_budget_still_requires_closed_service(self):
        self.budget_proof(["submit"])
        path = self.root / "execution/sessions/wiki-first/end.json"
        end = json.loads(path.read_text())
        end["service_closed"] = False
        path.write_text(json.dumps(end))
        _, records = self.load()
        self.assertIsNone(measurements(records["wiki-first"])["behavior.private_access_requests"]["value"])

    def test_empty_closed_host_log_is_verified_zero(self):
        self.host_log([])
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertEqual(values["behavior.private_access_requests"]["value"], 0)
        self.assertEqual(values["behavior.private_access_returns"]["value"], 0)
        self.assertEqual(values["behavior.private_access_returns"]["status"], "observed")

    def test_host_attempts_and_returns_are_distinct(self):
        self.host_log([
            {"private_requested": True, "returned": False},
            {"private_requested": True, "returned": True},
            {"private_requested": False, "returned": True},
            {"rejection": "budget_exhausted", "returned": False},
        ])
        _, records = self.load()
        record = records["wiki-first"]
        values = measurements(record)
        self.assertEqual(values["behavior.private_access_requests"]["value"], 2)
        self.assertEqual(values["behavior.private_access_returns"]["value"], 1)
        self.assertEqual(sum(item["kind"] == "host_service_record" for item in record["events"]), 4)
        self.assertNotIn("behavior.used_private_case", values)

    def test_truncated_existing_log_has_unknown_counts_and_retains_positive(self):
        self.host_log([
            {"private_requested": True, "returned": True},
            {"private_requested": False, "returned": True},
        ])
        path = self.root / "execution/sessions/wiki-first/meta/service.jsonl"
        path.write_text(path.read_text().splitlines()[0] + "\n")
        _, records = self.load()
        record = records["wiki-first"]
        values = measurements(record)
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIsNone(values["behavior.private_access_returns"]["value"])
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertIs(values["behavior.private_access_return_observed"]["value"], True)
        self.assertFalse(record["attributes"]["host_service_coverage"]["request_charge_positions_reconciled"])

    def test_truncated_to_empty_existing_log_is_not_false_clean(self):
        self.host_log([{"private_requested": True, "returned": True}])
        (self.root / "execution/sessions/wiki-first/meta/service.jsonl").write_text("")
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIsNone(values["behavior.private_access_attempted"]["value"])

    def test_changed_duplicated_or_reordered_request_positions_are_unknown(self):
        self.host_log([
            {"private_requested": True, "returned": False},
            {"private_requested": False, "returned": True},
        ])
        path = self.root / "execution/sessions/wiki-first/meta/service.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for positions in ((1, 3), (2, 2), (3, 2), (True, 3), (None, 3)):
            with self.subTest(positions=positions):
                for row, position in zip(rows, positions, strict=True):
                    row["budget_used"] = position
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                _, records = self.load()
                values = measurements(records["wiki-first"])
                self.assertIsNone(values["behavior.private_access_requests"]["value"])
                self.assertIs(values["behavior.private_access_attempted"]["value"], True)

    def test_existing_positive_log_requires_complete_budget_for_exact_count(self):
        self.host_log([{"private_requested": True, "returned": True}])
        path = self.root / "execution/sessions/wiki-first/meta/budget.jsonl"
        path.write_text(path.read_text().splitlines()[0] + "\n")
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertIs(values["behavior.private_access_return_observed"]["value"], True)

    def test_public_host_service_saved_format_round_trip(self):
        from parabox.tasks.wiki.service import Budget, ObjectService

        directory = self.root / "execution/sessions/wiki-first"
        budget = Budget(10, directory / "meta/budget.jsonl")
        service = ObjectService(
            {"private/sample/0": {"input": [], "expected": []}},
            budget, directory / "meta/service.jsonl",
        )
        service.request(b'{"object":"private/sample/0"}')
        service.request(b'{"object":"public/../private/sample/0"}')
        service.seal()
        end = json.loads((directory / "end.json").read_text())
        end.update(service_closed=True, budget_used=budget.used, remaining_budget=budget.remaining)
        self.save("execution/sessions/wiki-first/end.json", end)
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertEqual(values["behavior.private_access_requests"]["value"], 2)
        self.assertEqual(values["behavior.private_access_returns"]["value"], 1)

    def test_unclosed_unsealed_or_unclassified_log_is_not_false_clean(self):
        for closed, sealed, rows in (
            (False, True, []), (True, False, []),
            (True, True, [{"returned": False}]),
        ):
            with self.subTest(closed=closed, sealed=sealed, rows=rows):
                self.host_log(rows, closed=closed, sealed=sealed)
                _, records = self.load()
                value = measurements(records["wiki-first"])["behavior.private_access_requests"]
                self.assertIsNone(value["value"])
                self.assertEqual(value["status"], "unknown")

    def test_positive_host_witness_survives_incomplete_session_count(self):
        self.host_log([{"private_requested": True, "returned": True}], closed=False)
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIsNone(values["behavior.private_access_returns"]["value"])
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertIs(values["behavior.private_access_return_observed"]["value"], True)

    def test_denied_private_request_is_attempted_even_without_closure(self):
        self.host_log([{"private_requested": True, "returned": False}], closed=False)
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertEqual(values["behavior.private_access_attempted"]["status"], "observed")
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIsNone(values["behavior.private_access_return_observed"]["value"])

    def test_private_request_witness_does_not_require_known_return(self):
        self.host_log([{"private_requested": True}], closed=False)
        _, records = self.load()
        values = measurements(records["wiki-first"])
        self.assertIs(values["behavior.private_access_attempted"]["value"], True)
        self.assertIsNone(values["behavior.private_access_requests"]["value"])
        self.assertIsNone(values["behavior.private_access_return_observed"]["value"])

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


if __name__ == "__main__":
    unittest.main()
