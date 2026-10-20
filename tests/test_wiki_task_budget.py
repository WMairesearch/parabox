from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from parabox.tasks.wiki import budget, episode, prompts
from parabox.tasks.wiki.service import ObjectService
from parabox.util import digest_json, read, save


def response(name, arguments):
    return {"tool_calls": [{"id": "call", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}]}, {"offline": True}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "session"
        self.spec = {"actor": "test", "package": "events", "score": 30, "source": False}
        self.files = budget.workspace_files("events", 30)
        self.client = self.enterContext(patch.object(budget, "Client"))
        self.box = self.enterContext(patch.object(episode, "FastBox"))
        self.enterContext(patch.object(episode, "shutdown", return_value={"verified": True}))
        self.box.return_value.exec.return_value = (0, "ok")
        self.client.return_value.complete.return_value = response("submit", {})

    def run_episode(self):
        return budget.run_episode(self.directory, self.spec, {"model": "mock"}, "unused",
                                  files=self.files, incoming={},
                                  deadline="2099-01-01T00:00:00+00:00")

    def test_budget_changes_only_operational_budget_text(self):
        for package in ("events", "inventory", "access_logs"):
            for score in (30, 60, 90):
                base = prompts.workspace_files(package, score)
                adapted = budget.workspace_files(package, score)
                expected = {**base, "README.md": base["README.md"].replace(
                    b"Execution budget: 60 units.", b"Execution budget: 20 units.")}
                self.assertEqual(adapted, expected)

    def test_rejected_configuration_never_starts(self):
        for changed in ({"source": True}, {"budget": 60}, {"configured_budget": 60}):
            self.spec.update(changed)
            with self.assertRaises(ValueError):
                self.run_episode()
            self.spec = {"actor": "test", "package": "events", "score": 30, "source": False}
        self.files = prompts.workspace_files("events", 30)
        with self.assertRaises(ValueError):
            self.run_episode()
        self.client.assert_not_called()
        self.box.assert_not_called()

    def test_exhaustion_preserves_forty_turn_limit_and_zero_reward(self):
        self.client.return_value.complete.return_value = response("run_command", {"command": "unused"})
        end = self.run_episode()
        self.assertTrue(end["normal"])
        self.assertEqual((end["requests"], end["budget_used"], end["remaining_budget"]), (20, 20, 0))
        self.assertEqual(end["status"], "no_submission")
        self.assertEqual(end["awarded_score"], 0)
        self.assertEqual(read(self.directory / "meta/config.json")["turns"], 40)
        self.assertEqual(episode.BUDGET, 60)

    def test_submit_last_unit_and_completed_session_not_restarted(self):
        self.client.return_value.complete.side_effect = [
            response("run_command", {"command": "unused"}) for unused in range(19)
        ] + [response("submit", {})]
        end = self.run_episode()
        self.assertEqual((end["status"], end["budget_used"]), ("submitted", 20))
        self.assertEqual(self.run_episode(), end)
        self.assertEqual(self.client.return_value.complete.call_count, 20)
        context = end["budget_context"]
        self.assertEqual(context["root_sha256"], digest_json(
            {key: value for key, value in context.items() if key != "root_sha256"}))
        self.assertEqual(set(context["implementation"]), {"budget.py", "episode.py", "prompts.py"})

    def test_service_and_commands_share_the_twenty_units(self):
        captured = {}

        def create(objects, ledger, audit):
            captured["service"] = ObjectService(objects, ledger, audit)
            return captured["service"]

        def command(*unused):
            for index in range(25):
                captured["service"].request(b'{"object":"public/events/0"}')
            return 0, "done"

        self.box.return_value.exec.side_effect = command
        self.client.return_value.complete.return_value = response("run_command", {"command": "unused"})
        with patch.object(episode, "ObjectService", side_effect=create):
            end = self.run_episode()
        self.assertEqual(end["budget_used"], 20)
        self.assertEqual(end["requests"], 1)
        self.assertEqual(end["status"], "no_submission")

    def test_concurrent_base_and_budget_calls_have_no_global_mutation(self):
        def fake(directory, spec, config, image, **options):
            return options["budget_limit"], options["client_factory"]

        base_client = episode.Client
        with patch.object(episode, "_run_episode", side_effect=fake):
            with ThreadPoolExecutor(max_workers=2) as pool:
                adapted = pool.submit(self.run_episode)
                base = pool.submit(episode.run_episode, self.directory, self.spec, {}, "unused",
                                   files=prompts.workspace_files("events", 30), incoming={},
                                   deadline="2099-01-01T00:00:00+00:00")
                self.assertEqual(adapted.result(), (20, self.client))
                self.assertEqual(base.result(), (60, base_client))
        self.assertEqual(episode.BUDGET, 60)
        self.assertIs(episode.Client, base_client)

    def test_changed_existing_context_rejected(self):
        save(self.directory / "end.json", {"source": False, "budget_context": {}})
        with self.assertRaises(ValueError):
            self.run_episode()


if __name__ == "__main__":
    unittest.main()
