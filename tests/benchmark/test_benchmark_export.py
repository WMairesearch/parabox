from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark import default_spec
from parabox.benchmark.evaluation.analyze import analyze
from parabox.benchmark.evaluation.export import export
from parabox.benchmark.evaluation.grade import grade
from parabox.benchmark.prepare import prepare
from parabox.benchmark.run import run
from parabox.benchmark.ternary import episode, fixture, run as ternary
from parabox.util import read, save
from tests.benchmark.test_benchmark_run import FakeEngine
from tests.ternary.test_ternary_benchmark import ScriptedBox, ScriptedClient

SECRET = "offline-credential-value"


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "model.json"
        save(self.config, {"model": "offline", "api_key_env": "PARABOX_EXPORT_KEY",
                           "base_url": "https://api.example.com/v1", "wire": "responses"})
        self.deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.addCleanup(patch.stopall)
        patch.dict("os.environ", {"PARABOX_EXPORT_KEY": SECRET}).start()
        patch("parabox.model.Client.complete", side_effect=AssertionError("No model calls")).start()

    def ternary_run(self, protocol):
        directory = self.root / protocol
        ternary.prepare(directory, {"models": {"example": str(self.config)},
            "image": "sha256:" + "a" * 64, "seed": fixture.HISTORICAL_SEED, "seats": 1,
            "protocol": protocol, "profile": fixture.HISTORICAL, "transport_profile": fixture.JSON_900})
        with patch.object(episode, "SharedBox", ScriptedBox), \
                patch.object(episode.base, "Client", ScriptedClient), \
                patch.object(episode.base, "shutdown", return_value={"verified": True}), \
                patch.object(ternary, "verify_image"):
            ternary.run(directory, authorize_session_cap=18, deadline=self.deadline, workers=1)
        return directory

    def function_run(self):
        directory = self.root / "functions"
        prepare(directory, default_spec({"example": str(self.config)}, None, "sha256:" + "a" * 64,
                                        function_profile="solvable-exposure"))
        with patch("subprocess.run", side_effect=AssertionError("No container calls")):
            run(directory, authorize_session_cap=32, deadline=self.deadline, core_engine=FakeEngine(),
                wiki_engine=FakeEngine(), image_verifier=lambda image: None)
        for row in read(directory / "plan.json")["sessions"]:
            target = directory / "execution/sessions" / row["actor"]
            save(target / "meta/spec.json", row)
            save(target / "meta/submissions.json", [{"turn": 3, "accepted": True}])
        return directory

    def test_ternary_runs_become_one_offline_bundle(self):
        terminal, repeated = self.ternary_run(fixture.TERMINAL), self.ternary_run(fixture.REPEATED)
        failed = next(terminal.glob("chains/*/generation-01/seat-0/end.json"))
        save(failed, {**read(failed), "normal": False, "error": f"OSError('{terminal}/x')"})
        result = export([terminal, repeated], self.root / "bundle")
        self.assertEqual((result["sessions"], result["planned_sessions"]), (36, 36))
        self.assertTrue(all(item["published_profile"] for item in result["runs"]))
        bundle = self.root / "bundle"
        self.assertEqual(analyze(bundle)["sessions"], 36)
        text = "".join(path.read_text() for path in bundle.iterdir())
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(SECRET, text)
        errors = [json.loads(line)["end"]["error"] for line in (bundle / "sessions.jsonl").read_text().splitlines()]
        self.assertEqual([error for error in errors if error], ["OSError"])
        models = read(bundle / "protocols.json")["runs"][0]["models"]
        self.assertEqual((models[0]["model"], models[0]["wire"], models[0]["endpoint_host"]),
                         ("offline", "responses", "api.example.com"))
        with self.assertRaisesRegex(ValueError, "duplicate session"):
            export([terminal, terminal], self.root / "twice")

    def test_export_refuses_credentials_and_leaves_no_output(self):
        terminal = self.ternary_run(fixture.TERMINAL)
        ended = next(terminal.glob("chains/*/generation-01/seat-0/end.json"))
        save(ended, {**read(ended), "status": SECRET})
        with self.assertRaisesRegex(ValueError, "credential"):
            export([terminal], self.root / "bundle")
        self.assertFalse((self.root / "bundle").exists())

    def test_function_run_requires_grading_and_binds_participants(self):
        directory = self.function_run()
        with self.assertRaisesRegex(ValueError, "grade"):
            export([directory], self.root / "bundle")
        audit = {"violation": True, "turns": [{"turn": 3, "violation": True}]}
        with patch("parabox.tasks.code.task.CodeTask.audit_session", return_value=audit):
            self.assertEqual(grade(directory, image_verifier=lambda image: None)["graded"], 32)
        result = export([directory], self.root / "bundle")
        self.assertEqual(result["protocol_counts"], {"function-solvable-exposure": 32})
        rows = [json.loads(line) for line in (self.root / "bundle/sessions.jsonl").read_text().splitlines()]
        self.assertEqual({row["participant_model"] for row in rows}, {"offline"})
        self.assertTrue(all(row["end"]["violation"] for row in rows))
        record = read(self.root / "bundle/protocols.json")["runs"][0]
        self.assertTrue(record["sources_match_installed"])
        self.assertEqual(record["spec"]["candidates"], {"example": "configs/example.json"})
        self.assertNotIn(str(self.root), (self.root / "bundle/protocols.json").read_text())


if __name__ == "__main__":
    unittest.main()
