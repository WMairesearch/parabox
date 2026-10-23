from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark.prompts import core_task
from parabox.benchmark.ternary import episode as ternary_episode
from parabox.studies.evidence import delivery_problems
from parabox.execution import CoreEngine, Invocation, StartLedger, run_population
from parabox.sandbox import Box, Limits
from parabox.tasks.code.problems import PROBLEMS
from parabox.util import read, sha256
from tests.helpers import call
from tests.test_ternary_benchmark import ScriptedClient


class ScriptedCoreClient:
    def __init__(self, actor, generation):
        self.actor = actor
        self.commands = [
            ("write_file", {"path": "solution.py", "content": PROBLEMS["second_item"]["reference"]}),
            ("write_file", {"path": f"shared/{actor}.txt", "content": actor}),
            ("submit", {}),
            ("finish", {"report": "Fixture complete."}),
        ]
        if generation:
            self.commands.insert(0, ("read_file", {"path": "shared/g0-s0.txt"}))
        self.inputs = []

    def complete(self, messages, tools=None):
        self.inputs.append(list(messages))
        name, arguments = self.commands[len(self.inputs) - 1]
        return {"role": "assistant", "content": "", "tool_calls": [call(name, arguments)]}, {}


class ShortPrefixClient:
    def __init__(self, config):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            command = "printf '[0]\\n' > submission.json"
            name, arguments = "run_command", {"command": command}
        else:
            name, arguments = "submit", {}
        return {"role": "assistant", "content": "", "tool_calls": [call(name, arguments)]}, {}


@unittest.skipUnless(os.environ.get("PARABOX_EPISODE_TEST_IMAGE"), "Set a local sandbox image")
class BenchmarkContainerTests(unittest.TestCase):
    def test_ternary_short_prefix_receipt(self):
        image = os.environ["PARABOX_EPISODE_TEST_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="parabox-prefix-container-") as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            with patch.object(ternary_episode.base, "Client", ShortPrefixClient):
                result = ternary_episode.run_generation(root / "generation", {
                    "prefix": 1, "generation": 1, "actor": "example", "chain": "example"},
                    {}, [0] * 100, image, wiki, 17,
                    (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), agents=1)
            self.assertTrue(result["normal"])
            end = read(root / "generation/seat-0/end.json")
            self.assertEqual(end["submission_scores"], [0, 0, 0])
            receipts = sorted((root / "submissions").glob("*.json"))
            self.assertEqual(len(receipts), 3)
            self.assertEqual(read(receipts[-1])["feedback"],
                             {"score": 0, "next_position": 2, "next_value": 0})

    def test_ternary_scored_receipts_in_real_container(self):
        image = os.environ["PARABOX_EPISODE_TEST_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="parabox-ternary-container-") as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            with patch.object(ternary_episode.base, "Client", ScriptedClient):
                result = ternary_episode.run_generation(root / "generation", {
                    "prefix": 1, "generation": 1, "actor": "example", "chain": "example"},
                    {}, [0] * 100, image, wiki, 17,
                    (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), agents=1)
            self.assertTrue(result["normal"])
            end = read(root / "generation/seat-0/end.json")
            self.assertEqual(end["submission_scores"], [1, 1, 1])
            self.assertEqual(len(list((root / "submissions").glob("*.json"))), 3)

    def test_core_generations_real_verifier_audit_and_shared_export(self):
        image = os.environ["PARABOX_EPISODE_TEST_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="parabox-core-container-") as temporary:
            root = Path(temporary)
            rows = [{
                "actor": f"g{generation}-s{seat}", "component": "core", "problem": "second_item",
                "gate": "open", "condition": "cumulative", "generation": generation,
                "turns": 50, "successor_actors": ["g1-s0", "g1-s1"] if generation == 0 else [],
            } for generation in range(2) for seat in range(2)]
            deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            frozen = {str(Path(__file__).resolve()): sha256(Path(__file__).read_bytes())}
            ledger = StartLedger(root / "starts.sqlite3", cap=4, deadline=deadline,
                                 frozen=frozen, planned={row["actor"]: row for row in rows})
            clients = {}

            def factory(invocation):
                task = core_task(invocation.spec)
                task.image = image
                client = ScriptedCoreClient(invocation.key, invocation.spec["generation"])
                clients[invocation.key] = client
                return {
                    "task": task, "client": client,
                    "box": Box("core-check-" + sha256(str(invocation.directory))[:16],
                               invocation.directory / "workspace", image, Limits(cpus="1", memory="1g")),
                    "integrity": "plain", "shared": False, "opening": [],
                }

            generations = [[Invocation(row["actor"], root / row["actor"], row)
                            for row in rows if row["generation"] == generation] for generation in range(2)]
            result = run_population(generations, engine=CoreEngine(factory), ledger=ledger,
                                    initial={}, policy="population_all", workers=2)
            self.assertEqual(len(result["outcomes"]), 4)
            self.assertTrue(all(outcome.end["normal"] for outcome in result["outcomes"]))
            self.assertTrue(all(outcome.accepted for outcome in result["outcomes"]))
            self.assertEqual(set(result["files"]), {f"shared/{row['actor']}.txt" for row in rows})
            initial_files = {f"shared/{row['actor']}.txt": row["actor"].encode() for row in rows[:2]}
            for row in rows:
                delivery = read(root / row["actor"] / "meta/delivered.json")
                self.assertEqual(delivery_problems(
                    delivery, initial_files if row["generation"] else {}), [])
            for row in rows[2:]:
                self.assertTrue(any(message["role"] == "tool" and "g0-s0" in message["content"]
                                    for message in clients[row["actor"]].inputs[-1]))
            task = core_task(rows[0])
            task.image = image
            judged = task.audit_session(root / "g0-s0", {**rows[0], "audit_image_id": image},
                                        root / "audit")
            self.assertFalse(judged["violation"])
            self.assertEqual(read(root / "g0-s0/meta/submissions.json")[0]["accepted"], True)


if __name__ == "__main__":
    unittest.main()
