import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.adapters.execution import import_execution
from parabox.records.schema import validate


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def measurements(record):
    return {item["name"]: item for item in record["measurements"]}



class ExecutionAdapterFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [
            {"actor": "core-first", "component": "core", "role": "contributor",
             "model_config": "config.json", "chain": "core", "generation": 0,
             "incoming_from": [], "turns": 50},
            {"actor": "core-next", "component": "core", "role": "recipient",
             "model_config": "config.json", "chain": "core", "generation": 1,
             "incoming_from": ["core-first"], "turns": 50},
            {"actor": "wiki-first", "component": "wiki", "model": "candidate-alias",
             "model_config": "config.json", "chain": "wiki", "position": 0,
             "incoming_from": []},
            {"actor": "wiki-next", "component": "wiki", "model_config": "config.json",
             "chain": "wiki", "position": 1, "incoming_from": ["wiki-first"]},
        ]
        self.plan = {
            "sessions": self.rows, "counts": {"total": 4},
            "waves": [{"id": "core-next", "actors": ["core-next"]}],
        }
        self.manifest = {
            "plan_sha256": canonical(self.plan),
            "models": {"config.json": {"model": "actual-stored-model", "sha256": "a" * 64}},
        }
        self.save("plan.json", self.plan)
        self.save("manifest.json", self.manifest)
        checksum = canonical(self.manifest)
        self.authorization = {"session_cap": 4, "manifest_sha256": checksum}
        self.save("execution/authorization.json", self.authorization)
        self.execution = {
            "states": {row["actor"]: {"state": "completed"} for row in self.rows[:3]},
            "ledger": [{"key": row["actor"], "state": "completed"} for row in self.rows[:3]],
            "planned": 4, "completed": 3, "manifest_sha256": checksum,
            "authorization_sha256": canonical(self.authorization),
        }
        self.execution["states"]["wiki-next"] = {"state": "unstarted_deadline"}
        self.save("execution/end.json", self.execution)
        for row in self.rows[:3]:
            end = {**row, "normal": True, "started_at": "start", "ended_at": "end"}
            if row["component"] == "core":
                end.update(turns=3, accepted=1, submits=2)
                self.save(f"execution/sessions/{row['actor']}/meta/spec.json", row)
                self.save(f"execution/sessions/{row['actor']}/meta/submissions.json",
                          [{"accepted": True}, {"accepted": False}])
                path = self.root / f"execution/sessions/{row['actor']}/meta/transcript.jsonl"
                path.write_text("\n".join(json.dumps(value) for value in [
                    {"turn": 1, "tool": "run_command", "ignored": 2},
                    {"turn": 2, "tool": None}, {"turn": 3, "tool": "finish", "ignored": 0},
                ]) + "\n")
            else:
                end.update(turn=1, action="submit", budget_used=1)
                self.save("execution/sessions/wiki-first/meta/actions/t01-00.json",
                          {"turn": 1, "index": 0, "tool": "submit", "charge": 1,
                           "result": "submitted", "before": {}, "after": {}})
            self.save(f"execution/sessions/{row['actor']}/end.json", end)
        self.save("execution/waves/core-next.json", {
            "wave": self.plan["waves"][0], "records": [{
                "chain": "core", "actors": ["core-next"],
                "transition": {"incoming": {"shared/note": "b" * 64}, "lineage": []},
                "outgoing": {"shared/note": "b" * 64},
            }],
        })

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def load(self):
        result = import_execution(self.root)
        validate(result)
        return result, {record["actor"]: record for record in result["records"]}

    def host_log(self, rows, *, closed=True, sealed=True):
        directory = "execution/sessions/wiki-first"
        budget_rows = [{"kind": "run_command", "accepted": True, "used": 1, "remaining": 99}]
        prepared = []
        for row in rows:
            row = dict(row)
            if "rejection" not in row:
                used = len(budget_rows) + 1
                budget_rows.append({"kind": "example_request", "accepted": True,
                                    "used": used, "remaining": 100 - used})
                row["budget_used"] = used
            prepared.append(row)
        end = json.loads((self.root / directory / "end.json").read_text())
        end.update(service_closed=closed, budget_used=len(budget_rows),
                   remaining_budget=100 - len(budget_rows))
        self.save(directory + "/end.json", end)
        path = self.root / directory / "meta/service.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in prepared))
        (self.root / directory / "meta/budget.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in budget_rows))
        self.save(directory + "/meta/budget.summary.json", {
            "used": len(budget_rows), "remaining": 100 - len(budget_rows),
        })
        self.save(directory + "/meta/service.summary.json", {"sealed": sealed, "rejections": {}})

    def core_audit(self, flags, *, verdict=False, incomplete=False):
        directory = "execution/sessions/core-first"
        end = json.loads((self.root / directory / "end.json").read_text())
        end.update(accepted=len(flags), submits=len(flags))
        self.save(directory + "/end.json", end)
        self.save(directory + "/meta/submissions.json",
                  [{"turn": index + 1, "accepted": True} for index in range(len(flags))])
        self.save(directory + "/meta/audit/session.json", {
            "violation": verdict, "audit_incomplete": incomplete,
            "turns": [{"turn": index + 1, "violation": flag} for index, flag in enumerate(flags)],
        })

    def budget_proof(self, kinds):
        from parabox.tasks.wiki.runtime.service import Budget, ObjectService

        directory = self.root / "execution/sessions/wiki-first"
        budget = Budget(10, directory / "meta/budget.jsonl")
        service = ObjectService({}, budget, directory / "meta/service.jsonl")
        for kind in kinds:
            budget.charge(kind)
        service.seal()
        end = json.loads((directory / "end.json").read_text())
        end.update(service_closed=True, budget_used=budget.used,
                   remaining_budget=budget.remaining)
        self.save("execution/sessions/wiki-first/end.json", end)
