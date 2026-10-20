from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark.grade import grade
from parabox.util import read, save


class BenchmarkGradeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.image = "sha256:" + "a" * 64
        self.rows = [
            {"actor": "core-test", "component": "core", "problem": "reverse_words",
             "gate": "open", "condition": "isolated", "turns": 50, "successor_actors": []},
            {"actor": "wiki-test", "component": "wiki", "package": "events"},
            {"actor": "unstarted", "component": "wiki", "package": "events"},
        ]
        save(self.root / "plan.json", {"sessions": self.rows})
        save(self.root / "spec.json", {"image": self.image})
        save(self.root / "execution/end.json", {"manifest_sha256": "bound"})
        for row in self.rows[:2]:
            target = self.root / "execution/sessions" / row["actor"]
            save(target / "end.json", {**row, "normal": True})
            save(target / "meta/spec.json", row)
            save(target / "meta/submissions.json", [{"turn": 2, "accepted": True}])
        self.addCleanup(patch.stopall)
        patch("parabox.benchmark.grade.check", return_value={"manifest_sha256": "bound"}).start()
        patch("parabox.model.Client", side_effect=AssertionError("No models")).start()
        patch("subprocess.run", side_effect=AssertionError("Injected audits only")).start()

    def test_image_bound_independent_grading_and_missingness(self):
        audit = {"violation": True, "audit_incomplete": True,
                 "turns": [{"violation": True}, {"violation": None}]}
        with patch("parabox.tasks.code.task.CodeTask.audit_session", return_value=audit), \
                patch("parabox.tasks.wiki.grader.session", return_value={"earned_score": 1}) as wiki:
            result = grade(self.root, image_verifier=lambda image: self.assertEqual(image, self.image))
        self.assertEqual(result["graded"], 2)
        self.assertEqual(result["unavailable"], 1)
        core = read(self.root / "execution/sessions/core-test/grading.json")
        self.assertTrue(core["accepted_invalid"])
        self.assertIsNone(core["audit_clean_accepted"])
        self.assertEqual(core["image"], self.image)
        self.assertEqual(wiki.call_args.kwargs["image"], self.image)

    def test_grader_failure_is_not_a_behavioral_zero(self):
        with patch("parabox.tasks.code.task.CodeTask.audit_session", side_effect=RuntimeError), \
                patch("parabox.tasks.wiki.grader.session", side_effect=RuntimeError):
            result = grade(self.root, image_verifier=lambda image: None)
        self.assertEqual(result["graded"], 0)
        self.assertEqual(result["unavailable"], 3)
        self.assertTrue(all("result" not in row for row in result["sessions"]))

    def test_normal_session_without_accepted_submission_has_no_observed_gap(self):
        save(self.root / "execution/sessions/core-test/meta/submissions.json", [])
        audit = {"violation": None, "reason": "no_accepted", "turns": []}
        with patch("parabox.tasks.code.task.CodeTask.audit_session", return_value=audit), \
                patch("parabox.tasks.wiki.grader.session", return_value={"earned_score": 1}):
            grade(self.root, image_verifier=lambda image: None)
        record = read(self.root / "execution/sessions/core-test/grading.json")
        self.assertFalse(record["accepted_invalid"])
        self.assertFalse(record["audit_clean_accepted"])

    def test_core_actual_turns_are_not_the_assigned_budget(self):
        target = self.root / "execution/sessions/core-test"
        save(target / "end.json", {**self.rows[0], "turns": 9, "normal": True})
        audit = {"violation": False, "turns": [{"violation": False}]}
        with patch("parabox.tasks.code.task.CodeTask.audit_session", return_value=audit), \
                patch("parabox.tasks.wiki.grader.session", return_value={"earned_score": 1}):
            result = grade(self.root, image_verifier=lambda image: None)
        self.assertEqual(result["sessions"][0]["status"], "graded")
        self.assertEqual(read(target / "end.json")["turns"], 9)
        self.assertEqual(read(target / "meta/spec.json")["turns"], 50)

    def test_core_changed_assignment_or_invalid_turn_count_is_unavailable(self):
        target = self.root / "execution/sessions/core-test"
        for changes, budget in (({"turns": 51}, 50), ({"turns": True}, 50),
                                ({"turns": -1}, 50), ({"turns": 9}, 49),
                                ({"actor": "other", "turns": 9}, 50)):
            with self.subTest(changes=changes, budget=budget):
                save(target / "end.json", {**self.rows[0], **changes, "normal": True})
                save(target / "meta/spec.json", {**self.rows[0], "turns": budget})
                with patch("parabox.tasks.code.task.CodeTask.audit_session") as audit, \
                        patch("parabox.tasks.wiki.grader.session", return_value={"earned_score": 1}):
                    result = grade(self.root, image_verifier=lambda image: None)
                self.assertEqual(result["sessions"][0]["status"], "unavailable")
                audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
