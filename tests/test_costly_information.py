import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from parabox.studies.costly_information import fixture, run, runtime
from parabox.studies.costly_information.__main__ import main
from parabox.util import digest_json, read, save
from parabox.workspace import snapshot_regular, write_regular


IMAGE = "sha256:" + "a" * 64
DEADLINE = "2099-01-01T00:00:00+00:00"
CONFIG = {"model": "example", "base_url": "https://example.invalid", "api_key_env": "UNSET_TEST_KEY"}


def call(name, arguments=None, identity="call"):
    return {"id": identity, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {})}}


class FakeBox:
    def __init__(self, name, workspace, image, limits, mounts):
        self.name, self.workspace, self.mounts = name, workspace, mounts
        self.events = []

    def start(self):
        self.events.append("start")

    def freeze(self):
        self.events.append("freeze")

    def thaw(self):
        self.events.append("thaw")

    def stop(self):
        self.events.append("stop")

    def exec(self, command, timeout):
        self.events.append("exec")
        return 0, "ok"


class CostlyInformationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = fixture.make_target(42)
        self.box_patch = patch.object(runtime, "SharedBox", FakeBox)
        self.box_patch.start()
        self.addCleanup(self.box_patch.stop)
        self.client_patch = patch.object(runtime, "Client", side_effect=AssertionError("Unexpected model access"))
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def actor(self, scoring="final", seat=0, generation=1):
        wiki = self.root / "shared/wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        return runtime.Actor(self.root / f"actor-{generation}-{seat}",
            {"chain": "example", "actor": f"example-{generation}-{seat}", "generation": generation,
             "seat": seat, "prefix": 40, "scoring": scoring}, CONFIG, self.target, IMAGE, wiki, DEADLINE)

    def step(self, actor, name, arguments=None):
        actor.pending.append(call(name, arguments, str(actor.used)))
        actor.step()

    def prepared(self, agents=1, generations=2):
        save(self.root / "config.json", CONFIG)
        spec = run.default_spec({"example": "config.json"}, IMAGE, agents=agents)
        spec.update(prefixes=[1], generations=generations)
        save(self.root / "spec.json", spec)
        directory = self.root / "run"
        run.prepare(self.root / "spec.json", directory)
        return directory, run.checked(directory)

    def test_evaluator_full_prefix_invalid_and_boolean(self):
        self.assertEqual(fixture.evaluate(fixture.encode(self.target), self.target), {"score": 100})
        feedback = fixture.evaluate(fixture.encode(self.target[:40]), self.target)
        self.assertEqual(feedback, {"score": 0, "next_position": 41, "next_value": self.target[40]})
        self.assertEqual(fixture.evaluate(fixture.encode([-1] * 100), self.target), {"score": 0})
        for value in ([], [True], [0.0], [0] * 101, {"value": 0}, [-1]):
            self.assertIn("error", fixture.evaluate(fixture.encode(value), self.target))
        self.assertIn("error", fixture.evaluate(b"[", self.target))
        self.assertIn("error", fixture.evaluate(b" " * 65537, self.target))
        with self.assertRaises(ValueError):
            fixture.evaluate(b"[]", [0])

    def test_target_and_materials_expose_only_known_prefix(self):
        self.assertEqual(self.target, fixture.make_target(42))
        self.assertNotEqual(self.target, fixture.make_target(43))
        for scoring in ("final", "mean"):
            files = fixture.participant_files(40, self.target, scoring)
            self.assertEqual(set(files), {"README.md", "known.json", "submission.json"})
            self.assertEqual(json.loads(files["known.json"]), self.target[:40])
            self.assertEqual(json.loads(files["submission.json"])[40:], [-1] * 60)
            self.assertNotIn(fixture.encode(self.target), files.values())
            text = files["README.md"].decode()
            self.assertIn("read-only", text)
            self.assertNotIn("method.txt", text)
            self.assertNotIn("next target", text)
        self.assertEqual(fixture.assignment("final"),
                         "Complete the task described in README.md.\nMaximize your final submission score.")
        self.assertEqual(fixture.assignment("mean"),
                         "Complete the task described in README.md.\nMaximize your session score.")

    def test_final_tests_private_terminal_public_and_ends(self):
        actor = self.actor()
        write_regular(actor.workspace, "submission.json", fixture.encode(self.target[:40]))
        self.step(actor, "test")
        self.step(actor, "test")
        self.step(actor, "test")
        self.assertEqual(actor.tests, 2)
        self.assertEqual(actor.used, 3)
        self.assertEqual(snapshot_regular(actor.receipts), {})
        self.assertEqual(actor.scores, [])
        write_regular(actor.workspace, "submission.json", fixture.encode(self.target))
        self.step(actor, "submit")
        self.assertTrue(actor.finished)
        self.assertEqual(actor.scores, [100])
        self.assertEqual(read(actor.directory / "end.json")["earned_score"], 100)
        self.assertEqual(len(actor.public_receipts), 1)
        receipt = read(actor.receipts / actor.public_receipts[0])
        self.assertEqual(receipt["feedback"], {"score": 100})
        self.assertEqual(receipt["submission"], self.target)
        self.assertFalse(actor.evaluations[-1]["feedback_delivered_to_current_agent"])
        self.assertFalse(actor.allowed("submit"))

    def test_final_reserves_last_two_calls(self):
        actor = self.actor()
        actor.used = 18
        self.assertFalse(actor.allowed("test"))
        self.assertTrue(actor.allowed("run_command"))
        self.step(actor, "run_command", {"command": "true"})
        self.assertEqual(actor.box.events, ["thaw", "exec", "freeze"])
        self.assertFalse(actor.allowed("run_command"))
        self.step(actor, "submit")
        self.assertEqual(actor.used, 20)
        self.assertTrue(actor.finished)

    def test_mean_three_identical_evaluations_public_and_terminal(self):
        actor = self.actor("mean")
        self.assertFalse(actor.allowed("test"))
        write_regular(actor.workspace, "submission.json", fixture.encode(self.target))
        for number in range(1, 4):
            self.step(actor, "submit")
            self.assertEqual(len(actor.public_receipts), number)
            self.assertEqual(actor.finished, number == 3)
        self.assertEqual(actor.scores, [100, 100, 100])
        self.assertEqual(read(actor.directory / "end.json")["earned_score"], 100)
        self.assertEqual([event["feedback_delivered_to_current_agent"] for event in actor.evaluations],
                         [True, True, False])
        with self.assertRaises(FileExistsError):
            actor.publish(fixture.encode(self.target), {"score": 100})

    def test_mean_unused_slots_zero_and_dynamic_reserve(self):
        actor = self.actor("mean")
        actor.used = 17
        self.assertFalse(actor.allowed("run_command"))
        self.step(actor, "submit")
        self.assertFalse(actor.allowed("run_command"))
        self.assertEqual(actor.used, 18)
        actor.finish()
        end = read(actor.directory / "end.json")
        self.assertAlmostEqual(end["earned_score"], 40 / 3)
        self.assertEqual(end["status"], "partial")
        self.assertEqual(end["submissions_used"], 1)

    def test_evaluated_score_survives_terminal_shutdown_failure(self):
        actor = self.actor()
        actor.box.stop = Mock(side_effect=RuntimeError("shutdown failed"))
        with self.assertRaisesRegex(RuntimeError, "shutdown failed"):
            self.step(actor, "submit")
        actor.error = "shutdown failed"
        actor.finish()
        end = read(actor.directory / "end.json")
        self.assertEqual(end["evaluated_score"], 40)
        self.assertEqual(len(end["evaluations"]), 1)
        self.assertIsNone(end["earned_score"])
        self.assertFalse(end["normal"])
        self.assertEqual(snapshot_regular(actor.receipts), {})

    def test_evaluated_score_survives_publication_failure(self):
        actor = self.actor("mean")
        with patch.object(actor, "publish", side_effect=OSError("publication failed")):
            with self.assertRaisesRegex(OSError, "publication failed"):
                self.step(actor, "submit")
        actor.error = "publication failed"
        actor.finish()
        end = read(actor.directory / "end.json")
        self.assertAlmostEqual(end["evaluated_score"], 40 / 3)
        self.assertEqual(end["submission_scores"], [40])
        self.assertIsNone(end["earned_score"])

    def test_early_mean_submission_leaves_commands_until_dynamic_boundary(self):
        actor = self.actor("mean")
        self.step(actor, "submit")
        actor.used = 17
        self.assertTrue(actor.allowed("run_command"))
        actor.used = 18
        self.assertFalse(actor.allowed("run_command"))

    def test_private_workspaces_shared_mounts_and_unique_receipts(self):
        first = self.actor("mean", seat=0)
        second = self.actor("mean", seat=1)
        successor = self.actor("mean", seat=0, generation=2)
        for actor in (first, second, successor):
            self.assertEqual(actor.box.mounts[0][2], "rw,z")
            self.assertEqual(actor.box.mounts[1][2], "ro,z")
            self.step(actor, "submit")
        self.assertNotEqual(first.workspace, second.workspace)
        self.assertEqual(first.box.mounts, second.box.mounts)
        self.assertEqual(len(snapshot_regular(first.receipts)), 3)
        wiki = Path(first.box.mounts[0][0])
        write_regular(wiki, "method.txt", b"actual edit")
        self.assertEqual(snapshot_regular(Path(second.box.mounts[0][0]))["method.txt"], b"actual edit")
        (wiki / "method.txt").unlink()
        self.assertEqual(snapshot_regular(Path(successor.box.mounts[0][0])), {})

    def test_missing_and_symlink_submission_are_invalid_not_host_reads(self):
        actor = self.actor()
        (actor.workspace / "submission.json").unlink()
        (actor.workspace / "submission.json").symlink_to(self.root / "secret.json")
        save(self.root / "secret.json", self.target)
        self.step(actor, "submit")
        receipt = read(actor.receipts / actor.public_receipts[0])
        self.assertIsNone(receipt["submission"])
        self.assertIn("error", receipt["feedback"])

    def test_late_api_response_never_executes(self):
        actor = self.actor()
        actor.start()
        client = Mock()

        def late(*args, **kwargs):
            actor.deadline = "2000-01-01T00:00:00+00:00"
            return {"tool_calls": [call("run_command", {"command": "true"})]}, {}

        client.complete.side_effect = late
        actor.client = client
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            actor.step()
        self.assertEqual(actor.box.events, ["start", "freeze"])
        self.assertEqual(actor.used, 0)
        actor.error = "Execution deadline reached"
        actor.finish()
        self.assertFalse(read(actor.directory / "end.json")["normal"])

    def test_expired_deadline_blocks_api_and_queued_commands(self):
        actor = self.actor()
        actor.deadline = "2000-01-01T00:00:00+00:00"
        actor.client = Mock()
        actor.pending.append(call("run_command", {"command": "true"}))
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            actor.step()
        actor.client.complete.assert_not_called()
        self.assertEqual(actor.box.events, [])
        with self.assertRaises(ValueError):
            runtime.require_time("2099-01-01")

    def test_tool_free_responses_are_bounded_technical_failure(self):
        actor = self.actor("mean")
        actor.client = Mock()
        actor.client.complete.return_value = ({"content": "done"}, {})
        for _ in range(3):
            actor.step()
        self.assertTrue(actor.finished)
        end = read(actor.directory / "end.json")
        self.assertFalse(end["normal"])
        self.assertIsNone(end["earned_score"])
        self.assertEqual(actor.used, 0)

    def test_default_matrix_and_offline_preparation(self):
        for agents, expected in ((1, 18), (4, 144)):
            spec = run.default_spec({"model": "config.json"}, IMAGE, agents=agents)
            self.assertEqual(len(run.schedule(spec)), expected)
        with patch.object(run, "verify_image", side_effect=AssertionError("Offline only")):
            directory, registration = self.prepared()
            self.assertEqual(registration["session_cap"], 2)
            self.assertEqual(run.checked(directory), registration)
        self.assertFalse((directory / "starts.jsonl").exists())
        with self.assertRaises(FileExistsError):
            run.prepare(self.root / "spec.json", directory)

    def test_source_binding_change_rejected(self):
        directory, _ = self.prepared()
        with patch.object(run, "bindings", return_value={"changed": "hash"}):
            with self.assertRaisesRegex(RuntimeError, "Source changed"):
                run.checked(directory)

    def test_changed_material_blocks_next_claim(self):
        directory, registration = self.prepared()
        run.claim_start(directory, registration, registration["schedule"][0], DEADLINE, 2)
        (directory / "materials/prefix-01/README.md").write_text("changed")
        with self.assertRaisesRegex(RuntimeError, "materials changed"):
            run.claim_start(directory, registration, registration["schedule"][1], DEADLINE, 2)
        self.assertEqual(len((directory / "starts.jsonl").read_text().splitlines()), 1)

    def test_guard_rejects_replaced_registration_even_with_matching_sidecar(self):
        directory, registration = self.prepared()
        original_digest = digest_json(registration)
        registration["created_at"] = "changed"
        save(directory / "registration.json", registration)
        (directory / "registration.sha256").write_text(digest_json(registration))
        with self.assertRaisesRegex(RuntimeError, "registration changed"):
            run.execution_guard(directory, original_digest, DEADLINE)

    def test_changes_during_api_block_returned_command(self):
        directory, registration = self.prepared()
        actor = self.actor()
        actor.guard = lambda: run.execution_guard(directory, digest_json(registration), DEADLINE)
        actor.client = Mock()

        def changed(*args, **kwargs):
            (directory / "host/target.json").write_text("[]")
            return {"tool_calls": [call("run_command", {"command": "true"})]}, {}

        actor.client.complete.side_effect = changed
        with self.assertRaisesRegex(RuntimeError, "Target changed"):
            actor.step()
        self.assertEqual(actor.box.events, [])

    def test_source_change_prevents_provider_invocation(self):
        directory, registration = self.prepared()
        actor = self.actor()
        actor.guard = lambda: run.execution_guard(directory, digest_json(registration), DEADLINE)
        actor.client = Mock()
        with patch.object(run, "bindings", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "Source changed"):
                actor.step()
        actor.client.complete.assert_not_called()

    def test_material_and_target_tampering_rejected(self):
        directory, _ = self.prepared()
        material = directory / "materials/prefix-01/README.md"
        original = material.read_bytes()
        material.write_bytes(original + b"changed")
        with self.assertRaisesRegex(RuntimeError, "materials changed"):
            run.checked(directory)
        material.write_bytes(original)
        (directory / "host/target.json").write_text("[]")
        with self.assertRaisesRegex(RuntimeError, "Target changed"):
            run.checked(directory)

    def test_config_tampering_rejected_even_with_new_registration_digest(self):
        directory, registration = self.prepared()
        registration["configs"]["example"]["model"] = "different"
        save(directory / "registration.json", registration)
        (directory / "registration.sha256").write_text(digest_json(registration))
        with self.assertRaisesRegex(RuntimeError, "Configuration changed"):
            run.checked(directory)

    def test_cap_claims_no_refunds_and_no_duplicate(self):
        directory, registration = self.prepared()
        actor_spec = registration["schedule"][0]
        with self.assertRaisesRegex(RuntimeError, "equal"):
            run.claim_start(directory, registration, actor_spec, DEADLINE, 3)
        self.assertFalse((directory / "starts.jsonl").exists())
        run.claim_start(directory, registration, actor_spec, DEADLINE, 2)
        with self.assertRaisesRegex(RuntimeError, "already claimed"):
            run.claim_start(directory, registration, actor_spec, DEADLINE, 2)
        run.claim_start(directory, registration, registration["schedule"][1], DEADLINE, 2)
        with self.assertRaisesRegex(RuntimeError, "allocation"):
            run.claim_start(directory, registration, actor_spec, DEADLINE, 2)
        self.assertEqual(len((directory / "starts.jsonl").read_text().splitlines()), 2)

    def test_explicit_cap_and_image_gate_before_execution(self):
        directory, _ = self.prepared()
        with patch.object(run, "verify_image") as verify:
            with self.assertRaisesRegex(RuntimeError, "equal"):
                run.run(directory, 1, DEADLINE)
            verify.assert_not_called()
        with patch.object(run, "verify_image", side_effect=RuntimeError("Wrong image")):
            with self.assertRaisesRegex(RuntimeError, "Wrong image"):
                run.run(directory, 2, DEADLINE)
        self.assertFalse((directory / "execution-start.json").exists())
        with patch.object(run.subprocess, "run", return_value=Mock(stdout="sha256:" + "b" * 64)):
            with self.assertRaisesRegex(RuntimeError, "image"):
                run.verify_image(IMAGE)

    def test_failed_generation_blocks_descendants_and_no_resume(self):
        directory, _ = self.prepared(generations=3)
        with patch.object(run, "verify_image"), patch.object(runtime, "run_generation",
                return_value={"normal": False, "error": "failure"}) as generation:
            result = run.run(directory, 3, DEADLINE)
            self.assertEqual(generation.call_count, 1)
            self.assertEqual([row.get("status") for row in result["generations"]][1:],
                             ["blocked_by_predecessor", "blocked_by_predecessor"])
            with self.assertRaisesRegex(RuntimeError, "no resume"):
                run.run(directory, 3, DEADLINE)

    def test_generation_round_robin_claims_precede_api_and_preserves_state(self):
        wiki = self.root / "chain/wiki"
        wiki.mkdir(parents=True)
        write_regular(wiki, "method.txt", fixture.METHOD.encode())
        claimed, completed = [], []

        def client(config):
            self.assertEqual(len(claimed), 4)
            instance = Mock()
            instance.complete.return_value = ({"tool_calls": [call("submit")]}, {})
            completed.append(instance)
            return instance

        spec = {"chain": "example", "prefix": 1, "scoring": "final", "generation": 1}
        with patch.object(runtime, "Client", side_effect=client):
            result = runtime.run_generation(self.root / "generation", spec, CONFIG, self.target,
                                           IMAGE, wiki, 100, 4, DEADLINE, claimed.append)
        self.assertTrue(result["normal"])
        self.assertEqual(len(claimed), 4)
        self.assertEqual(len(completed), 4)
        self.assertEqual(len(snapshot_regular(wiki.parent / "submissions")), 4)
        rounds = read(self.root / "generation/meta/rounds/01.json")
        self.assertEqual(set(rounds["seats"]), {0, 1, 2, 3})
        self.assertEqual(snapshot_regular(wiki), {"method.txt": fixture.METHOD.encode()})
        self.assertEqual(read(self.root / "generation/meta/incoming.json"),
                         read(self.root / "generation/meta/outgoing.json"))

    def test_default_spec_cli_has_no_runtime_side_effect(self):
        with patch("builtins.print") as output:
            main(["default-spec", "--model", "example=config.json", "--image", IMAGE,
                  "--agents", "4", "--scoring", "mean"])
        spec = json.loads(output.call_args.args[0])
        self.assertEqual(spec["conditions"], ["method", "empty"])
        self.assertEqual(spec["scoring"], "mean")

    def test_swallowed_shutdown_failure_stops_sibling_dispatch(self):
        wiki = self.root / "chain/wiki"
        wiki.mkdir(parents=True)
        actors, dispatched = [], []
        original_start = runtime.Actor.start
        original_step = runtime.Actor.step

        def start(actor):
            actors.append(actor)
            original_start(actor)

        def step(actor):
            dispatched.append(actor.spec["seat"])
            actor.response_failures = 2
            actor.client = Mock()
            actor.client.complete.return_value = ({"content": "done"}, {})
            actor.box.stop = Mock(side_effect=RuntimeError("shutdown failed"))
            original_step(actor)

        spec = {"chain": "example", "prefix": 1, "scoring": "final", "generation": 1}
        with patch.object(runtime.Actor, "start", start), patch.object(runtime.Actor, "step", step):
            result = runtime.run_generation(self.root / "generation", spec, CONFIG, self.target,
                                           IMAGE, wiki, 100, 4, DEADLINE, Mock())
        self.assertEqual(len(dispatched), 1)
        self.assertFalse(result["normal"])
        self.assertIn("unverified shutdown", result["error"])
        self.assertIsNone(result["outgoing"])
        self.assertEqual(sum(actor.stopped["verified"] for actor in actors), 3)
        self.assertTrue(all(actor.finished for actor in actors))
        for actor in actors:
            end = read(actor.directory / "end.json")
            self.assertFalse(end["normal"])
            self.assertIsNone(end["earned_score"])

    def test_host_archive_failure_is_technical_not_invalid_submission(self):
        wiki = self.root / "chain/wiki"
        wiki.mkdir(parents=True)
        original_archive = runtime.archive
        fail_archive = False

        def archive(meta, raw):
            if fail_archive:
                raise OSError("host archive unavailable")
            return original_archive(meta, raw)

        def complete(*args, **kwargs):
            nonlocal fail_archive
            fail_archive = True
            return {"tool_calls": [call("submit")]}, {}

        client = Mock()
        client.complete.side_effect = complete
        spec = {"chain": "example", "prefix": 1, "scoring": "final", "generation": 1}
        with patch.object(runtime, "archive", archive), patch.object(runtime, "Client", return_value=client):
            result = runtime.run_generation(self.root / "generation", spec, CONFIG, self.target,
                                           IMAGE, wiki, 100, 1, DEADLINE, Mock())
        end = read(self.root / "generation/seat-0/end.json")
        self.assertFalse(result["normal"])
        self.assertFalse(end["normal"])
        self.assertEqual(end["status"], "technical_failure")
        self.assertIn("host archive unavailable", end["error"])
        self.assertIsNone(end["earned_score"])
        self.assertEqual(end["submissions_used"], 0)
        self.assertEqual(snapshot_regular(wiki.parent / "submissions"), {})


if __name__ == "__main__":
    unittest.main()
