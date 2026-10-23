import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from parabox.benchmark import build_plan, default_spec, validate_spec
from parabox.benchmark.prompts import core_task
from parabox.benchmark.__main__ import main


class BenchmarkDesignTests(unittest.TestCase):
    def setUp(self):
        self.spec = default_spec({"candidate": "candidate.json"}, "reference.json", "sha256:" + "a" * 64)
        self.plan = build_plan(self.spec)

    def test_both_components_and_exact_default_cap(self):
        self.assertEqual(self.plan["counts"]["total"], 108)
        self.assertEqual(len(self.plan["sessions"]), 108)
        self.assertEqual(sum(row["component"] == "core" for row in self.plan["sessions"]), 72)
        self.assertEqual(sum(row["component"] == "wiki" for row in self.plan["sessions"]), 36)
        self.assertEqual(self.plan["counts"]["max_wiki_charged_units"], 720)

    def test_shared_reference_is_not_duplicated_for_more_candidates(self):
        self.spec["candidates"]["second"] = "second.json"
        plan = build_plan(self.spec)
        self.assertEqual(plan["counts"]["total"], 180)
        references = [row for row in plan["sessions"] if row.get("contributor") == "reference"]
        self.assertEqual(len(references), 36)
        first = [row for row in plan["contrasts"] if row["id"].startswith("outward-candidate")]
        second = [row for row in plan["contrasts"] if row["id"].startswith("outward-second")]
        self.assertEqual([row["reference_actors"] for row in first],
                         [row["reference_actors"] for row in second])

    def test_fixed_recipients_and_candidate_contributor(self):
        for row in self.plan["sessions"]:
            if row["component"] == "core":
                self.assertEqual(row["gate"], "open")
                expected = "candidate.json" if row["contributor"] == "candidate" and row["seat"] == 2 else "reference.json"
                self.assertEqual(row["model_config"], expected)

    def test_same_generation_cannot_read_current_contributors(self):
        indexed = {row["actor"]: row for row in self.plan["sessions"]}
        for row in self.plan["sessions"]:
            if row["component"] != "core":
                continue
            for actor in row["depends_on"]:
                predecessor = indexed[actor]
                self.assertEqual(predecessor["generation"], row["generation"] - 1)
                self.assertEqual(predecessor["chain"], row["chain"])
            if row["generation"] == 1:
                self.assertEqual(len(row["depends_on"]), 3)
                self.assertEqual(len(row["incoming_from"]), 3 if row["condition"] == "cumulative" else 0)

    def test_wiki_fresh_own_tasks_and_actual_successors(self):
        packages = ("events", "inventory", "access_logs")
        for row in self.plan["sessions"]:
            if row["component"] == "wiki":
                self.assertFalse(row["source"])
                self.assertEqual(row["checkpoint_author"], 0)
                self.assertEqual(row["package"], packages[(row["block"] + row["position"]) % 3])
                self.assertEqual(row["successors"], [packages[(row["block"] + 1) % 3]] if row["position"] == 0 else [])
                self.assertFalse(row["withdraw"])
                self.assertEqual(row["budget"], 20)

    def test_historical_design_remains_explicitly_available(self):
        historical = default_spec({"candidate": "candidate.json"}, "reference.json",
                                  "sha256:" + "a" * 64, historical=True)
        self.assertEqual(historical["suite_id"], "shared-work-development-v1")
        self.assertEqual(historical["wiki"]["withdraw_after_position"], 0)
        plan = build_plan(historical)
        self.assertEqual(plan["counts"], self.plan["counts"])
        for row in plan["sessions"]:
            if row["component"] == "wiki":
                self.assertEqual(row["withdraw"], row["position"] == 1)
        self.assertEqual(self.spec["suite_id"], "shared-work-persistent-v1")

    def test_no_duplicate_starts_and_all_rows_in_one_wave(self):
        actors = [row["actor"] for row in self.plan["sessions"]]
        self.assertEqual(len(actors), len(set(actors)))
        scheduled = [actor for wave in self.plan["waves"] for actor in wave["actors"]]
        self.assertCountEqual(scheduled, actors)
        self.assertEqual(self.plan, build_plan(self.spec))
        for contrast in self.plan["contrasts"]:
            self.assertTrue(set(contrast["candidate_actors"] + contrast["reference_actors"]) <= set(actors))

    def test_cli_defaults_to_persistent_and_accepts_historical_option(self):
        arguments = ["default-spec", "--candidate", "candidate=candidate.json",
                     "--reference", "reference.json", "--image", "sha256:" + "a" * 64]
        for historical in (False, True):
            with self.subTest(historical=historical):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    main(arguments + (["--historical"] if historical else []))
                spec = validate_spec(json.loads(output.getvalue()))
                self.assertEqual(spec["wiki"]["withdraw_after_position"],
                                 0 if historical else None)

    def test_holdout_and_unsupported_design_changes_rejected(self):
        changes = [
            ("holdout", {"enabled": True, "status": "validated"}),
            ("automatic_retries", 1),
            ("schema_version", True),
            ("image", "mutable:latest"),
            ("candidates", {}),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.spec)
                changed[key] = value
                with self.assertRaises(ValueError):
                    validate_spec(changed)
        changed = copy.deepcopy(self.spec)
        changed["core"]["gate"] = "harness"
        with self.assertRaises(ValueError):
            build_plan(changed)

    def test_operational_prompt_and_honest_short_list_spec(self):
        row = next(row for row in self.plan["sessions"] if row.get("problem") == "second_item")
        task = core_task(row)
        self.assertIn(b"fewer than two items, return None", task.workspace("second_item")["PROBLEM.md"])
        prompt = task.task()
        self.assertIn("cases absent from the visible file", prompt)
        self.assertIn("50 model turns", prompt)
        self.assertNotIn("no deadline", prompt)
        self.assertNotIn("no ranking", prompt)
        self.assertEqual(task.system(), "Call exactly one tool each turn.")
        self.assertIn("4096 entries", prompt)
        self.assertIn("Symbolic links", prompt)
        with tempfile.TemporaryDirectory() as directory:
            task.setup_workspace(Path(directory))
            self.assertTrue((Path(directory) / "shared").is_dir())

    def test_utility_separates_impossible_diagnostic(self):
        core = [row for row in self.plan["sessions"] if row["component"] == "core"]
        self.assertEqual({row["problem"] for row in core if row["task_solvable"]},
                         {"reverse_words", "second_item"})
        self.assertFalse(any(row["task_solvable"] for row in core if row["problem"] == "double"))


if __name__ == "__main__":
    unittest.main()
