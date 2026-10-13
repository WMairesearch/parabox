import json
import tempfile
import unittest
from pathlib import Path

from parabox.session import run_session
from parabox.studies.discovery import check as C
from parabox.studies.discovery import design as D
from parabox.studies.discovery import notes as N
from parabox.studies.discovery import run as RUN
from parabox.studies.discovery import score as S
from parabox.tasks.lean import prompts as P
from parabox.tasks.lean.discovery import DiscoveryLeanTask
from parabox.tasks.lean.task import ORACLE_DIR
from parabox.util import save
from tests.helpers import FakeBox, call


class FakeDiscoveryTask(DiscoveryLeanTask):
    def compile(self, box, relative):
        return 0, ""


class ExplorerClient:
    """Lists the directory, reads the note, writes the exploit, submits, finishes."""

    model = "scripted"

    def complete(self, messages, tools=None):
        step = sum(1 for m in messages if m["role"] == "assistant")
        script = (
            [call("list_dir", {"path": "."})],
            [call("read_file", {"path": N.NOTE_PATH})],
            [call("write_file", {"path": "Problem.lean", "content": (ORACLE_DIR / "odd-perfect-exploit.lean").read_text()})],
            [call("submit", {})],
            [call("finish", {"report": "Not a proof."})],
        )
        return {"role": "assistant", "content": "", "tool_calls": script[min(step, len(script) - 1)]}, {"step": step}


def fake_run(directory: Path) -> list[dict]:
    schedule = D.design(["odd_perfect"], 1)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "schedule.json", schedule)
    save(directory / "protocol.json", {"frozen": {"note_sha256": N.digests()}})
    task = FakeDiscoveryTask()
    for row in schedule:
        target = directory / "sessions" / row["actor"]
        run_session(task, ExplorerClient(), FakeBox(target / "workspace"), target, row,
                    integrity="none", shared=False, opening=[], extra_files=RUN.extra_files(row["arm"]))
        save(target / "meta" / "delivered-note.json", {"arm": row["arm"], "note": N.note_for(row["arm"]) or ""})
    return schedule


class PromptTest(unittest.TestCase):
    def test_system_has_no_integrity_and_task_names_list_dir(self):
        task = DiscoveryLeanTask()
        system = task.system(integrity="none", shared=False)
        self.assertNotIn("Proof Integrity", system)
        self.assertNotIn("STRICTLY FORBIDDEN", system)
        self.assertIn("list_dir", system)
        self.assertIn("list_dir", task.task(shared=False))

    def test_tools_have_list_dir_and_no_method(self):
        names = [t["function"]["name"] for t in DiscoveryLeanTask().tools(shared=False)]
        self.assertIn("list_dir", names)
        submit = next(t for t in DiscoveryLeanTask().tools(shared=False) if t["function"]["name"] == "submit")
        self.assertEqual(submit["function"]["parameters"]["properties"], {})


class ListDirTest(unittest.TestCase):
    def test_list_dir_shows_the_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            schedule = D.design(["odd_perfect"], 1)
            method_row = next(r for r in schedule if r["arm"] == "method")
            sdir = target / "sessions" / method_row["actor"]
            run_session(FakeDiscoveryTask(), _ListOnce(), FakeBox(sdir / "workspace"), sdir, method_row,
                        integrity="none", shared=False, opening=[], extra_files=RUN.extra_files("method"))
            messages = json.loads((sdir / "meta" / "requests" / "t02.json").read_text())["messages"]
            listing = next(m["content"] for m in messages if m.get("role") == "tool")
            self.assertIn("shared/note-from-K7.txt", listing)
            self.assertIn("Problem.lean", listing)


class _ListOnce:
    model = "scripted"

    def complete(self, messages, tools=None):
        step = sum(1 for m in messages if m["role"] == "assistant")
        calls = [call("list_dir", {"path": "."})] if step == 0 else [call("finish", {"report": "done"})]
        return {"role": "assistant", "content": "", "tool_calls": calls}, {"step": step}


class RunTest(unittest.TestCase):
    def test_delivery_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fake_run(directory)
            result = C.check(directory)
            self.assertTrue(result["ok"], result["problems"])
            self.assertEqual(result["sessions"], 3)
            control = directory / "sessions" / "b00-control" / "workspace" / N.NOTE_PATH
            method = directory / "sessions" / "b00-method" / "workspace" / N.NOTE_PATH
            self.assertFalse(control.exists())
            self.assertTrue(method.exists())

    def test_check_catches_a_tampered_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fake_run(directory)
            bad = directory / "sessions" / "b00-help" / "meta" / "delivered-note.json"
            save(bad, {"arm": "help", "note": "tampered"})
            result = C.check(directory)
            self.assertFalse(result["ok"])
            self.assertTrue(any("help" in p for p in result["problems"]))

    def test_descriptors_separate_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fake_run(directory)
            desc = S.descriptors(directory)
            self.assertEqual(desc["sessions"], 3)
            self.assertEqual(desc["list_dir_rate"]["method"], 1.0)
            self.assertEqual(desc["read_note_rate"]["method"], 1.0)
            self.assertEqual(desc["read_note_rate"]["help"], 1.0)
            self.assertEqual(desc["read_note_rate"]["control"], 0.0)


if __name__ == "__main__":
    unittest.main()
