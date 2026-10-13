import json
import tempfile
import unittest
from pathlib import Path

from parabox.session import run_session
from parabox.studies.relay import design as D
from parabox.studies.relay import library as Lib
from parabox.studies.relay_files import check as C
from parabox.studies.relay_files import run as RUN
from parabox.studies.relay_files import score as S
from parabox.tasks.lean import prompts as P
from parabox.tasks.lean.files import FilesLeanTask
from parabox.tasks.lean.task import POOL
from parabox.util import digest_json, read, save
from tests.helpers import FakeBox, ScriptedClient


class FakeFilesTask(FilesLeanTask):
    def compile(self, box, relative):
        return 0, ""


def fake_run(directory: Path, *, tamper=None, integrity="library") -> list[dict]:
    chains, schedule = D.design(POOL, blocks=1, generations=2)
    for row in schedule:
        row["problem"] = "odd_perfect"
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "schedule.json", schedule)
    save(directory / "protocol.json", {"frozen": {"integrity": integrity, "carry_method": False}})
    seed = RUN.load_seed()
    task = FakeFilesTask()
    for rows in D.by_generation(schedule):
        for row in rows:
            opening = RUN.delivery(directory, row, seed)
            if tamper:
                opening = tamper(row, opening)
            target = RUN.session_dir(directory, row["actor"])
            run_session(task, ScriptedClient(), FakeBox(target / "workspace"), target, row,
                        integrity=integrity, shared=D.SHARED[row["arm"]], opening=opening)
    return schedule


class PromptTest(unittest.TestCase):
    def test_isolated_arm_equals_the_relay_isolated_arm(self):
        self.assertEqual(FilesLeanTask().prompts_record(integrity="library", shared=False), P.record("library", False))

    def test_shared_submit_has_no_method_and_task_offers_none(self):
        submit = next(t for t in P.files_tools() if t["function"]["name"] == "submit")
        self.assertEqual(submit["function"]["parameters"]["properties"], {})
        self.assertNotIn("method note", P.files_task())
        self.assertIn("submit_feedback only", P.files_task())
        self.assertNotEqual(P.files_record("library")["sha256"], P.record("library", True)["sha256"])


class LibraryTest(unittest.TestCase):
    entries = [{"generation": 1, "problem": "beal", "turn": 3, "method": "shadow the id", "file": "theorem x := rfl"}]

    def test_render_drops_method_but_keeps_the_file(self):
        text = Lib.render("SEED", self.entries, carry_method=False)
        self.assertIn("Accepted file from generation 1 (beal), turn 3", text)
        self.assertIn("theorem x", text)
        self.assertNotIn("Method from generation", text)
        self.assertNotIn("shadow the id", text)

    def test_default_still_carries_method(self):
        self.assertIn("Method from generation", Lib.render("SEED", self.entries))


class RunTest(unittest.TestCase):
    def test_delivery_by_arm_and_no_method_in_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            schedule = fake_run(directory)
            result = C.check(directory)
            self.assertTrue(result["ok"], result["problems"])
            self.assertEqual(result["sessions"], 6)
            by_arm = {(row["arm"], row["generation"]): row for row in schedule}
            dynamic = read(RUN.session_dir(directory, by_arm[("dynamic", 2)]["actor"]) / "meta" / "opening.json")
            self.assertIn("Accepted file from generation 1", dynamic[0]["text"])
            self.assertNotIn("Method from generation", dynamic[0]["text"])
            static = read(RUN.session_dir(directory, by_arm[("static", 2)]["actor"]) / "meta" / "opening.json")
            self.assertNotIn("Accepted file", static[0]["text"])
            self.assertEqual(read(RUN.session_dir(directory, by_arm[("isolated", 2)]["actor"]) / "meta" / "opening.json"), [])

    def test_check_catches_a_tampered_library(self):
        def tamper(row, opening):
            if row["arm"] == "dynamic" and opening:
                return [opening[0] + "\nMethod from generation 1 (beal), turn 3:\n\nshadow\n"]
            return opening
        with tempfile.TemporaryDirectory() as tmp:
            fake_run(Path(tmp), tamper=tamper)
            result = C.check(Path(tmp))
            self.assertFalse(result["ok"])
            self.assertTrue(any("saved opening differs" in p for p in result["problems"]))

    def test_check_flags_a_method_in_the_delivered_library(self):
        entries = [{"generation": 1, "problem": "beal", "turn": 3, "method": "shadow", "file": "theorem x := rfl"}]
        clean = Lib.opening("dynamic", "SEED", entries, carry_method=False)[0]
        carried = Lib.opening("dynamic", "SEED", entries, carry_method=True)[0]
        self.assertNotIn("Method from generation", clean)
        self.assertIn("Method from generation", carried)

    def test_check_catches_a_changed_isolated_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            schedule = fake_run(directory)
            actor = next(r for r in schedule if r["arm"] == "isolated")["actor"]
            protocol = read(directory / "protocol.json")
            protocol["isolated_from"] = {"directory": "elsewhere", "sessions": {actor: "0" * 64}}
            save(directory / "protocol.json", protocol)
            result = C.check(directory)
            self.assertIn(f"{actor}: isolated session is not the copy recorded in protocol.json", result["problems"])


class IsolatedReuseTest(unittest.TestCase):
    def test_source_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            schedule = fake_run(source)
            frozen = {key: key for key in RUN.ISOLATED_KEYS}
            frozen["prompts"] = {"isolated": "same", "shared": "old"}
            design = {"blocks": 1, "generations": 2, "design_seed": 1, "pool": POOL}
            save(source / "protocol.json", {**design, "frozen": frozen})
            here = {**design, "frozen": {**frozen, "prompts": {"isolated": "same", "shared": "new"}}}
            self.assertEqual(RUN.check_isolated_source(source, here, schedule), [])
            other = {**here, "frozen": {**here["frozen"], "model": "another"}}
            self.assertEqual(RUN.check_isolated_source(source, other, schedule), ["frozen model differs"])
            gone = next(r for r in schedule if r["arm"] == "isolated")["actor"]
            (RUN.session_dir(source, gone) / "end.json").unlink()
            self.assertIn(f"{gone} did not end normally in the source",
                          RUN.check_isolated_source(source, here, schedule))


class CompareTest(unittest.TestCase):
    def test_compare_pairs_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            one, two = Path(tmp) / "one", Path(tmp) / "two"
            fake_run(one)
            fake_run(two)
            out = S.compare(one, two)
            self.assertEqual(out["dynamic"]["violation"]["value"], 0)
            self.assertTrue((one / "compare.json").exists())


if __name__ == "__main__":
    unittest.main()
