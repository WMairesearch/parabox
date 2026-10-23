from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from parabox.benchmark import sources
from parabox.execution import Outcome, FrozenWikiEngine
from parabox.tasks.wiki import budget, episode
from parabox.tasks.wiki.prompts import assignment
from parabox.util import read, save, sha256
from parabox.studies.shared_wiki import default_spec, prepare, check, run
from parabox.studies.shared_wiki.design import build_plan, validate_spec
from parabox.studies.shared_wiki.prepare import source_bindings
from parabox.studies.shared_wiki.run import transport_payload, verify_image
from parabox.studies.shared_wiki.__main__ import main


class FakeEngine:
    policies = {"replace"}

    def __init__(self, fail=None, corrupt=None):
        self.calls = []
        self.fail, self.corrupt = fail, corrupt
        self.lock = threading.Lock()

    def __call__(self, invocation, incoming):
        row = invocation.spec
        with self.lock:
            self.calls.append((dict(row), dict(incoming), invocation.options))
        if row["actor"] == self.fail:
            raise RuntimeError("Offline synthetic failure")
        files = dict(incoming)
        if row["position"] == 0:
            files.pop("shared/wiki/cases.json", None)
            files["shared/wiki/binary.bin"] = b"\xff\x00"
        else:
            files.pop(sources.NOTE, None)
        hashes = {}
        for name, raw in files.items():
            digest = sha256(raw)
            artifact = invocation.directory / "meta/artifacts" / digest
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(raw if row["actor"] != self.corrupt else b"corrupt")
            hashes[name.removeprefix("shared/wiki/")] = digest
        end = {**row, "normal": True, "shutdown_verified": True, "outgoing": {"files": hashes}}
        save(invocation.directory / "end.json", end)
        return Outcome(end, files)


class SharedWikiStudyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "model.json"
        save(self.config, {"model": "offline", "api_key_env": "NEVER_READ"})
        self.spec = default_spec({"candidate": str(self.config)}, "sha256:" + "a" * 64)
        self.directory = self.root / "study"
        self.deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        for target in ("parabox.model.Client.complete", "subprocess.run"):
            patcher = patch(target, side_effect=AssertionError("Offline tests must not call external services"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def small(self, transport="persistent"):
        spec = {**self.spec, "positions": 3, "scores": [60], "blocks": [0], "transport": transport}
        prepare(self.directory, spec)
        return spec

    def launch(self, engine, **kwargs):
        return run(self.directory, authorize_session_cap=9, deadline=self.deadline,
                   wiki_engine=engine, image_verifier=lambda image: None, **kwargs)

    def test_full_six_model_matrix_and_original_wave_order(self):
        models = {name: str(self.config) for name in
                  ("deepseek-flash", "gemini-flash", "kimi", "qwen-max", "deepseek-pro", "gemini-pro")}
        spec = default_spec(models, self.spec["image"])
        plan = build_plan(spec)
        self.assertEqual(plan["counts"], {"total": 972, "chains": 162, "models": 6})
        self.assertEqual(len({row["actor"] for row in plan["sessions"]}), 972)
        for model in models:
            rows = [row for row in plan["sessions"] if row["model"] == model]
            self.assertEqual(len(rows), 162)
            for position in range(6):
                wave = sorted((row for row in rows if row["position"] == position),
                              key=lambda row: (row["score"], row["condition"], row["block"]))
                random.Random(20261019 + position).shuffle(wave)
                self.assertEqual(plan["wave_orders"][model][str(position)], [row["actor"] for row in wave])

    def test_prepare_check_exact_operational_materials_and_founder_proof(self):
        record = prepare(self.directory, self.spec)
        self.assertEqual(record["state"], "prepared_not_authorized")
        self.assertEqual(check(self.directory)["counts"]["total"], 162)
        self.assertFalse((self.directory / "execution").exists())
        materials = read(self.directory / "materials.json")
        for row in build_plan(self.spec)["sessions"]:
            surface = materials["surfaces"][row["actor"]]
            self.assertEqual(surface["prompts"], {"system": episode.SYSTEM,
                             "user": assignment(row["package"]), "tools": episode.TOOLS})
            files = budget.workspace_files(row["package"], row["score"], row["successors"])
            self.assertEqual(surface["workspace"], {name: sha256(raw) for name, raw in files.items()})
        for block in range(3):
            for condition in self.spec["conditions"]:
                seed = sources.initial_payload(block, condition)
                stored = materials["founders"][f"{block}:{condition}"]
                self.assertEqual(stored["provenance"], seed["provenance"])
                self.assertEqual(stored["source_note_hash"], seed["source_note_hash"])
                self.assertEqual(stored["files"], {name: sha256(raw) for name, raw in seed["files"].items()})

    def test_spec_rejects_unsafe_names_images_and_unknown_fields(self):
        for spec in ({**self.spec, "models": {"../escape": str(self.config)}},
                     {**self.spec, "image": "mutable:latest"}, {**self.spec, "positions": True},
                     {**self.spec, "transport": "merge"}, {**self.spec, "resume": True}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                validate_spec(spec)

    def test_model_and_source_and_artifact_tamper_rejected(self):
        self.small()
        original = self.config.read_bytes()
        save(self.config, {"model": "different"})
        with self.assertRaises(ValueError):
            check(self.directory)
        self.config.write_bytes(original)
        module = importlib.import_module("parabox.studies.shared_wiki.prepare")
        with patch.object(module, "source_bindings", return_value={}):
            with self.assertRaises(ValueError):
                check(self.directory)
        digest = read(self.directory / "manifest.json")["artifacts"][0]
        (self.directory / "artifacts" / digest).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            check(self.directory)

    def test_manifest_tamper_and_embedded_credentials_rejected(self):
        self.small()
        manifest = read(self.directory / "manifest.json")
        manifest["session_cap"] = 999
        save(self.directory / "manifest.json", manifest)
        with self.assertRaises(ValueError):
            check(self.directory)
        save(self.config, {"model": "offline", "api_key": "embedded"})
        with self.assertRaisesRegex(ValueError, "credentials|secrets"):
            prepare(self.root / "bad", self.spec)

    def test_transport_is_actual_state_not_seed_merge(self):
        note = b"founder"
        digest = sha256(note)
        files = {sources.NOTE: note, "shared/wiki/new.bin": b"\xff"}
        persistent, proof = transport_payload(files, digest, transport="persistent", position=1)
        self.assertEqual(persistent, files)
        self.assertIsNone(proof["removed_note_original_hash"])
        historical, proof = transport_payload(files, digest, transport="historical-withdrawal", position=1)
        self.assertNotIn(sources.NOTE, historical)
        self.assertEqual(proof["removed_note_original_hash"], digest)
        for policy in ("persistent", "historical-withdrawal"):
            deleted, _ = transport_payload({}, digest, transport=policy, position=1)
            self.assertEqual(deleted, {})
            changed, _ = transport_payload({sources.NOTE: b"agent edit"}, digest, transport=policy, position=1)
            self.assertEqual(changed[sources.NOTE], b"agent edit")
        restored, _ = transport_payload(files, digest, transport="historical-withdrawal", position=2)
        self.assertEqual(restored, files)
        self.assertEqual(files[sources.NOTE], note)

    def test_mock_run_preserves_then_deletes_and_never_resumes(self):
        self.small()
        engine = FakeEngine()
        result = self.launch(engine)
        self.assertEqual(result["completed"], 9)
        self.assertEqual(len(result["ledger"]), 9)
        for row, incoming, options in engine.calls:
            self.assertEqual(set(options), {"config", "image", "files", "deadline"})
            if row["position"] == 1:
                self.assertNotIn("shared/wiki/cases.json", incoming)
                self.assertEqual(incoming["shared/wiki/binary.bin"], b"\xff\x00")
                self.assertEqual(sources.NOTE in incoming, row["condition"] == "full_wiki")
            elif row["position"] == 2:
                self.assertNotIn(sources.NOTE, incoming)
        with self.assertRaisesRegex(ValueError, "no resume"):
            self.launch(engine)

    def test_historical_withdrawal_only_at_first_successor(self):
        self.small("historical-withdrawal")
        engine = FakeEngine()
        self.launch(engine)
        self.assertTrue(all(sources.NOTE not in incoming for row, incoming, _ in engine.calls if row["position"] == 1))

    def test_failed_or_corrupt_export_blocks_only_its_descendants(self):
        self.small()
        actor = "recipient-candidate-60-full_wiki-00-00"
        engine = FakeEngine(corrupt=actor)
        result = self.launch(engine)
        self.assertEqual(result["states"][actor]["state"], "technical_failure")
        for position in (1, 2):
            self.assertEqual(result["states"][actor[:-2] + f"{position:02d}"]["state"], "unavailable_predecessor")
        self.assertEqual(len(result["ledger"]), 7)
        self.assertEqual(result["completed"], 6)

    def test_runtime_failure_claimed_before_call_without_retry(self):
        self.small()
        engine = FakeEngine(fail="recipient-candidate-60-full_wiki-00-00")
        result = self.launch(engine)
        record = next(row for row in result["ledger"] if row["key"] == engine.fail)
        self.assertEqual(record["state"], "failed")
        self.assertEqual(len(result["ledger"]), 7)
        self.assertEqual(sum(row["actor"] == engine.fail for row, _, _ in engine.calls), 1)

    def test_authorization_deadline_and_image_guard(self):
        self.small()
        for cap, deadline in ((8, self.deadline), (True, self.deadline),
                              (9, "2099-01-01T00:00:00"), (9, "2000-01-01T00:00:00+00:00")):
            with self.assertRaises(ValueError):
                run(self.directory, authorize_session_cap=cap, deadline=deadline)
        verifier = Mock(side_effect=ValueError("image mismatch"))
        with self.assertRaisesRegex(ValueError, "image mismatch"):
            run(self.directory, authorize_session_cap=9, deadline=self.deadline, image_verifier=verifier)
        self.assertFalse((self.directory / "execution").exists())
        with patch("parabox.studies.shared_wiki.run.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, "sha256:" + "b" * 64, "")):
            with self.assertRaises(ValueError):
                verify_image(self.spec["image"])

    def test_frozen_adapter_with_mock_runtime_and_bound_ledger(self):
        self.small()
        fake = FakeEngine()

        def runtime(directory, spec, *, incoming, **options):
            import sqlite3
            with sqlite3.connect(self.directory / "execution/starts.sqlite3") as connection:
                state = connection.execute("SELECT state FROM starts WHERE key=?", (spec["actor"],)).fetchone()
            self.assertEqual(state, ("started",))
            from parabox.execution import Invocation
            return fake(Invocation(spec["actor"], directory, spec, options), incoming).end

        adapter = FrozenWikiEngine(variant="budget20", frozen=source_bindings(), runner=runtime)
        result = self.launch(adapter)
        self.assertEqual(result["completed"], 9)

    def test_cli_offline_and_duplicate_models(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(["default-spec", "--model", f"candidate={self.config}", "--image", self.spec["image"]])
        self.assertEqual(json.loads(output.getvalue())["transport"], "persistent")
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            main(["default-spec", "--model", f"candidate={self.config}", "--model", f"candidate={self.config}",
                  "--image", self.spec["image"]])

    def test_grade_uses_saved_sessions_and_registered_image(self):
        from parabox.studies.shared_wiki.grade import grade
        self.small()
        self.launch(FakeEngine(fail="recipient-candidate-60-full_wiki-00-00"))
        with patch("parabox.studies.shared_wiki.grade.grader.session", return_value={"earned_score": 60}) as grader:
            result = grade(self.directory, image_verifier=lambda image: None)
        self.assertEqual(result["graded"], 6)
        self.assertEqual(grader.call_count, 6)
        for call in grader.call_args_list:
            self.assertEqual(call.kwargs["image"], self.spec["image"])
            self.assertEqual(call.kwargs["cache"], self.directory / "execution/grading-cache")


@unittest.skipUnless(os.environ.get("PARABOX_SHARED_WIKI_TEST_IMAGE"), "Set an immutable local sandbox image")
class SharedWikiContainerTests(unittest.TestCase):
    def test_three_recipients_budget_and_actual_exports(self):
        image = os.environ["PARABOX_SHARED_WIKI_TEST_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="parabox-shared-wiki-smoke-") as temporary:
            root = Path(temporary)
            config = root / "offline.json"
            save(config, {"model": "scripted", "api_key_env": "MUST_NOT_BE_READ"})
            spec = default_spec({"scripted": str(config)}, image)
            spec.update(positions=3, scores=[60], conditions=["full_wiki"], blocks=[0],
                        workers_per_model=1, workers_total=1)
            directory = root / "study"
            prepare(directory, spec)
            rows = read(directory / "plan.json")["sessions"]
            clients = []

            class ScriptedClient:
                def __init__(self, row):
                    position = row["position"]
                    command = ("test -f shared/wiki/NOTES.md" if position < 2 else
                               "test ! -e shared/wiki/NOTES.md")
                    if position == 0:
                        command += " && python3 -c 'from pathlib import Path; Path(\"shared/wiki/binary.bin\").write_bytes(bytes([255,0]))'"
                    else:
                        command += " && python3 -c 'from pathlib import Path; assert Path(\"shared/wiki/binary.bin\").read_bytes()==bytes([255,0])'"
                    if position == 1:
                        command += " && rm shared/wiki/NOTES.md"
                    command += f" && python3 examples.py public/{row['package']}/0"
                    self.calls = iter([("run_command", {"command": command})] +
                                      [("run_command", {"command": "true"})] * 17 + [("submit", {})])
                    self.turn = 0

                def complete(self, messages, tools):
                    self.turn += 1
                    name, arguments = next(self.calls)
                    message = {"content": "", "tool_calls": [{"id": f"call-{self.turn}", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)}}]}
                    return message, message

            def factory(config):
                client = ScriptedClient(rows[len(clients)])
                clients.append(client)
                return client

            deadline = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
            with patch("parabox.tasks.wiki.budget.Client", side_effect=factory), \
                    patch("parabox.model.Client.complete", side_effect=AssertionError("Provider calls forbidden")) as provider:
                result = run(directory, authorize_session_cap=3, deadline=deadline)
                provider.assert_not_called()
            self.assertEqual(result["completed"], 3, result["states"])
            self.assertEqual(len(result["ledger"]), 3)
            for row in rows:
                session = directory / "execution/sessions" / row["actor"]
                end, files = sources.export_wiki(session)
                self.assertEqual(end["budget_used"], 20)
                self.assertEqual(end["remaining_budget"], 0)
                self.assertEqual(end["action"], "submit")
                self.assertEqual(files["shared/wiki/binary.bin"], b"\xff\x00")
                self.assertEqual(sources.NOTE in files, row["position"] == 0)
                first = read(session / "meta/actions/t01-00.json")
                self.assertTrue(first["result"].startswith("exit_code=0"), first["result"])
                self.assertIn('"case"', first["result"])


if __name__ == "__main__":
    unittest.main()
