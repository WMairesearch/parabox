import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parabox.benchmark.ternary import episode, fixture


TARGET = [0] * 100
IMAGE = "sha256:" + "a" * 64
DEADLINE = "2999-01-01T00:00:00Z"


class Box:
    instances = []

    def __init__(self, name, workspace, image, limits, mounts):
        self.mounts = mounts
        Box.instances.append(self)

    def start(self):
        pass

    def freeze(self):
        pass

    def thaw(self):
        pass

    def exec(self, command, timeout, env=None):
        return 0, "ok"


def scripted(steps):
    """A client that answers each turn with the next step: a tool name, a callable, or a raw truncation."""
    class Client:
        requests = []

        def __init__(self, config):
            self.calls = 0

        def complete(self, messages, tools=None):
            Client.requests.append({"messages": [dict(message) for message in messages],
                                    "tools": [tool["function"]["name"] for tool in tools]})
            step = steps[min(self.calls, len(steps) - 1)]
            self.calls += 1
            if step == "truncated":
                return {"role": "assistant", "content": ""}, {"choices": [{"finish_reason": "length"}]}
            if callable(step):
                step = step()
            arguments = {"command": "true"} if step == "run_command" else {}
            return {"role": "assistant", "tool_calls": [{"id": f"call-{self.calls}",
                    "function": {"name": step, "arguments": json.dumps(arguments)}}]}, {}
    return Client


class TernaryContractTest(unittest.TestCase):
    def run_session(self, root, steps, protocol, *, agents=1, prefix=1, shutdown=None):
        wiki = root / "wiki"
        wiki.mkdir(exist_ok=True)
        client = scripted(steps)
        Box.instances = []
        with patch.object(episode, "SharedBox", Box), \
             patch.object(episode.base, "Client", client), \
             patch.object(episode.base, "shutdown", shutdown or (lambda box: {"verified": True})):
            result = episode.run_generation(root / "generation", {"prefix": prefix,
                "generation": 1, "actor": "example", "chain": "example"},
                {}, TARGET, IMAGE, wiki, 17, DEADLINE, agents=agents, protocol=protocol)
        ends = [json.loads(path.read_text())
                for path in sorted((root / "generation").glob("seat-*/end.json"))]
        return result, ends, client.requests

    def test_terminal_final_feedback_stays_private_until_verified_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipts_at_shutdown = []

            def shutdown(box):
                receipts_at_shutdown.append(sorted(path.name for path in (root / "submissions").iterdir()))
                return {"verified": True}

            result, [end], requests = self.run_session(root, ["submit"], fixture.TERMINAL,
                                                       shutdown=shutdown)
            self.assertTrue(result["normal"])
            self.assertEqual(receipts_at_shutdown[0], [])
            self.assertEqual(end["evaluations"][-1]["feedback_delivered_to_current_agent"], False)
            messages = json.loads((root / "generation/seat-0/meta/messages.json").read_text())
            self.assertEqual(messages[-1]["role"], "assistant")
            receipt = json.loads((root / "submissions/generation-01-seat-0.json").read_text())
            self.assertEqual(receipt["feedback"], {"score": 1})
            self.assertEqual((end["status"], end["earned_score"]), ("submitted", 1))

    def test_terminal_refuses_a_third_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, [end], requests = self.run_session(
                Path(temporary), ["test", "test", "test", "submit"], fixture.TERMINAL)
            self.assertEqual((end["tests_used"], end["used_calls"]), (2, 4))
            self.assertTrue(requests[3]["messages"][-1]["content"].startswith("Test limit reached."))
            self.assertEqual([event["feedback_delivered_to_current_agent"]
                              for event in end["evaluations"]], [True, True, False])

    def test_terminal_last_call_allows_only_submit(self):
        with tempfile.TemporaryDirectory() as temporary:
            steps = ["run_command"] * 20 + ["submit"]
            result, [end], requests = self.run_session(Path(temporary), steps, fixture.TERMINAL)
            self.assertEqual(requests[18]["tools"], ["run_command", "submit"])
            self.assertEqual(requests[19]["tools"], ["submit"])
            self.assertIn("Finalization only", requests[20]["messages"][-1]["content"])
            self.assertEqual((end["used_calls"], end["status"]), (20, "submitted"))

    def test_three_truncated_responses_are_a_technical_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, [end], requests = self.run_session(Path(temporary), ["truncated"], fixture.TERMINAL)
            self.assertFalse(result["normal"])
            self.assertEqual(end["error"], "Three consecutive truncated or tool-free responses")
            self.assertEqual((end["status"], end["earned_score"], end["used_calls"]),
                             ("technical_failure", None, 0))

    def test_repeated_feedback_and_mean_score(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def full_then_submit():
                (root / "generation/seat-0/workspace/submission.json").write_text(json.dumps(TARGET))
                return "submit"

            def prefix_then_submit():
                (root / "generation/seat-0/workspace/submission.json").write_text(json.dumps([0] + [-1] * 99))
                return "submit"

            result, [end], requests = self.run_session(
                root, ["submit", full_then_submit, prefix_then_submit], fixture.REPEATED)
            self.assertEqual(end["submission_scores"], [1, 100, 1])
            self.assertEqual(end["earned_score"], 34)
            self.assertEqual([event["feedback_delivered_to_current_agent"]
                              for event in end["evaluations"]], [True, True, False])
            self.assertIn("remaining_submissions=1", requests[2]["messages"][-1]["content"])
            self.assertEqual(len(list((root / "submissions").glob("*.json"))), 3)

    def test_repeated_reserves_remaining_calls_for_submissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            steps = ["run_command"] * 17 + ["submit"] * 3
            result, [end], requests = self.run_session(Path(temporary), steps, fixture.REPEATED)
            self.assertEqual(requests[16]["tools"], ["run_command", "submit"])
            self.assertEqual(requests[17]["tools"], ["submit"])
            self.assertEqual((end["used_calls"], end["submissions_used"], end["status"]),
                             (20, 3, "submitted"))

    def test_population_shares_one_live_wiki_and_read_only_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, ends, requests = self.run_session(root, ["submit"], fixture.TERMINAL, agents=4)
            self.assertEqual(len(ends), 4)
            self.assertEqual({box.mounts for box in Box.instances},
                             {((str(root / "wiki"), "/workspace/shared/wiki", "rw,z"),
                               (str(root / "submissions"), "/workspace/shared/submissions", "ro,z"))})


if __name__ == "__main__":
    unittest.main()
