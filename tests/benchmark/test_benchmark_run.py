from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from parabox.benchmark import default_spec
from parabox.benchmark.prepare import prepare
from parabox.benchmark.run import BoundOutcomeEngine, DeadlineClient, run, withdraw_note
from parabox.execution import CoreEngine, FrozenWikiEngine, Invocation, Outcome
from parabox.benchmark.protocol.prompts import core_task
from parabox.util import read, save, sha256
from tests.benchmark.test_benchmark_prepare import payload


class FakeEngine:
    policies = {"replace", "population_all"}

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, invocation, incoming):
        row = invocation.spec
        self.calls.append((row, dict(incoming), invocation.options))
        files = dict(incoming)
        if row["component"] == "core":
            files[f"shared/{row['actor']}.txt"] = row["actor"].encode()
        else:
            files.pop("shared/wiki/cases.json", None)
            files["shared/wiki/kept.txt"] = b"successor material"
        normal = row["actor"] != self.fail
        end = {**row, "normal": normal, "shutdown_verified": True}
        save(invocation.directory / "end.json", end)
        return Outcome(end, files, False if row["component"] == "core" else None)


class BenchmarkRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "model.json"
        save(self.config, {"model": "offline", "api_key_env": "NEVER_READ"})
        self.spec = default_spec({"candidate": str(self.config)}, str(self.config), "sha256:" + "a" * 64)
        self.directory = self.root / "suite"
        self.deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.addCleanup(patch.stopall)
        patch("parabox.benchmark.sources.initial_payload", side_effect=payload).start()
        patch("parabox.model.Client.complete", side_effect=AssertionError("No model calls")).start()
        patch("subprocess.run", side_effect=AssertionError("No container calls")).start()
        prepare(self.directory, self.spec)
        self.core, self.wiki = FakeEngine(), FakeEngine()

    def launch(self, **kwargs):
        return run(self.directory, authorize_session_cap=108, deadline=self.deadline,
                   core_engine=self.core, wiki_engine=self.wiki,
                   image_verifier=lambda image: None, **kwargs)

    def test_full_mock_run_uses_stage_two_ledger_and_every_declared_row_once(self):
        result = self.launch()
        self.assertEqual(result["completed"], 108)
        self.assertEqual(len(result["ledger"]), 108)
        self.assertEqual(len(self.core.calls), 72)
        self.assertEqual(len(self.wiki.calls), 36)
        plan = read(self.directory / "plan.json")
        self.assertEqual({row["actor"] for row in plan["sessions"]},
                         {entry["key"] for entry in result["ledger"]})
        self.assertIn("not_run", result["grading"])
        with self.assertRaises(ValueError):
            self.launch()

    def test_population_same_prior_record_and_isolation(self):
        self.launch()
        for row, incoming, _ in self.core.calls:
            if row["generation"] == 0 or row["condition"] == "isolated":
                self.assertEqual(incoming, {})
            else:
                self.assertEqual(len(incoming), 3)
                self.assertTrue(all("-g0-" in name for name in incoming))
        grouped = {}
        for row, incoming, _ in self.core.calls:
            grouped.setdefault((row["chain"], row["generation"]), []).append(incoming)
        self.assertTrue(all(items[0] == items[1] == items[2] for items in grouped.values()))

    def test_wiki_default_preserves_notes_and_agent_deletions(self):
        self.launch()
        for row, incoming, options in self.wiki.calls:
            self.assertEqual(set(options), {"config", "image", "files", "deadline"})
            self.assertIn(b"Execution budget: 20 units.", options["files"]["README.md"])
            if row["position"] == 1:
                if row["condition"] == "full_wiki":
                    self.assertEqual(incoming["shared/wiki/NOTES.md"], f"fixture-{row['block']}".encode())
                else:
                    self.assertNotIn("shared/wiki/NOTES.md", incoming)
                self.assertNotIn("shared/wiki/cases.json", incoming)
                self.assertEqual(incoming["shared/wiki/kept.txt"], b"successor material")

    def test_historical_entry_keeps_original_note_withdrawal(self):
        historical = default_spec({"candidate": str(self.config)}, str(self.config),
                                  "sha256:" + "a" * 64, historical=True)
        self.directory = self.root / "historical"
        prepare(self.directory, historical)
        self.launch()
        for row, incoming, _ in self.wiki.calls:
            if row["position"] == 1:
                self.assertNotIn("shared/wiki/NOTES.md", incoming)
                self.assertNotIn("shared/wiki/cases.json", incoming)
                self.assertEqual(incoming["shared/wiki/kept.txt"], b"successor material")

    def test_failure_blocks_descendants_without_erasing_successful_siblings(self):
        actor = "core-candidate-double-cumulative-g0-s2"
        self.core.fail = actor
        result = self.launch()
        self.assertEqual(result["states"][actor]["state"], "technical_failure")
        self.assertEqual(result["states"][actor.replace("s2", "s0")]["state"], "completed")
        for seat in range(3):
            descendant = f"core-candidate-double-cumulative-g1-s{seat}"
            self.assertEqual(result["states"][descendant]["state"], "unavailable_predecessor")
        self.assertEqual(len(result["ledger"]), 105)

    def test_authorization_deadline_and_image_checks_before_execution(self):
        for cap, deadline in ((107, self.deadline), (108, "2099-01-01T00:00:00"),
                              (108, "2000-01-01T00:00:00+00:00")):
            with self.subTest(cap=cap, deadline=deadline), self.assertRaises(ValueError):
                run(self.directory, authorize_session_cap=cap, deadline=deadline)
        self.assertFalse((self.directory / "execution").exists())
        with self.assertRaises(RuntimeError):
            run(self.directory, authorize_session_cap=108, deadline=self.deadline,
                image_verifier=Mock(side_effect=RuntimeError("image mismatch")))
        self.assertFalse((self.directory / "execution").exists())

    def test_deadline_mid_run_leaves_unstarted_not_behavioral_failures(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        calls = 0

        def clock():
            nonlocal calls
            calls += 1
            return datetime.now(timezone.utc) if calls < 4 else future

        result = self.launch(clock=clock)
        self.assertLess(len(result["ledger"]), 108)
        self.assertTrue(any(value["state"] == "unstarted_deadline" for value in result["states"].values()))

    def test_actual_engine_adapters_with_injected_runners(self):
        def factory(invocation):
            return {"task": core_task(invocation.spec), "client": None, "box": None,
                    "integrity": "plain", "shared": False, "opening": []}

        def core_runner(**kwargs):
            self.assertEqual(kwargs["task"].system(), "Call exactly one tool each turn.")
            row = kwargs["spec"]
            save(kwargs["directory"] / "end.json", {**row, "normal": True})
            return {**row, "normal": True}

        def wiki_runner(directory, spec, config, image, *, files, incoming, deadline):
            self.assertFalse(spec["source"])
            self.assertEqual(spec["budget"], 20)
            self.assertEqual(deadline, self.deadline)
            end = {**spec, "normal": True, "shutdown_verified": True}
            save(directory / "end.json", end)
            return end

        self.core = CoreEngine(factory, runner=core_runner, exporter=lambda invocation: ({}, False))
        bindings = read(self.directory / "manifest.json")["sources"]
        self.wiki = FrozenWikiEngine(variant="budget20", frozen=bindings, runner=wiki_runner,
                                    exporter=lambda invocation: {})
        self.assertEqual(self.launch()["completed"], 108)


class DeadlineAndWithdrawalTests(unittest.TestCase):
    def test_foreign_actor_outcome_rejected_before_ledger_completion(self):
        engine = Mock()
        engine.policies = {"replace"}
        engine.return_value = Outcome({"actor": "foreign", "normal": True}, {})
        wrapped = BoundOutcomeEngine(engine)
        with self.assertRaises(ValueError):
            wrapped(Invocation("planned", Path("unused"), {"actor": "planned"}), {})

    def test_late_completion_never_returns_for_dispatch(self):
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        deadline = before + timedelta(seconds=1)
        client = Mock()
        clock = Mock(side_effect=[before, deadline])
        bounded = DeadlineClient(client, deadline.isoformat(), clock=clock)
        with self.assertRaises(TimeoutError):
            bounded.complete([], tools=[])
        client.complete.assert_called_once()

    def test_expired_deadline_does_not_call_provider(self):
        now = datetime.now(timezone.utc)
        client = Mock()
        bounded = DeadlineClient(client, now.isoformat(), clock=lambda: now)
        with self.assertRaises(TimeoutError):
            bounded.complete([])
        client.complete.assert_not_called()

    def test_edited_note_and_copied_original_are_preserved(self):
        original = b"founder"
        files = {"shared/wiki/NOTES.md": b"edited", "shared/wiki/copy.md": original}
        delivered, lineage = withdraw_note(files, sha256(original))
        self.assertEqual(delivered, files)
        self.assertIsNone(lineage["removed_note_original_hash"])
        files["shared/wiki/NOTES.md"] = original
        delivered, lineage = withdraw_note(files, sha256(original))
        self.assertNotIn("shared/wiki/NOTES.md", delivered)
        self.assertEqual(delivered["shared/wiki/copy.md"], original)
        self.assertEqual(lineage["removed_note_original_hash"], sha256(original))


if __name__ == "__main__":
    unittest.main()
