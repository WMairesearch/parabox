import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from parabox.execution import (
    CoreEngine, Invocation, Outcome, StartLedger,
    handoff, manifest, run_population, run_sequential, spec_digest,
)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.frozen = self.root / "engine.py"
        self.frozen.write_text("frozen")
        self.binding = {str(self.frozen): hashlib.sha256(self.frozen.read_bytes()).hexdigest()}

    def ledger(self, cap=10, deadline="2099-01-01T00:00:00+00:00"):
        return StartLedger(self.root / "ledger.sqlite", cap=cap,
                           deadline=deadline, frozen=self.binding)

    def invocation(self, number):
        return Invocation(str(number), self.root / str(number), {"actor": str(number)})

    def test_concurrent_cap_and_reopen(self):
        ledger = self.ledger(cap=3)
        def admit(number):
            try:
                ledger.admit(str(number))
                return True
            except RuntimeError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(admit, range(20))), 3)
        self.assertEqual(len(self.ledger(cap=3).rows()), 3)
        with self.assertRaises(ValueError):
            self.ledger(cap=4)

    def test_deadline_and_digest(self):
        ledger = self.ledger(deadline="2000-01-01T00:00:00Z")
        with self.assertRaises(RuntimeError):
            ledger.admit("late")
        self.assertEqual(ledger.rows(), [])
        self.frozen.write_text("changed")
        with self.assertRaises(ValueError):
            ledger.admit("changed")

    def test_transition_and_duplicate(self):
        ledger = self.ledger()
        ledger.admit("one")
        with self.assertRaises(ValueError):
            ledger.mark("one", "completed")
        ledger.mark("one", "started")
        ledger.mark("one", "completed")
        with self.assertRaises(Exception):
            ledger.admit("one")
        self.assertEqual(len(ledger.rows()), 1)

    def test_plan_binding_and_orchestrated_validation(self):
        invocation = self.invocation(1)
        ledger = StartLedger(self.root / "planned.sqlite", cap=3,
                             deadline="2099-01-01T00:00:00Z", frozen=self.binding,
                             planned={"1": invocation.spec})
        with self.assertRaises(ValueError):
            ledger.admit("unknown", spec={})
        with self.assertRaises(ValueError):
            ledger.admit("1", spec={"actor": "wrong"})
        self.assertEqual(ledger.rows(), [])
        run_sequential([invocation], engine=lambda *_: Outcome({"normal": True}, {}),
                       ledger=ledger, initial={})
        with self.assertRaises(ValueError):
            StartLedger(self.root / "planned.sqlite", cap=3,
                        deadline="2099-01-01T00:00:00Z", frozen=self.binding,
                        planned={"1": {"actor": "wrong"}})
        reopened = StartLedger(self.root / "planned.sqlite", cap=3,
                               deadline="2099-01-01T00:00:00Z", frozen=self.binding,
                               planned={"1": spec_digest(invocation.spec)})
        self.assertEqual(len(reopened.rows()), 1)

    def test_artifact_limits_and_conflicts(self):
        invalid = [
            {"a": b"", "a/b": b""},
            {"../escape": b""},
            {"/absolute": b""},
            {"a//b": b""},
            {"/".join(["part"] * 33): b""},
            {str(number): b"" for number in range(4097)},
            {"large": b"x" * (4 * 1024 * 1024 + 1)},
            {str(number): b"x" * (4 * 1024 * 1024) for number in range(5)},
        ]
        for files in invalid:
            with self.subTest(names=list(files)[:2]):
                with self.assertRaises(ValueError):
                    manifest(files)
        self.assertEqual(len(manifest({"a/b": b"x"})), 1)

    def test_provider_error_text_not_persisted(self):
        ledger = self.ledger()
        def engine(*_):
            raise RuntimeError("secret-provider-token")
        with self.assertRaises(RuntimeError):
            run_sequential([self.invocation(1)], engine=engine, ledger=ledger, initial={})
        self.assertEqual(ledger.rows()[0]["detail"], {"error_type": "RuntimeError"})

    def test_sequential_replacement_and_fresh_inputs(self):
        seen = []
        def engine(invocation, incoming):
            seen.append(dict(incoming))
            incoming.clear()
            return Outcome({"normal": True, "actor": invocation.key},
                           {f"shared/{invocation.key}": b"new"})
        initial = {"shared/old": b"old"}
        result = run_sequential([self.invocation(1), self.invocation(2)],
                                engine=engine, ledger=self.ledger(), initial=initial)
        self.assertEqual(seen, [initial, {"shared/1": b"new"}])
        self.assertEqual(result["lineage"][0]["deleted"], ["shared/old"])
        self.assertEqual(initial, {"shared/old": b"old"})
        self.assertTrue(all(row["state"] == "completed" for row in self.ledger().rows()))

    def test_population_barrier_and_selected(self):
        seen = {}
        def engine(invocation, incoming):
            seen[invocation.key] = dict(incoming)
            return Outcome({"normal": True, "actor": invocation.key},
                           {f"shared/{invocation.key}": b"new"},
                           invocation.key != "2")
        initial = {"shared/old": b"old"}
        result = run_population([[self.invocation(1), self.invocation(2)],
                                 [self.invocation(3)]],
                                engine=engine, ledger=self.ledger(), initial=initial,
                                policy="population_accepted", workers=2)
        self.assertEqual(seen["1"], seen["2"])
        self.assertIn("shared/1", seen["3"])
        self.assertNotIn("shared/2", seen["3"])
        self.assertIn("shared/old", result["files"])

    def test_merge_matches_existing_policy(self):
        from parabox.execution.merge import merge_record
        previous = {"shared/note": b"old"}
        outcomes = [Outcome({"normal": True, "actor": "one"},
                            {"shared/note": b"new"}, True),
                    Outcome({"normal": True, "actor": "two"}, {}, False)]
        expected, _ = merge_record(previous, [
            {"agent": index, "actor": item.end["actor"], "accepted": item.accepted,
             "received": previous, "written": item.files}
            for index, item in enumerate(outcomes)], "all")
        actual, lineage = handoff(previous, outcomes, policy="population_all")
        self.assertEqual(actual, expected)
        self.assertEqual(lineage["deleted"], [])
        self.assertEqual(actual["shared/note"], b"old")

    def test_failure_blocks_successors_and_keeps_start(self):
        def engine(invocation, incoming):
            raise RuntimeError("injected")
        ledger = self.ledger()
        with self.assertRaises(RuntimeError):
            run_sequential([self.invocation(1), self.invocation(2)],
                           engine=engine, ledger=ledger, initial={})
        self.assertEqual([row["state"] for row in ledger.rows()], ["failed"])

    def test_abnormal_blocks_handoff(self):
        with self.assertRaises(RuntimeError):
            run_sequential([self.invocation(1), self.invocation(2)],
                           engine=lambda *_: Outcome({"normal": False}, {}),
                           ledger=self.ledger(), initial={})
        self.assertEqual(len(self.ledger().rows()), 1)

    def test_core_adapter_real_signature_fake_execution(self):
        captured = {}
        def runner(**kwargs):
            captured.update(kwargs)
            return {"normal": True, "actor": "core"}
        engine = CoreEngine(lambda _: {"task": object(), "client": object(),
                                      "box": object(), "integrity": "operational",
                                      "shared": True, "opening": []},
                            runner=runner, exporter=lambda _: ({"shared/new": b"x"}, True))
        result = run_population([[self.invocation(1)]], engine=engine,
                                ledger=self.ledger(), initial={"shared/old": b"x"},
                                policy="population_accepted")
        self.assertEqual(captured["extra_files"], {"shared/old": b"x"})
        self.assertEqual(captured["delivered_record"]["files"], {"shared/old": "x"})
        self.assertEqual(captured["delivered_record"]["file_sha256"],
                         manifest({"shared/old": b"x"}))
        self.assertTrue(result["outcomes"][0].accepted)

    def test_conflicting_core_delivery_metadata_never_reaches_runner(self):
        def runner(**kwargs):
            raise AssertionError("Conflicting delivery must be rejected before runner")
        for supplied in ({"files": {}}, {"shared_sha256": "wrong"}, None):
            with self.subTest(supplied=supplied):
                engine = CoreEngine(lambda _: {"delivered_record": supplied}, runner=runner)
                with self.assertRaisesRegex(ValueError, "Delivery metadata"):
                    engine(self.invocation(1), {"shared/input": b"data"})

    def test_invalid_policy_and_duplicate_have_no_starts(self):
        ledger = self.ledger()
        with self.assertRaises(ValueError):
            run_population([], engine=None, ledger=ledger, initial={}, policy="replace")
        with self.assertRaises(ValueError):
            run_sequential([self.invocation(1), self.invocation(1)],
                           engine=None, ledger=ledger, initial={})
        self.assertEqual(ledger.rows(), [])

    def test_unsupported_engine_policy_rejected_before_start(self):
        class NoAcceptance:
            policies = {"replace", "population_all"}
            def __call__(self, *_):
                raise AssertionError("Must not execute")
        ledger = self.ledger()
        with self.assertRaises(ValueError):
            run_population([[self.invocation(1)]], engine=NoAcceptance(),
                           ledger=ledger, initial={}, policy="population_accepted")
        self.assertEqual(ledger.rows(), [])

    def test_existing_later_directory_rejected_before_any_start(self):
        self.invocation(2).directory.mkdir()
        ledger = self.ledger()
        with self.assertRaises(ValueError):
            run_sequential([self.invocation(1), self.invocation(2)],
                           engine=None, ledger=ledger, initial={})
        self.assertEqual(ledger.rows(), [])

    def test_frozen_scripts_unchanged_by_offline_execution(self):
        root = Path(__file__).resolve().parents[1]
        paths = [root / "parabox/runner/session.py",
                 root / "parabox/execution/merge.py"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        run_sequential([self.invocation(1)], ledger=self.ledger(), initial={},
                       engine=lambda *_: Outcome({"normal": True}, {}))
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in paths})


if __name__ == "__main__":
    unittest.main()
