import tempfile
import unittest
from pathlib import Path

from parabox.session import IGNORED, run_session
from parabox.util import read
from tests.helpers import FakeBox, FakeTask, ScriptedClient


class SessionTest(unittest.TestCase):
    def run_one(self, shared, extra_call=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "s"
        client = ScriptedClient(extra_call=extra_call)
        spec = {"actor": "a", "problem": "odd_perfect", "arm": "dynamic" if shared else "isolated"}
        end = run_session(FakeTask(), client, FakeBox(target / "workspace"), target, spec,
                          integrity="library", shared=shared, opening=["Library:\n\nSeed recipe:\n\nx\n"] if shared else [])
        return end, target, client

    def test_a_session_saves_requests_submissions_and_contribution(self):
        end, target, _ = self.run_one(True)
        self.assertTrue(end["normal"] and end["finished"])
        self.assertEqual(end["accepted"], 1)
        self.assertEqual(len(list((target / "meta" / "requests").glob("t*.json"))), 4)
        contribution = read(target / "meta" / "contribution.json")
        self.assertEqual(contribution[0]["method"], "shadow Perfect with False")
        self.assertEqual(read(target / "meta" / "feedback.json")[0]["turn"], 3)

    def test_opening_is_on_turn_one(self):
        _, target, _ = self.run_one(True)
        messages = read(target / "meta" / "requests" / "t01.json")["messages"]
        self.assertEqual([m["role"] for m in messages], ["system", "user", "user"])
        self.assertTrue(messages[2]["content"].startswith("Library:"))

    def test_only_the_first_tool_call_runs(self):
        _, target, _ = self.run_one(True, extra_call=True)
        messages = read(target / "meta" / "requests" / "t02.json")["messages"]
        tools = [m for m in messages if m["role"] == "tool"]
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[1]["content"], IGNORED)

    def test_extra_files_are_written_into_the_workspace(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "s"
        run_session(FakeTask(), ScriptedClient(), FakeBox(target / "workspace"), target,
                    {"actor": "a", "problem": "odd_perfect"}, integrity="library", shared=False, opening=[],
                    extra_files={"notes/readme.txt": b"hello"})
        self.assertEqual((target / "workspace" / "notes" / "readme.txt").read_bytes(), b"hello")

    def test_ended_session_is_not_rerun(self):
        end, target, _ = self.run_one(False)
        again = run_session(FakeTask(), ScriptedClient(), FakeBox(target / "workspace"), target,
                            {"actor": "a", "problem": "odd_perfect"}, integrity="library", shared=False, opening=[])
        self.assertEqual(end, again)


if __name__ == "__main__":
    unittest.main()
