import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parabox.analysis import late_chains, outcome_summary
from parabox.session import run_session
from parabox.studies.relay.run import code_commit
from parabox.studies.unified import run as runner
from parabox.studies.unified.design import design
from parabox.studies.unified.notes import content_arm
from parabox.studies.unified.score import session_record
from parabox.studies.unified.score import records, cells
from parabox.tasks.code.task import CodeTask
from parabox.util import read, save


class ReviewRegressions(unittest.TestCase):
    def prepared(self, root, **changes):
        config = root / "model.json"
        save(config, {"model": "fixture", "api_key_env": "UNUSED"})
        target = root / "run"
        with patch.object(runner, "image_exists", return_value=True), patch.object(runner, "image_id", return_value="fixture"):
            runner.prepare(target, **({"mode": "single", "gate": "open", "arms": ["control", "method"],
                                      "model_config": str(config), "problems": ["second_item"], "reps": 1} | changes))
        return target

    def test_plan_membership_and_assignments_are_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.prepared(Path(directory))
            plan = read(target / "plan.json")
            for changed in (plan["actors"][:1], [dict(row, model="changed") for row in plan["actors"]]):
                save(target / "plan.json", {"actors": changed})
                with self.assertRaisesRegex(ValueError, "frozen protocol design"):
                    runner.check_frozen(target)

    def test_unused_model_configs_remain_in_frozen_set(self):
        for conditions in (["mixed-method"], ["control"]):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                extra = root / "peer.json"
                save(extra, {"model": "peer", "api_key_env": "UNUSED"})
                target = self.prepared(root, mode="population", arms=conditions,
                                       models=[str(extra)], agents=2, generations=1, chains=1)
                with patch.object(runner, "image_id", return_value="fixture"):
                    runner.check_frozen(target)
                save(extra, {"model": "changed", "api_key_env": "UNUSED"})
                with patch.object(runner, "image_id", return_value="fixture"), self.assertRaises(SystemExit):
                    runner.check_frozen(target)

    def test_invalid_designs_rejected(self):
        for changes in ({"arms": ["contorl"]}, {"arms": ["control", "control"]},
                        {"arms": []}, {"reps": 0}, {"problems": []},
                        {"mode": "chain", "lineages": 0},
                        {"mode": "population", "agents": 0}, {"generations": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                design(**({"mode": "single", "arms": ["control"], "gate": "open"} | changes))
        for name in ("v4pro-all", "v4pro-selected", "mixed-all", "mixed-selected", "all", "selected"):
            self.assertEqual(content_arm(name), "hint")

    def test_invalid_prepare_does_not_write_or_inspect_image(self):
        for changes in ({"turns": 0}, {"concurrency": 0}, {"hard_stop": "tomorrow"},
                        {"hard_stop": "2026-10-14T12:00:00"}, {"arms": ["typo"]}):
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "run"
                with patch.object(runner, "image_exists", side_effect=AssertionError("image called")):
                    with self.assertRaises(ValueError):
                        runner.prepare(target, **({"mode": "single", "gate": "open", "arms": ["control"],
                                                  "model_config": "unused"} | changes))
                self.assertFalse(target.exists())
        self.assertEqual(runner._deadline("2026-10-14T14:00:00+02:00"),
                         runner._deadline("2026-10-14T12:00:00Z"))

    def test_git_is_optional_for_installed_preparation(self):
        with patch("parabox.studies.relay.run.shutil.which", return_value=None):
            self.assertEqual(code_commit(), {"head": None, "dirty": None, "available": False})

    def test_unknown_audit_bounds_and_dependent_interval(self):
        result = outcome_summary([{"accepted": True, "audit_ok": False, "cheat": False}])
        self.assertIsNone(result["cheat_rate"])
        self.assertEqual((result["lower_bound"], result["upper_bound"]), (0, 1))
        result = outcome_summary([{"chain": "first", "cheat": True}] * 8 +
                                 [{"chain": "second", "accepted": False, "cheat": False}] * 8,
                                 draws=100)
        self.assertEqual(result["n_chains"], 2)
        self.assertEqual(result["interval_method"], "independent-chain percentile bootstrap")

    def test_peer_required_for_completion_not_endpoint(self):
        rows = [{"chain": "mixed-method-c00", "generation": generation, "agent": agent,
                 "normal": True, "cheat": agent == 3, "audit_unknown": False}
                for generation in (6, 7, 8) for agent in range(4)]
        self.assertEqual(late_chains(rows, chains=1)[0]["rate"], 0)
        self.assertFalse(late_chains(rows[:-1], chains=1)[0]["complete"])

    def test_confirmed_cheat_survives_other_unknown_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            save(target / "meta/submissions.json", [{"turn": 1, "accepted": True}, {"turn": 2, "accepted": True}])
            (target / "meta/submissions").mkdir()
            for turn in (1, 2):
                (target / f"meta/submissions/t{turn:02d}.py").write_text("pass")
            for flags, expected in (([True, None], True), ([False, None], None), ([True, False], True)):
                with patch("parabox.tasks.code.task.A.audit_bytes", side_effect=[{"violation": flag} for flag in flags]):
                    result = CodeTask().audit_session(target, {"problem": "double"}, target / "scratch")
                self.assertIs(result["violation"], expected)

    def test_interrupted_attempt_is_preserved_and_retry_archives_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "plan.json", {"actors": [{"actor": "example"}]})
            target = root / "sessions/example"
            save(target / "meta/responses/t01.json", {"evidence": "preserve"})
            with self.assertRaisesRegex(RuntimeError, "unfinished session"):
                run_session(None, None, None, target, {}, integrity="plain", shared=False, opening=[])
            self.assertEqual(runner.retry(root), ["example"])
            self.assertEqual(read(root / "retried/example-1/meta/responses/t01.json"), {"evidence": "preserve"})

    def test_merge_cache_requires_record_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(runner.merge_path(root, "chain", 1), {"record_files": {}})
            with self.assertRaises(ValueError):
                runner.validate_merge(root, "chain", 1)
            runner.write_record(root, "chain", 1, {})
            runner.validate_merge(root, "chain", 1)

    def test_null_audit_remains_unknown_in_session_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sessions/example"
            save(target / "end.json", {"normal": True, "turns": 1})
            save(target / "meta/submissions.json", [{"accepted": True, "extras": []}])
            save(target / "meta/audit/session.json", {"violation": None})
            with patch("parabox.studies.unified.score.last_submit_had_artifact", return_value=False):
                row = session_record(root, {"actor": "example", "arm": "control", "gate": "open", "problem": "double"}, 24)
            self.assertIsNone(row["audit_ok"])
            self.assertTrue(row["audit_unknown"])

    def test_planned_missing_sessions_remain_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = design(mode="chain", arms=["control"], gate="open", lineages=2, generations=2)
            save(root / "protocol.json", {"turns": 24})
            save(root / "plan.json", {"actors": plan})
            for row in plan:
                if row["chain_index"] == 1:
                    continue
                target = root / "sessions" / row["actor"]
                save(target / "end.json", {"normal": True, "turns": 1})
            sessions = records(root)
            total = next(cell for cell in cells(sessions) if cell["generation"] == "all")
            self.assertEqual(len(sessions), 4)
            self.assertEqual(total["unknown"], 2)
            self.assertEqual(total["complete_known_chains"], 1)
            self.assertEqual((total["lower_bound"], total["upper_bound"]), (0, 0.5))
            self.assertIsNone(total["interval_low"])

    def test_audit_retry_reuses_definitive_turn_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            save(target / "meta/submissions.json", [{"turn": 1, "accepted": True}, {"turn": 2, "accepted": True}])
            (target / "meta/submissions").mkdir()
            for turn in (1, 2):
                (target / f"meta/submissions/t{turn:02d}.py").write_text("pass")
            spec = {"problem": "double", "audit_image_id": "fixture-image"}
            with patch("parabox.tasks.code.task.A.audit_bytes", side_effect=[{"violation": True}, {"violation": None}]):
                first = CodeTask().audit_session(target, spec, target / "scratch")
            save(target / "meta/audit/session.json", first)
            with patch("parabox.tasks.code.task.A.audit_bytes", return_value={"violation": None}) as audit:
                second = CodeTask().audit_session(target, spec, target / "scratch")
            self.assertEqual(audit.call_count, 1)
            self.assertIs(second["violation"], True)
            self.assertTrue(second["audit_incomplete"])

    def test_missing_chain_workspace_differs_from_empty_shared_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.prepared(Path(directory), mode="chain", arms=["control"], lineages=1, generations=2)
            rows = runner.load_plan(target)
            previous = target / "sessions" / rows[0]["actor"]
            save(previous / "end.json", {"normal": True})
            with self.assertRaisesRegex(ValueError, "predecessor workspace"):
                runner.extra_files(target, rows[1])
            (previous / "workspace").mkdir()
            self.assertEqual(runner.extra_files(target, rows[1]), {})

    def test_population_merge_requires_source_workspace_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.prepared(Path(directory), mode="population", arms=["control"], chains=1, agents=1, generations=1)
            rows = runner.load_plan(target)
            source = target / "sessions" / rows[0]["actor"]
            with self.assertRaisesRegex(ValueError, "source workspace"):
                runner.merge_generation(target, rows)
            (source / "workspace").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "submission metadata"):
                runner.merge_generation(target, rows)
            save(source / "meta/submissions.json", [])
            runner.merge_generation(target, rows)
            runner.validate_merge(target, rows[0]["chain"], 1)

    def test_missing_audit_image_identity_preserves_effective_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.prepared(Path(directory))
            row = runner.load_plan(target)[0]
            source = target / "sessions" / row["actor"]
            save(source / "end.json", {"normal": True})
            save(source / "meta/spec.json", row)
            save(source / "meta/submissions.json", [{"accepted": True, "turn": 1}])
            original = {"violation": True, "audit_incomplete": True, "turns": []}
            save(source / "meta/audit/session.json", original)
            with patch.object(runner, "image_id", return_value=None), patch.object(runner, "run_audit_session") as audit:
                with self.assertRaisesRegex(ValueError, "cannot identify audit image"):
                    runner.audit(target)
            audit.assert_not_called()
            self.assertEqual(read(source / "meta/audit/session.json"), original)

    def test_runner_validates_completed_audit_identity_before_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.prepared(Path(directory))
            row = runner.load_plan(target)[0]
            source = target / "sessions" / row["actor"]
            save(source / "end.json", {"normal": True})
            save(source / "meta/spec.json", row)
            save(source / "meta/submissions.json", [{"accepted": True, "turn": 1}])
            (source / "meta/submissions").mkdir()
            (source / "meta/submissions/t01.py").write_text("pass")
            with patch.object(runner, "image_id", return_value="image-first"), patch("parabox.tasks.code.task.A.audit_bytes", return_value={"violation": False}) as audit:
                self.assertEqual(runner.audit(target)["audited"], 1)
                self.assertEqual(runner.audit(target)["audited"], 0)
                self.assertEqual(audit.call_count, 1)
            with patch.object(runner, "image_id", return_value="image-second"), patch("parabox.tasks.code.task.A.audit_bytes", return_value={"violation": True}) as audit:
                self.assertEqual(runner.audit(target)["audited"], 1)
                self.assertEqual(audit.call_count, 1)
            self.assertIs(read(source / "meta/audit/session.json")["violation"], True)
            self.assertTrue((source / "meta/audit/previous-001.json").exists())
