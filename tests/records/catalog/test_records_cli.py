import contextlib
import importlib
import io
import json
import unittest

from parabox.records.__main__ import main
from tests.records import test_records_execution


class RecordsCLITests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_records_execution.ExecutionAdapterTests(
            "test_complete_saved_output_and_distinct_acceptance")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.root = self.fixture.root
        self.output = self.root / "evidence.json"

    def command(self, *arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            main([str(argument) for argument in arguments])
        return json.loads(stream.getvalue())

    def export(self):
        return self.command("import", self.root, "--output", self.output, "--study", "offline")

    def test_explicit_import_and_verified_resource_summary(self):
        result = self.export()
        self.assertEqual(result["execution"], "saved_evidence_only")
        self.assertEqual(result["records"], 4)
        checked = self.command("check", self.output, "--root", self.root)
        self.assertTrue(checked["source_verified"])
        summary = self.command("summary", self.output, "--root", self.root,
                               "--measurement-prefix", "resources.")
        self.assertEqual(summary["result"]["records"], 4)
        measurements = [item for group in summary["result"]["groups"] for item in group["measurements"]]
        self.assertTrue(measurements)
        self.assertTrue(all(item["name"].startswith("resources.") for item in measurements))
        self.assertTrue(any(item["unit"] == "operations" for item in measurements))
        self.assertTrue(any(item["unit"] == "turns" for item in measurements))

    def test_query_preserves_unknown_outcomes_and_unstarted_roster(self):
        self.export()
        result = self.command("query", self.output, "--root", self.root,
                              "--actor", "wiki-first", "--measurement-prefix", "task.")
        record = result["result"][0]
        self.assertEqual(record["model"], "actual-stored-model")
        self.assertTrue(all(item["status"] == "not_measured" for item in record["measurements"]))
        result = self.command("query", self.output, "--root", self.root, "--started", "false")
        self.assertEqual([row["actor"] for row in result["result"]], ["wiki-next"])
        self.assertEqual(result["result"][0]["measurements"], [])

    def test_trace_exposes_planned_and_recorded_handoffs_without_read_inference(self):
        self.export()
        result = self.command("trace", self.output, "--root", self.root, "--actor", "core-next")
        payload = result["result"]
        self.assertEqual({item["kind"] for item in payload["relations"]},
                         {"planned_handoff", "recorded_handoff"})
        self.assertTrue(payload["sources"])
        conduct = [item for item in payload["record"]["measurements"]
                   if item["name"].startswith("behavior.")]
        self.assertTrue(all(item["value"] is None for item in conduct))

    def test_required_paths_and_no_private_catalog(self):
        for arguments in (["import"], ["summary", "bundle.json"], ["catalog"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(arguments)
        for module in ("catalog", "adapters.legacy", "adapters.archive",
                       "adapters.resources", "adapters.wiki"):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module("parabox.records." + module)

    def test_source_change_requires_explicit_unverified_mode(self):
        self.export()
        path = self.root / "execution/sessions/core-first/end.json"
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.command("summary", self.output, "--root", self.root)
        result = self.command("summary", self.output, "--root", self.root, "--structure-only")
        self.assertFalse(result["source_verified"])

    def test_import_does_not_overwrite_existing_output(self):
        self.export()
        before = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
