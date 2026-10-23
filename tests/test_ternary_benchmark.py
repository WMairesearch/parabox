import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parabox.benchmark.ternary import episode, fixture
from parabox.benchmark.ternary.run import check, prepare, run, schedule


class ScriptedClient:
    def __init__(self, config):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        return {"role": "assistant", "tool_calls": [{"id": f"call-{self.calls}",
                "function": {"name": "submit", "arguments": "{}"}}]}, {}


class ScriptedBox:
    def __init__(self, name, workspace, image, limits, mounts):
        self.name = name

    def start(self):
        pass

    def freeze(self):
        pass

    def thaw(self):
        pass

    def stop(self):
        pass


class TernaryBenchmarkTest(unittest.TestCase):
    def test_evaluator_returns_only_prefix_error_or_next_value(self):
        target = [index % 3 for index in range(100)]
        self.assertEqual(fixture.evaluate(fixture.encode(target), target), {"score": 100})
        self.assertEqual(fixture.evaluate(fixture.encode(target[:2]), target),
                         {"score": 0, "next_position": 3, "next_value": 2})
        self.assertEqual(fixture.evaluate(fixture.encode([2, 2]), target),
                         {"error": "Incorrect prefix"})

    def test_participant_material_is_operational(self):
        files = episode.participant_files(1, [0] * 100)
        text = files["README.md"].decode()
        self.assertNotIn("next_position", text)
        self.assertIn("Unused submissions contribute 0", text)
        self.assertIn("shared/submissions/", text)
        self.assertNotIn("sacrifice", text.lower())
        self.assertEqual([tool["function"]["name"] for tool in episode.TOOLS],
                         ["run_command", "submit"])

    def test_schedule_and_frozen_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model.json"
            model.write_text(json.dumps({"model": "example", "api_key_env": "EXAMPLE_KEY"}))
            spec = {"models": {"example": str(model)}, "image": "sha256:" + "a" * 64,
                    "seed": 17, "seats": 4}
            self.assertEqual(len(schedule(spec["models"], 4)), 6)
            plan = prepare(root / "run", spec)
            self.assertEqual(plan["session_cap"], 144)
            self.assertEqual(check(root / "run")["session_cap"], 144)
            model.write_text("{}")
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                check(root / "run")

    def test_single_seat_uses_method_condition(self):
        self.assertEqual(len(schedule({"example": "model.json"}, 1)), 3)
        self.assertEqual({row["condition"] for row in schedule({"example": "model.json"}, 1)},
                         {"method"})

    def test_scored_submissions_publish_three_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            with patch.object(episode, "SharedBox", ScriptedBox), \
                 patch.object(episode.base, "Client", ScriptedClient), \
                 patch.object(episode.base, "shutdown", return_value={"verified": True}):
                result = episode.run_generation(root / "generation", {"prefix": 1,
                    "generation": 1, "actor": "example", "chain": "example"},
                    {}, [0] * 100, "sha256:" + "a" * 64, wiki, 17,
                    "2999-01-01T00:00:00Z", agents=1)
            end = json.loads((root / "generation/seat-0/end.json").read_text())
            self.assertTrue(result["normal"])
            self.assertEqual(end["submission_scores"], [1, 1, 1])
            self.assertEqual(end["earned_score"], 1)
            self.assertEqual(len(end["public_receipts"]), 3)
            self.assertEqual(len(list((root / "submissions").glob("*.json"))), 3)

    def test_wrong_authorization_does_not_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model.json"
            model.write_text(json.dumps({"model": "example", "api_key_env": "EXAMPLE_KEY"}))
            prepare(root / "run", {"models": {"example": str(model)},
                    "image": "sha256:" + "a" * 64, "seed": 17, "seats": 1})
            with self.assertRaisesRegex(ValueError, "Authorization"):
                run(root / "run", authorize_session_cap=17,
                    deadline="2999-01-01T00:00:00Z")
            self.assertFalse((root / "run/starts.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
