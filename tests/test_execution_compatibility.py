from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from parabox.execution import (
    BoundOutcomeEngine, CoreEngine, DeadlineClient, Invocation, Outcome,
    StartLedger, run_sequential,
)
from parabox.execution.runtime import execute_invocation
from parabox.session import run_session
from parabox.util import digest_json, sha256
from tests.helpers import FakeBox, FakeTask, ScriptedClient
from tests.test_relay_board import BoardClient, FakeBoardTask, seed_record


class GuardCompatibilityTests(unittest.TestCase):
    def test_deadline_prevents_late_request_and_late_dispatch(self):
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        deadline = before + timedelta(seconds=1)
        client = Mock()
        wrapped = DeadlineClient(client, deadline.isoformat(), Mock(return_value=deadline))
        with self.assertRaises(TimeoutError):
            wrapped.complete([], tools=[])
        client.complete.assert_not_called()
        wrapped = DeadlineClient(client, deadline.isoformat(),
                                 Mock(side_effect=[before, deadline]))
        with self.assertRaises(TimeoutError):
            wrapped.complete([], tools=[])
        client.complete.assert_called_once()

    def test_deadline_wrapper_forwards_request_and_response_without_copying(self):
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        messages, tools = [{"role": "user", "content": "input"}], []
        response = ({"role": "assistant"}, {"usage": {"input_tokens": 1}})
        client = Mock()
        client.complete.return_value = response
        clock = Mock(return_value=before)
        wrapped = DeadlineClient(client, (before + timedelta(seconds=1)).isoformat(), clock)
        self.assertIs(wrapped.complete(messages, tools=tools), response)
        self.assertIs(client.complete.call_args.args[0], messages)
        self.assertIs(client.complete.call_args.kwargs["tools"], tools)
        self.assertEqual(clock.call_count, 2)

    def test_provider_failure_is_not_retried_or_replaced(self):
        before = datetime(2099, 1, 1, tzinfo=timezone.utc)
        error = RuntimeError("provider failed")
        client = Mock()
        client.complete.side_effect = error
        clock = Mock(return_value=before)
        wrapped = DeadlineClient(client, (before + timedelta(seconds=1)).isoformat(), clock)
        with self.assertRaises(RuntimeError) as caught:
            wrapped.complete([], tools=[])
        self.assertIs(caught.exception, error)
        client.complete.assert_called_once()
        clock.assert_called_once()

    def test_identity_wrapper_preserves_policy_inputs_and_outcome(self):
        invocation = Invocation("actor", Path("unused"), {"actor": "actor"})
        incoming = {"shared/note": b"content"}
        outcome = Outcome({"actor": "actor", "normal": True}, incoming, False)
        engine = Mock(return_value=outcome)
        engine.policies = {"replace"}
        wrapped = BoundOutcomeEngine(engine)
        self.assertIs(wrapped.policies, engine.policies)
        self.assertIs(wrapped(invocation, incoming), outcome)
        self.assertIs(engine.call_args.args[0], invocation)
        self.assertIs(engine.call_args.args[1], incoming)


class LifecycleCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.invocation = Invocation("actor", self.root / "session", {"actor": "actor"})
        self.ledger = Mock()

    def test_admission_precedes_execution_and_only_input_mapping_is_copied(self):
        incoming = {"shared/note": b"content"}
        outcome = Outcome({"actor": "actor", "normal": True}, {})

        def engine(invocation, received):
            self.assertIs(invocation, self.invocation)
            self.assertEqual(self.ledger.mock_calls, [
                call.admit("actor", spec=self.invocation.spec), call.mark("actor", "started"),
            ])
            self.assertIsNot(received, incoming)
            self.assertIs(received["shared/note"], incoming["shared/note"])
            received.clear()
            return outcome

        self.assertIs(execute_invocation(engine, self.ledger, self.invocation, incoming), outcome)
        self.assertEqual(incoming, {"shared/note": b"content"})
        self.assertEqual(self.ledger.mock_calls[-1],
                         call.mark("actor", "completed", {"normal": True}))

    def test_existing_destination_prevents_admission(self):
        self.invocation.directory.mkdir()
        engine = Mock()
        with self.assertRaises(ValueError):
            execute_invocation(engine, self.ledger, self.invocation, {})
        self.assertEqual(self.ledger.mock_calls, [])
        engine.assert_not_called()

    def test_admission_failure_never_starts_engine(self):
        self.ledger.admit.side_effect = RuntimeError("cap reached")
        engine = Mock()
        with self.assertRaises(RuntimeError):
            execute_invocation(engine, self.ledger, self.invocation, {})
        self.ledger.mark.assert_not_called()
        engine.assert_not_called()

    def test_interruption_remains_failed_without_retry(self):
        engine = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            execute_invocation(engine, self.ledger, self.invocation, {})
        engine.assert_called_once()
        self.assertEqual(self.ledger.mock_calls[-1],
                         call.mark("actor", "failed", {"error_type": "KeyboardInterrupt"}))

    def test_invalid_export_fails_before_completion(self):
        engine = Mock(return_value=Outcome({"normal": True}, {"../outside": b"content"}))
        with self.assertRaises(ValueError):
            execute_invocation(engine, self.ledger, self.invocation, {})
        self.assertEqual(self.ledger.mock_calls[-1],
                         call.mark("actor", "failed", {"error_type": "ValueError"}))


class CoreSessionCompatibilityTests(unittest.TestCase):
    def test_public_unfinished_evidence_guard_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "session"
            evidence = directory / "meta" / "existing.txt"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"existing evidence")
            client = Mock()
            engine = CoreEngine(lambda invocation: {
                "task": FakeTask(), "client": client,
                "box": FakeBox(directory / "workspace"), "integrity": "library",
                "shared": True, "opening": [],
            })
            with self.assertRaisesRegex(RuntimeError, "unfinished session evidence"):
                engine(Invocation("actor", directory, {"actor": "actor"}), {})
            self.assertEqual(evidence.read_bytes(), b"existing evidence")
            client.complete.assert_not_called()

    def test_direct_and_adapted_sessions_have_identical_saved_bytes(self):
        variants = (
            (FakeTask, lambda: ScriptedClient(extra_call=True), None),
            (FakeBoardTask, BoardClient, [seed_record("Saved peer note.")]),
        )
        for task_factory, client_factory, board in variants:
            with self.subTest(task=task_factory.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                direct, adapted = root / "direct", root / "adapted"
                spec = {"actor": "actor", "problem": "odd_perfect", "generation": 1}
                incoming = {"shared/note.txt": b"Saved file."}
                opening = ["Session input."]

                def options(directory):
                    return {
                        "task": task_factory(), "client": client_factory(),
                        "box": FakeBox(directory / "workspace"),
                        "integrity": "library", "shared": True,
                        "opening": opening, "board": board,
                        "delivered_record": {
                            "files": {"shared/note.txt": "Saved file."},
                            "shared_sha256": digest_json({"shared/note.txt": sha256(b"Saved file.")}),
                            "file_sha256": {"shared/note.txt": sha256(b"Saved file.")},
                        },
                    }

                source = root / "source"
                source.write_bytes(b"offline fixture")
                ledger = StartLedger(
                    root / "ledger.sqlite", cap=1, deadline="2099-01-01T00:00:00Z",
                    frozen={str(source): sha256(source.read_bytes())},
                    planned={"actor": spec},
                )
                engine = CoreEngine(
                    lambda invocation: options(invocation.directory),
                    exporter=lambda invocation: (
                        {"shared/note.txt": (invocation.directory / "workspace/shared/note.txt").read_bytes()},
                        True,
                    ),
                )
                with patch("parabox.session.now", return_value="2026-01-01T00:00:00+00:00"):
                    expected = run_session(directory=direct, spec=spec, extra_files=incoming,
                                           **options(direct))
                    result = run_sequential(
                        [Invocation("actor", adapted, spec)], engine=engine,
                        ledger=ledger, initial=incoming,
                    )
                self.assertTrue(expected["normal"])
                self.assertTrue(expected["finished"])
                self.assertEqual(result["outcomes"][0].end, expected)
                self.assertEqual(result["files"], incoming)
                expected_files = {
                    saved.relative_to(direct): saved.read_bytes()
                    for saved in direct.rglob("*") if saved.is_file()
                }
                actual_files = {
                    saved.relative_to(adapted): saved.read_bytes()
                    for saved in adapted.rglob("*") if saved.is_file()
                }
                self.assertEqual(actual_files, expected_files)


if __name__ == "__main__":
    unittest.main()
