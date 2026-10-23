"""Read-only completeness and submission-integrity checks for unified runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from parabox.util import read, sha256


def delivery_problems(delivered: dict, expected: dict[str, bytes]) -> list[str]:
    from parabox.studies.transmission.run import shared_digest

    problems = []
    if delivered.get("shared_sha256") != shared_digest(expected):
        problems.append("delivery-byte-digest-mismatch")
    preview = {name: content.decode("utf-8", "replace") for name, content in expected.items()}
    if delivered.get("files") != preview:
        problems.append("delivery-preview-mismatch")
    return problems


def validate_run(directory: str | Path) -> dict:
    directory = Path(directory)
    raw_plan = read(directory / "plan.json")
    plan = raw_plan["actors"] if isinstance(raw_plan, dict) else raw_plan
    actors = [row["actor"] for row in plan]
    problems = []
    missing, abnormal, unknown = [], [], []
    accepted_sessions = 0
    delivery_checked = 0
    has_protocol = (directory / "protocol.json").is_file()
    if len(set(actors)) != len(actors):
        problems.append({"kind": "duplicate-assignment"})
    prompts_path = directory / "prompts.json"
    payload = read(prompts_path).get("payload", {}) if prompts_path.exists() else {}
    for row in plan:
        actor = row["actor"]
        if Path(actor).name != actor or actor in ("", ".", ".."):
            problems.append({"actor": actor, "kind": "invalid-actor-path"})
            missing.append(actor)
            continue
        target = directory / "sessions" / actor
        if not (target / "end.json").is_file():
            missing.append(actor)
            continue
        end = read(target / "end.json")
        if end.get("normal") is not True:
            abnormal.append(actor)
        if has_protocol:
            from parabox.studies.unified.run import extra_files

            delivery_path = target / "meta/delivered.json"
            if not delivery_path.is_file():
                problems.append({"actor": actor, "kind": "missing-delivery-record"})
            else:
                delivery_checked += 1
                for kind in delivery_problems(read(delivery_path), extra_files(directory, row)):
                    problems.append({"actor": actor, "kind": kind})
        for key in ("actor", "arm", "problem", "generation", "agent", "model"):
            if key in row and end.get(key) != row[key]:
                problems.append({"actor": actor, "kind": "assignment-mismatch", "field": key})
        first = target / "meta/requests/t01.json"
        if not first.exists():
            problems.append({"actor": actor, "kind": "missing-first-request"})
        elif payload:
            messages = read(first).get("messages", [])
            expected = [{"role": "system", "content": payload.get("system")},
                        {"role": "user", "content": payload.get("task")}]
            if messages[:2] != expected:
                problems.append({"actor": actor, "kind": "prompt-mismatch"})
        path = target / "meta/submissions.json"
        if not path.exists():
            problems.append({"actor": actor, "kind": "missing-submissions-record"})
            continue
        submissions = read(path)
        accepted = [item for item in submissions if item.get("accepted")]
        if end.get("accepted") != len(accepted):
            problems.append({"actor": actor, "kind": "acceptance-count-mismatch"})
        for item in submissions:
            snapshot = target / "meta/submissions" / f"t{item['turn']:02d}.py"
            if not snapshot.exists() or sha256(snapshot.read_bytes()) != item.get("sha256"):
                problems.append({"actor": actor, "kind": "submission-digest-mismatch", "turn": item["turn"]})
        if not accepted:
            continue
        accepted_sessions += 1
        audit_path = target / "meta/audit/session.json"
        if not audit_path.exists():
            unknown.append(actor)
            continue
        audit = read(audit_path)
        if audit.get("violation") is None:
            unknown.append(actor)
        turns = audit.get("turns", [])
        if audit.get("audit_incomplete") or any(item.get("violation") is None for item in turns):
            problems.append({"actor": actor, "kind": "incomplete-turn-audit"})
        if {item.get("turn") for item in turns} != {item["turn"] for item in accepted}:
            problems.append({"actor": actor, "kind": "accepted-turn-audit-coverage"})
    return {"planned": len(plan), "normal": len(plan) - len(missing) - len(abnormal),
            "accepted_sessions": accepted_sessions, "delivery_checked": delivery_checked,
            "missing": missing, "abnormal": abnormal,
            "audit_unknown": unknown, "problems": problems,
            "complete": not missing and not abnormal,
            "ok": not (missing or abnormal or unknown or problems)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate_run(args.directory)
    output = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    print(output)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
