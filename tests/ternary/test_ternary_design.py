from datetime import datetime, timedelta, timezone
import difflib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark.evaluation.analyze import analyze
from parabox.benchmark.evaluation.export import export
from parabox.benchmark.ternary import episode, fixture, run as ternary
from parabox.util import digest_json, read, save, sha256
from tests.ternary.test_ternary_benchmark import ScriptedBox, ScriptedClient

IMAGE = "sha256:" + "a" * 64
PUBLISHED = {"image": IMAGE, "seed": fixture.HISTORICAL_SEED, "protocol": fixture.TERMINAL,
             "profile": fixture.HISTORICAL, "transport_profile": fixture.JSON_900}


class TernaryDesignTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "model.json"
        save(self.config, {"model": "offline", "api_key_env": "PARABOX_DESIGN_KEY"})
        self.models = {"gemini-pro": str(self.config)}

    def spec(self, **design):
        return {**PUBLISHED, "models": self.models, "seats": 1, **design}

    def no_reader(self, protocol=fixture.TERMINAL):
        return self.spec(protocol=protocol, generations=1, replicates=4, readers=fixture.NO_READER)

    def test_published_preset_registers_the_frozen_schedule_and_materials(self):
        ternary.prepare(self.root / "published", {**self.spec(), "seats": 4})
        registration = ternary.check(self.root / "published")
        self.assertEqual(registration["session_cap"], 144)
        self.assertEqual(registration["generations"], 6)
        self.assertEqual([row["chain"] for row in registration["chains"]][:2],
                         ["gemini-pro-prefix-01-empty", "gemini-pro-prefix-01-method"])
        self.assertTrue(all(set(row) == {"chain", "model", "prefix", "condition"}
                            for row in registration["chains"]))
        surfaces = registration["materials"]["1"]
        self.assertEqual(sha256(surfaces["files"]["README.md"].encode()),
                         "9271d9d0198897e041218a64b430f9cfa55bc351124f7f46dad7bd82443c7156")
        self.assertEqual(surfaces["tools"], fixture.TERMINAL_TOOLS)
        self.assertEqual(surfaces["messages"][1]["content"], fixture.TERMINAL_ASSIGNMENT)

    def test_no_reader_condition_changes_only_the_reader_statements(self):
        for protocol, changed in ((fixture.TERMINAL, 3), (fixture.REPEATED, 2)):
            ternary.prepare(self.root / protocol, self.no_reader(protocol))
            registration = ternary.check(self.root / protocol)
            self.assertEqual((registration["session_cap"], registration["generations"]), (12, 1))
            self.assertEqual(registration["chains"][0], {
                "chain": "gemini-pro-prefix-01-method-no-reader-r01", "model": "gemini-pro",
                "prefix": 1, "condition": "method", "readers": fixture.NO_READER, "replicate": 1})
            for prefix in fixture.PREFIXES:
                published = episode.participant_files(prefix, registration["target"], protocol)["README.md"]
                variant = registration["materials"][str(prefix)]["files"]["README.md"]
                removed = [line for line in difflib.ndiff(published.decode().splitlines(), variant.splitlines())
                           if line.startswith("- ")]
                self.assertEqual(len(removed), changed)
                self.assertEqual(variant.count("No other agent or later session will read"), 2)
                self.assertNotIn("persist", variant)

    def test_invalid_designs_are_rejected_before_preparation(self):
        for design, message in (({"readers": fixture.NO_READER}, "one seat and one generation"),
                                ({"readers": fixture.NO_READER, "generations": 1, "seats": 4},
                                 "one seat and one generation"),
                                ({"readers": "later"}, "Unknown reader condition"),
                                ({"replicates": 0}, "replicates 1 to 100"),
                                ({"generations": True}, "Generations must be")):
            with self.assertRaisesRegex(ValueError, message):
                ternary.prepare(self.root / "rejected", self.spec(**design))
            self.assertFalse((self.root / "rejected").exists())

    def test_check_rejects_rewritten_materials(self):
        directory = self.root / "run"
        ternary.prepare(directory, self.no_reader())
        registration = read(directory / "registration.json")
        registration["materials"]["1"]["files"]["README.md"] = "Edited after prepare.\n"
        save(directory / "registration.json", registration)
        (directory / "registration.sha256").write_text(digest_json(registration) + "\n")
        with self.assertRaisesRegex(ValueError, "Participant materials changed"):
            ternary.check(directory)

    def test_independent_replicates_run_export_and_analyze_apart_from_published_groups(self):
        directory = self.root / "run"
        ternary.prepare(directory, self.no_reader())
        deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with patch.object(episode, "SharedBox", ScriptedBox), \
                patch.object(episode.base, "Client", ScriptedClient), \
                patch.object(episode.base, "shutdown", return_value={"verified": True}), \
                patch.object(ternary, "verify_image"):
            result = ternary.run(directory, authorize_session_cap=12, deadline=deadline, workers=2)
        self.assertEqual((result["completed"], result["chain_errors"]), (12, {}))
        chains = sorted((directory / "chains").iterdir())
        self.assertEqual(len(chains), 12)
        for chain in chains:
            self.assertEqual([path.name for path in (chain / "submissions").iterdir()],
                             ["generation-01-seat-0.json"])
            prompts = read(chain / "generation-01/seat-0/meta/prompts.json")
            self.assertIn("No other agent or later session will read them.", prompts["files"]["README.md"])
            end = read(chain / "generation-01/seat-0/end.json")
            self.assertEqual(end["rules"], {"call_limit": 20, "test_limit": 2, "submission_limit": 1})
        bundle = self.root / "bundle"
        with patch.dict("os.environ", {"PARABOX_DESIGN_KEY": "offline-credential"}):
            summary = export([directory], bundle)
        [record] = read(bundle / "protocols.json")["runs"]
        self.assertFalse(record["published_profile"])
        self.assertEqual(record["design"], {"generations": 1, "replicates": 4, "readers": fixture.NO_READER})
        rows = [json.loads(line) for line in (bundle / "sessions.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["id"], "ternary-terminal/1-agent/gemini-pro-prefix-01-method-no-reader-r01/1/0")
        self.assertEqual({(row["readers"], row["replicate"]) for row in rows},
                         {(fixture.NO_READER, replicate) for replicate in range(1, 5)})
        groups = analyze(bundle)["groups"]
        self.assertEqual({group.get("variant") for group in groups}, {"readers-none"})
        overall = next(group for group in groups if group["dimension"] == "all")
        self.assertEqual((overall["sessions"], overall["chains"], summary["sessions"]), (12, 12, 12))


if __name__ == "__main__":
    unittest.main()
