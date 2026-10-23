import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark import default_spec
from parabox.benchmark.__main__ import main
from parabox.benchmark.prepare import check, prepare, source_bindings
from parabox.util import read, save


def payload(block, condition, checkpoint_author=0):
    files = {} if condition == "empty_wiki" else {
        "shared/wiki/NOTES.md": f"fixture-{block}".encode(),
        "shared/wiki/cases.json": b"[]",
    }
    return {"files": files, "provenance": {"block": block, "checkpoint_author": checkpoint_author}}


class BenchmarkPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = self.root / "model.json"
        save(self.model, {"model": "fixture", "api_key_env": "NEVER_READ"})
        self.spec = default_spec({"candidate": str(self.model)}, str(self.model), "sha256:" + "b" * 64)
        self.output = self.root / "prepared"
        self.addCleanup(patch.stopall)
        self.payload = patch("parabox.benchmark.sources.initial_payload", side_effect=payload).start()
        patch("parabox.model.Client.complete", side_effect=AssertionError("No model calls")).start()
        patch("subprocess.run", side_effect=AssertionError("No containers or subprocesses")).start()

    def test_prepare_check_without_models_or_containers(self):
        manifest = prepare(self.output, self.spec)
        self.assertEqual(manifest["state"], "prepared_not_authorized")
        self.assertEqual(check(self.output)["counts"]["total"], 108)
        self.assertFalse(manifest["image_locally_verified"])
        self.assertFalse((self.output / "sessions").exists())

    def test_all_wiki_prompts_are_ordinary_and_twenty_unit(self):
        prepare(self.output, self.spec)
        materials = read(self.output / "materials.json")
        for actor, surface in materials["surfaces"].items():
            if actor.startswith("wiki-"):
                digest = surface["workspace"]["README.md"]
                readme = (self.output / "artifacts" / digest).read_text()
                self.assertIn("Execution budget: 20 units.", readme)
                self.assertNotIn("Execution budget: 60 units.", readme)
                self.assertIn("Implement the", surface["prompts"]["task"])
                self.assertNotIn("Recover evaluator", surface["prompts"]["task"])
                if actor.endswith("-p1"):
                    self.assertIn("Scheduled subsequent package assignments: [].", readme)

    def test_prepare_refuses_overwrite(self):
        prepare(self.output, self.spec)
        with self.assertRaises(FileExistsError):
            prepare(self.output, self.spec)

    def test_extracted_runtime_modules_remain_source_bound(self):
        manifest = prepare(self.output, self.spec)
        source_root = Path(__file__).resolve().parents[1]
        for name in ("runtime.py", "guards.py"):
            source = str((source_root / "parabox/execution/control" / name).resolve())
            with self.subTest(module=name):
                self.assertIn(source, manifest["sources"])
                changed = source_bindings()
                changed[source] = "0" * 64
                with patch("parabox.benchmark.prepare.source_bindings", return_value=changed):
                    with self.assertRaisesRegex(ValueError, "Implementation bindings changed"):
                        check(self.output)

    def test_embedded_credentials_rejected_before_output(self):
        save(self.model, {"model": "fixture", "api_key": "not-a-real-key"})
        with self.assertRaises(ValueError):
            prepare(self.output, self.spec)
        self.assertFalse(self.output.exists())

    def test_changed_config_rejected(self):
        prepare(self.output, self.spec)
        save(self.model, {"model": "changed"})
        with self.assertRaises(ValueError):
            check(self.output)

    def test_changed_artifact_rejected(self):
        manifest = prepare(self.output, self.spec)
        (self.output / "artifacts" / manifest["artifacts"][0]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            check(self.output)

    def test_changed_plan_and_execution_policy_rejected(self):
        prepare(self.output, self.spec)
        original = read(self.output / "plan.json")
        changed = read(self.output / "plan.json")
        changed["sessions"][0]["gate"] = "harness"
        save(self.output / "plan.json", changed)
        with self.assertRaises(ValueError):
            check(self.output)
        save(self.output / "plan.json", original)
        manifest = read(self.output / "manifest.json")
        manifest["execution"]["wiki_variant"] = "base"
        save(self.output / "manifest.json", manifest)
        with self.assertRaises(ValueError):
            check(self.output)

    def test_missing_source_fails_before_preparation(self):
        self.payload.side_effect = RuntimeError("Missing source block")
        with self.assertRaises(RuntimeError):
            prepare(self.output, self.spec)
        self.assertFalse(self.output.exists())

    def test_cli_default_prepare_check_and_no_run_command(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            main(["default-spec", "--candidate", f"candidate={self.model}",
                  "--reference", str(self.model), "--image", self.spec["image"]])
        specfile = self.root / "spec.json"
        save(specfile, json.loads(stream.getvalue()))
        with contextlib.redirect_stdout(io.StringIO()):
            main(["prepare", str(self.output), "--spec", str(specfile)])
            main(["check", str(self.output)])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["run", str(self.output)])


if __name__ == "__main__":
    unittest.main()
