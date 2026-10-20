import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.util import read, sha256
from parabox.tasks.wiki import episode
from parabox.tasks.wiki.service import ObjectService


def response(name, arguments):
    message = {"tool_calls": [{"id": "call", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}]}
    return message, {"scripted": True}


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "participant"
        self.client = self.enterContext(patch.object(episode, "Client"))
        self.box = self.enterContext(patch.object(episode, "FastBox"))
        self.stop = self.enterContext(patch.object(episode, "shutdown", return_value={"verified": True}))
        self.box.return_value.exec.return_value = (0, "ok")
        self.client.return_value.complete.return_value = response("submit", {})
        self.files = {"README.md": b"Use the tools.", "PROBLEM.md": b"Implement solve.",
                      "solution.py": b"def solve(value):\n    return []\n", "examples.py": b""}
        self.config = {"model": "mock", "api_key": "never-save-secret",
                       "base_url": "https://user:password@invalid", "wire": "chat"}

    def run_episode(self, incoming=None, deadline="2099-01-01T00:00:00+00:00"):
        return episode.run_episode(self.directory, {"actor": "author", "package": "events", "score": 30},
                                   self.config, "image", files=self.files, incoming=incoming or {},
                                   deadline=deadline)

    def test_submit_freezes_and_cleans_service_without_grading(self):
        end = self.run_episode({"shared/wiki/notes.md": b"old", "shared/incoming/source.json": b"{}"})
        self.assertTrue(end["normal"])
        self.assertEqual(end["action"], "submit")
        self.assertIsNone(end["awarded_score"])
        self.assertEqual(end["budget_used"], 1)
        self.assertEqual(end["final_solution"]["sha256"], sha256(self.files["solution.py"]))
        self.assertTrue(end["service_closed"])
        self.stop.assert_called_once()
        self.client.return_value.complete.assert_called_once()
        self.assertFalse((self.directory / "grading.json").exists())
        mounts = self.box.call_args.kwargs["mounts"]
        self.assertEqual(mounts[0][1:], ("/service", "ro"))
        self.assertFalse(Path(mounts[0][0]).exists())
        self.assertNotIn(str(self.directory), mounts[0][0])
        self.assertEqual(mounts[1][1:], ("/workspace/shared/incoming", "ro"))
        self.assertTrue(self.box.call_args.args[0].startswith("session-"))
        config = (self.directory / "meta/config.json").read_text()
        self.assertNotIn("never-save-secret", config)
        self.assertNotIn("password", config)
        self.assertEqual(read(self.directory / "meta/prompts.json")["messages"][0]["content"], episode.SYSTEM)
        self.assertEqual([item["function"]["name"] for item in episode.TOOLS], ["run_command", "submit"])

    def test_cumulative_wiki_and_solution_snapshots(self):
        def edit(command, timeout):
            workspace = self.directory / "workspace"
            (workspace / "solution.py").write_bytes(b"changed")
            (workspace / "shared/wiki/notes.md").write_bytes(b"edited")
            (workspace / "shared/wiki/new.md").write_bytes(b"new")
            return 0, "ok"
        self.box.return_value.exec.side_effect = edit
        self.client.return_value.complete.side_effect = [response("run_command", {"command": "edit"}),
                                                        response("submit", {})]
        end = self.run_episode({"shared/wiki/notes.md": b"old", "shared/wiki/kept.md": b"keep"})
        self.assertEqual(end["budget_used"], 2)
        self.assertEqual(end["outgoing"]["files"], {"notes.md": sha256(b"edited"),
                                                   "new.md": sha256(b"new"), "kept.md": sha256(b"keep")})
        action = read(self.directory / "meta/actions/t01-00.json")
        self.assertEqual(action["before"]["wiki"]["files"]["notes.md"], sha256(b"old"))
        self.assertEqual(action["after"]["solution"]["sha256"], sha256(b"changed"))
        self.assertIn("remaining_budget=59", action["result"])
        for raw in (b"old", b"edited", b"new", b"keep", b"changed"):
            self.assertEqual((self.directory / "meta/artifacts" / sha256(raw)).read_bytes(), raw)

    def test_service_requests_share_shell_budget_and_are_external(self):
        captured = {}
        def create(objects, budget, audit):
            captured["service"] = ObjectService(objects, budget, audit)
            self.assertNotIn("workspace", audit.parts)
            self.assertIn("private/events/0", objects)
            return captured["service"]
        def probe(command, timeout):
            for unused in range(75):
                captured["service"].request(b'{"object":"public/../private/events/0"}')
            return 0, "done"
        self.box.return_value.exec.side_effect = probe
        self.client.return_value.complete.return_value = response("run_command", {"command": "probe"})
        with patch.object(episode, "ObjectService", side_effect=create):
            end = self.run_episode()
        self.assertEqual(end["budget_used"], 60)
        self.assertEqual(end["awarded_score"], 0)
        self.assertTrue(end["normal"])
        self.assertIsNone(end["action"])
        self.assertEqual(end["requests"], 1)
        records = (self.directory / "meta/service.jsonl").read_text().splitlines()
        accepted = [json.loads(row) for row in records if "rejection" not in json.loads(row)]
        self.assertEqual(len(accepted), 59)
        self.assertTrue(all(row["private_requested"] for row in accepted))

    def test_service_is_sealed_before_submit_shutdown(self):
        captured = {}

        def create(objects, budget, audit):
            captured["service"] = ObjectService(objects, budget, audit)
            return captured["service"]

        def stop(box):
            result = captured["service"].request(b'{"object":"public/../private/events/0"}')
            self.assertNotIn("case", result)
            return {"verified": True}

        self.stop.side_effect = stop
        with patch.object(episode, "ObjectService", side_effect=create):
            end = self.run_episode()
        self.assertTrue(end["normal"])
        self.assertEqual(end["budget_used"], 1)

    def test_service_is_sealed_on_client_failure(self):
        captured = {}

        def create(objects, budget, audit):
            captured["service"] = ObjectService(objects, budget, audit)
            return captured["service"]

        def stop(box):
            self.assertNotIn("case", captured["service"].request(
                b'{"object":"public/../private/events/0"}'))
            return {"verified": True}

        self.stop.side_effect = stop
        self.client.return_value.complete.side_effect = RuntimeError("test")
        with patch.object(episode, "ObjectService", side_effect=create):
            end = self.run_episode()
        self.assertFalse(end["normal"])
        self.assertTrue(end["service_closed"])

    def test_malformed_actions_and_no_tool_cost_budget(self):
        invalid, raw = response("submit", {})
        invalid["tool_calls"][0]["function"]["arguments"] = "{"
        self.client.return_value.complete.side_effect = [
            ({"content": "done"}, {}), response("inspect", {}),
            response("run_command", {"command": 42}), (invalid, raw),
            response("submit", []), response("submit", {})]
        end = self.run_episode()
        self.assertEqual(end["budget_used"], 6)
        self.assertEqual(end["action"], "submit")
        self.box.return_value.exec.assert_not_called()

    def test_multiple_calls_are_charged_but_not_executed(self):
        message, raw = response("run_command", {"command": "true"})
        message["tool_calls"].extend(response("submit", {})[0]["tool_calls"])
        self.client.return_value.complete.side_effect = [(message, raw), response("submit", {})]
        end = self.run_episode()
        self.assertEqual(end["budget_used"], 3)
        self.box.return_value.exec.assert_not_called()
        self.assertEqual(len(list((self.directory / "meta/actions").glob("*.json"))), 3)

    def test_turn_exhaustion_is_normal_zero_score(self):
        self.client.return_value.complete.return_value = response("run_command", {"command": "true"})
        end = self.run_episode()
        self.assertEqual(end["requests"], 40)
        self.assertEqual(end["budget_used"], 40)
        self.assertEqual(end["status"], "no_submission")
        self.assertEqual(end["awarded_score"], 0)

    def test_last_budget_unit_can_submit(self):
        with patch.object(episode, "BUDGET", 1):
            end = self.run_episode()
        self.assertEqual(end["status"], "submitted")
        self.assertEqual(end["remaining_budget"], 0)

    def test_client_failure_is_technical_and_cleans_service(self):
        self.client.return_value.complete.side_effect = RuntimeError("never-save-secret")
        end = self.run_episode()
        self.assertEqual(end["status"], "technical_failure")
        self.assertIsNone(end["awarded_score"])
        self.assertTrue(end["shutdown_verified"])
        self.assertTrue(end["service_closed"])
        self.assertNotIn("never-save-secret", (self.directory / "end.json").read_text())

    def test_shutdown_failure_prevents_frozen_submission(self):
        self.stop.return_value = {"verified": False}
        end = self.run_episode()
        self.assertFalse(end["normal"])
        self.assertEqual(end["final_solution"], {})
        self.assertTrue(end["service_closed"])
        self.assertTrue((self.directory / "meta/actions/t01-00.json").exists())
        self.assertFalse((self.directory / "meta/submission-intent.json").exists())

    def test_start_failure_cleans_service_without_client(self):
        self.box.return_value.start.side_effect = RuntimeError("start failed")
        end = self.run_episode()
        self.assertFalse(end["normal"])
        self.assertTrue(end["service_closed"])
        self.client.assert_not_called()

    def test_service_start_failure_is_recorded(self):
        with patch.object(episode, "ServiceServer", side_effect=OSError("socket failure")):
            end = self.run_episode()
        self.assertFalse(end["normal"])
        self.assertTrue(end["service_closed"])
        self.box.assert_not_called()
        self.client.assert_not_called()

    def test_container_runtime_error_is_technical(self):
        self.box.return_value.exec.return_value = (126, "Error: crun: cgroup.procs")
        self.client.return_value.complete.return_value = response("run_command", {"command": "true"})
        end = self.run_episode()
        self.assertEqual(end["status"], "technical_failure")
        self.assertEqual(end["requests"], 1)

    def test_expired_deadline_never_starts_and_late_response_never_executes(self):
        with self.assertRaises(RuntimeError):
            self.run_episode(deadline="2000-01-01T00:00:00+00:00")
        self.client.assert_not_called()
        with patch.object(episode, "before_deadline", side_effect=[True, True, False]):
            end = self.run_episode()
        self.assertTrue(end["deadline_reached"])
        self.assertIsNone(end["action"])
        self.box.return_value.exec.assert_not_called()

    def test_existing_episode_is_not_restarted(self):
        end = self.run_episode()
        self.assertEqual(self.run_episode(), end)
        self.client.assert_called_once()
        (self.directory / "end.json").unlink()
        with self.assertRaises(RuntimeError):
            self.run_episode()

    def test_input_paths_and_sizes_are_bounded(self):
        for incoming in ({"../outside": b"x"}, {"shared/../outside": b"x"},
                         {"shared/wiki/../../solution.py": b"x"}, {"solution.py": b"x"},
                         {"shared/wiki/huge": b"x" * (4 * 1024 * 1024 + 1)}):
            with self.subTest(paths=list(incoming)), self.assertRaises(ValueError):
                self.run_episode(incoming)
        self.client.assert_not_called()

    def test_wiki_rejects_external_parent_symlinks(self):
        root = self.directory
        (root / "workspace").mkdir(parents=True)
        outside = root / "outside"
        (outside / "wiki").mkdir(parents=True)
        (outside / "wiki/secret").write_bytes(b"secret")
        (root / "workspace/shared").symlink_to(outside, target_is_directory=True)
        result = episode.snapshot(root / "workspace", root / "meta")
        self.assertIn("error", result["wiki"])
        self.assertFalse((root / "meta/artifacts" / sha256(b"secret")).exists())

    def test_wiki_omits_links_and_rejects_oversized_files(self):
        workspace, meta = self.directory / "workspace", self.directory / "meta"
        wiki = workspace / "shared/wiki"
        wiki.mkdir(parents=True)
        secret = self.directory / "secret"
        secret.write_bytes(b"secret")
        (wiki / "link").symlink_to(secret)
        self.assertEqual(episode.wiki_snapshot(workspace, meta), {"files": {}})
        with (wiki / "huge").open("wb") as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
        self.assertIn("error", episode.snapshot(workspace, meta)["wiki"])
        self.assertFalse((meta / "artifacts" / sha256(b"secret")).exists())

    def test_fastbox_has_no_network(self):
        from parabox.tasks.wiki.helpers import FastBox
        box = FastBox("session-test", self.directory, "image")
        argv = box.run_argv()
        self.assertEqual(argv[argv.index("--network") + 1], "none")


@unittest.skipUnless(os.environ.get("PARABOX_EPISODE_TEST_IMAGE"), "Set a local sandbox image for live integration")
class SandboxIntegrationTests(unittest.TestCase):
    def test_real_socket_metering_archive_and_teardown_with_scripted_client(self):
        from parabox.tasks.wiki.prompts import workspace_files
        with tempfile.TemporaryDirectory(prefix="session-test-") as temporary:
            directory = Path(temporary) / "episode"
            command = (
                "test -S /service/examples.sock && "
                "test $(ls -A /service | wc -l) -eq 1 && "
                "! touch /service/forbidden; "
                "python examples.py public/events/0 && "
                "python examples.py public/../private/inventory/0 && "
                "printf 'updated' > shared/wiki/notes.md && "
                "printf 'new' > shared/wiki/new.md"
            )
            with patch.object(episode, "Client") as client:
                client.return_value.complete.side_effect = [response("run_command", {"command": command}),
                                                            response("submit", {})]
                end = episode.run_episode(
                    directory, {"actor": "test", "package": "events", "score": 30},
                    {"model": "scripted"}, os.environ["PARABOX_EPISODE_TEST_IMAGE"],
                    files=workspace_files("events", 30), incoming={"shared/wiki/notes.md": b"old"},
                    deadline="2099-01-01T00:00:00+00:00")
            self.assertTrue(end["normal"], end)
            self.assertTrue(end["shutdown_verified"])
            self.assertTrue(end["service_closed"])
            self.assertEqual(end["budget_used"], 4)
            self.assertEqual(end["initial_solution"], end["final_solution"])
            self.assertEqual(end["outgoing"]["files"], {"notes.md": sha256(b"updated"), "new.md": sha256(b"new")})
            action = read(directory / "meta/actions/t01-00.json")
            self.assertIn("Read-only file system", action["result"])
            self.assertIn("private/inventory/0", action["result"])
            records = [json.loads(line) for line in (directory / "meta/service.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertTrue(records[1]["private_requested"])


if __name__ == "__main__":
    unittest.main()
