import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from parabox.tasks.wiki import evaluator, fixture, grader
from parabox.tasks.wiki.evaluation.scoring import submission_score
from parabox.util import read, save, sha256


IMAGE = "sha256:" + "1" * 64


def evaluation(passed):
    return {"cases": [{"index": index, "passed": index < passed} for index in range(100)],
            "infraerror": None, "passed": passed == 100}


class GraderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "cache"
        self.evaluate = self.enterContext(patch.object(evaluator, "evaluate", return_value=evaluation(60)))

    def grade(self, raw=b"candidate marker", image=IMAGE):
        return grader.grade(raw, "events", image=image, cache=self.cache)

    def test_explicit_image_cache_and_scoring_bindings(self):
        first = self.grade()
        self.assertEqual(self.grade(), first)
        self.evaluate.assert_called_once()
        image, raw, cases, scratch = self.evaluate.call_args.args
        self.assertEqual(image, IMAGE)
        self.assertEqual(raw, b"candidate marker")
        self.assertEqual(cases, fixture.cases("events"))
        self.assertEqual(scratch.parent, self.cache)
        self.assertEqual(first["score"], submission_score(evaluation(60)["cases"], True))
        self.assertEqual(set(first["binding"]["implementation"]),
                         {"grader.py", "evaluator.py", "fixture.py", "helpers.py", "scoring.py"})
        self.grade(image="2" * 64)
        self.assertEqual(self.evaluate.call_count, 2)

    def test_image_required(self):
        with self.assertRaises(TypeError):
            grader.grade(b"candidate", "events", cache=self.cache)
        with self.assertRaises(ValueError):
            self.grade(image="")
        with self.assertRaises(ValueError):
            self.grade(image="python:latest")
        self.evaluate.assert_not_called()

    def test_corrupt_cached_score_rejected(self):
        self.grade()
        path = next(self.cache.glob("*.json"))
        record = read(path)
        record["score"]["code_score"] = 1
        save(path, record)
        with self.assertRaises(RuntimeError):
            self.grade()

    def test_unresolved_case_is_not_a_false_score(self):
        results = evaluation(60)
        results["cases"][0]["passed"] = None
        self.evaluate.return_value = results
        with self.assertRaises(ValueError):
            self.grade()
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_session_keeps_code_quality_separate_from_submission(self):
        directory = self.root / "session"
        digest = sha256(b"candidate marker")
        archive = directory / "meta/artifacts" / digest
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"candidate marker")
        end = {"shutdown_verified": True, "source": False, "package": "events",
               "actor": "actor", "model": "mock", "initial_solution": {"sha256": digest},
               "final_solution": {"sha256": digest}, "normal": True,
               "action": None, "budget_used": 20}
        save(directory / "end.json", end)
        result = grader.session(directory, image=IMAGE, cache=self.cache)
        self.assertEqual(result["final_score"]["code_score"], 0.6)
        self.assertEqual(result["earned_score"], 0)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["image"], IMAGE)
        self.assertEqual(result["end_file_sha256"], sha256((directory / "end.json").read_bytes()))
        self.assertIn(digest, result["grading_bindings"])
        end["normal"] = False
        save(directory / "end.json", end)
        result = grader.session(directory, image=IMAGE, cache=self.cache)
        self.assertIsNone(result["earned_score"])
        self.assertIsNone(result["qualified"])

    def test_archived_candidate_path_cannot_escape(self):
        directory = self.root / "session"
        save(directory / "end.json", {"shutdown_verified": True, "source": False,
             "package": "events", "initial_solution": {"sha256": "../../secret"}})
        with self.assertRaises(ValueError):
            grader.session(directory, image=IMAGE, cache=self.cache)
        self.evaluate.assert_not_called()

    def test_image_prefix_normalizes_to_same_cache_binding(self):
        first = self.grade(image="1" * 64)
        self.assertEqual(first, self.grade(image=IMAGE))
        self.evaluate.assert_called_once()

    def test_changing_end_during_grading_does_not_publish_result(self):
        directory = self.root / "session"
        raw = b"candidate marker"
        digest = sha256(raw)
        archive = directory / "meta/artifacts" / digest
        archive.parent.mkdir(parents=True)
        archive.write_bytes(raw)
        end = {"shutdown_verified": True, "source": False, "package": "events",
               "actor": "actor", "model": "mock", "initial_solution": {"sha256": digest},
               "final_solution": {"sha256": digest}, "normal": True,
               "action": "submit", "budget_used": 20}
        save(directory / "end.json", end)

        def changed(*args):
            save(directory / "end.json", {**end, "action": None})
            return evaluation(60)

        self.evaluate.side_effect = changed
        with self.assertRaisesRegex(RuntimeError, "ending changed"):
            grader.session(directory, image=IMAGE, cache=self.cache)
        self.assertFalse((directory / "grading.json").exists())


class IsolatedEvaluatorTests(unittest.TestCase):
    def test_only_candidate_and_case_input_enter_sandbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            expected = {"host_only": "private answer"}
            boxes = []

            def box_factory(*args, **kwargs):
                box = Mock()
                box.name = args[0]
                boxes.append((args, kwargs, box))
                return box

            execution = {"stdout": json.dumps(expected), "stderr": "", "exit_code": 0, "reason": None}
            with patch.object(evaluator, "Box", side_effect=box_factory), \
                    patch.object(evaluator, "_execute", return_value=execution) as execute, \
                    patch.object(evaluator, "_stop_verified") as stop:
                result = evaluator.evaluate("explicit-image", b"unexecuted candidate bytes",
                                            [{"input": [1], "expected": expected},
                                             {"input": [2], "expected": expected}], scratch)
            self.assertTrue(result["passed"])
            self.assertEqual(len(boxes), 2)
            self.assertNotEqual(boxes[0][2], boxes[1][2])
            self.assertEqual([call.args[1] for call in execute.call_args_list], [[1], [2]])
            self.assertEqual(stop.call_count, 2)
            for args, options, box in boxes:
                self.assertEqual(args[2], "explicit-image")
                self.assertEqual(options["mounts"][0][1:], ("/candidate", "ro"))
                self.assertEqual(len(options["mounts"]), 1)
                candidate = Path(options["mounts"][0][0])
                self.assertEqual([path.name for path in candidate.iterdir()], ["solution.py"])
            self.assertTrue(all(b"private answer" not in path.read_bytes()
                                for path in scratch.rglob("*") if path.is_file()))

    def test_strict_json_and_infrastructure_classification(self):
        def score(output, expected, code=0):
            return evaluator._score({"stdout": output, "stderr": "", "exit_code": code,
                                     "reason": None}, expected)
        self.assertFalse(score("true", 1)["passed"])
        self.assertFalse(score('{"a":1,"a":1}', {"a": 1})["passed"])
        self.assertFalse(score("NaN", 0)["passed"])
        self.assertEqual(score("", None, code=1)["reason"], "candidate_exception_or_exit")
        failed = evaluator._score({"stdout": "", "stderr": "Error: OCI container",
                                   "exit_code": 125, "reason": None}, [])
        self.assertIsNone(failed["passed"])
        self.assertEqual(failed["reason"], "container_execution_error")


if __name__ == "__main__":
    unittest.main()
