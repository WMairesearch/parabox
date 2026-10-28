"""Portable session evidence, shared by local runs and published bundles."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


TERNARY_DESIGN = ("readers", "replicate")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path):
    return json.loads(path.read_bytes())


def lines(path: Path) -> list:
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def session(directory: Path, protocol: str, identity: dict, *, grading=None) -> dict:
    end_path = directory / "end.json"
    end = read(end_path)
    source = {"end_sha256": digest(end_path.read_bytes())}
    result = {"protocol": protocol, **identity, "end": end, "source": source}
    result["id"] = f"{protocol}/{identity.get('seats', 1)}-agent/{identity['chain']}/{identity['generation']}/{identity['seat']}"
    if end.get('normal') is not True:
        return result
    if protocol == "persistent-wiki":
        for name in ("service", "budget"):
            path = directory / "meta" / f"{name}.jsonl"
            if not path.exists() and name == "service" and read(directory / "meta/service.summary.json").get("sealed") is True:
                result[name] = []
                source["service_summary_sha256"] = digest((directory / "meta/service.summary.json").read_bytes())
            else:
                result[name] = lines(path)
                source[f"{name}_sha256"] = digest(path.read_bytes())
        path = Path(grading) if grading else directory / "grading.json"
        result["grading"] = read(path) if path.exists() else None
        if result["grading"] is not None and "grading" in result["grading"]:
            result["grading"] = result["grading"]["grading"]
        if result["grading"] is not None:
            bound = digest(json.dumps(end, sort_keys=True, ensure_ascii=False).encode())
            if result['grading'].get('end_sha256') != bound:
                raise ValueError("Grading does not bind the session end")
            source["grading_sha256"] = digest(path.read_bytes())
        for name in ("incoming", "outgoing"):
            path = directory / "meta" / f"{name}.json"
            result[name] = read(path)
            source[f"{name}_sha256"] = digest(path.read_bytes())
        for path in sorted((directory / 'meta/actions').glob('*.json')):
            action = read(path)
            if action['before']['solution'].get('sha256') != action['after']['solution'].get('sha256'):
                result['first_change_action'] = {key: action[key] for key in ('turn', 'index', 'recorded_at')}
                source['first_change_action_sha256'] = digest(path.read_bytes())
                break
    return result


def load(directory: Path) -> tuple[dict, list[dict]]:
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() and read(manifest_path).get("schema") == "parabox-evidence-v1":
        manifest = read(manifest_path)
        for name, expected in manifest["files"].items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("Invalid evidence path")
            if not (directory / path).resolve().is_relative_to(directory.resolve()) or any(
                    (directory / Path(*path.parts[:index])).is_symlink() for index in range(1, len(path.parts) + 1)):
                raise ValueError("Evidence path crosses a symlink")
            if digest((directory / path).read_bytes()) != expected:
                raise ValueError(f"Evidence hash mismatch: {name}")
        if "sessions.jsonl" not in manifest["files"]:
            raise ValueError("Session evidence is not bound")
        rows = lines(directory / "sessions.jsonl")
        if len(rows) != manifest["sessions"]:
            raise ValueError("Evidence session count differs")
    elif (directory / "registration.json").exists():
        registration = read(directory / "registration.json")
        if "target" not in registration or "spec" not in registration:
            raise ValueError("Use an evidence bundle for archived or mixed-source runs")
        spec = registration["spec"]
        protocol = "ternary-terminal" if spec.get("protocol") == "terminal" else "ternary-repeated"
        rows = []
        for path in sorted(directory.glob("chains/*/generation-*/seat-*/end.json")):
            end = read(path)
            rows.append(session(path.parent, protocol, {"seats": spec["seats"], **{
                key: end[key] for key in ("chain", "model", "prefix", "condition", "generation", "seat")
            }, **{key: end[key] for key in TERNARY_DESIGN if key in end}}))
        manifest = {"schema": "local-run", "planned_sessions": registration["session_cap"],
                    "registration_sha256": digest((directory / "registration.json").read_bytes())}
    elif (directory / "plan.json").exists():
        plan = read(directory / "plan.json")
        rows = []
        for assignment in plan["sessions"]:
            root = directory / "execution/sessions" / assignment["actor"]
            if not (root / "end.json").exists():
                continue
            if assignment["component"] == "core":
                from parabox.benchmark.functions.evidence import session as function_session
                seats = assignment.get("seats", read(directory / "spec.json")["core"]["recipients"] + 1)
                rows.append(function_session(root, {**assignment,
                    "model": assignment["contributor"], "seats": seats}))
                continue
            rows.append(session(root, "persistent-wiki", {
                "chain": assignment["chain"], "model": assignment["model"],
                "condition": assignment["condition"], "initial_score": assignment["score"],
                "generation": assignment["position"] + 1, "seat": 0, "seats": 1,
                "package": assignment["package"], "block": assignment["block"]}))
        manifest = {"schema": "local-run", "planned_sessions": len(plan["sessions"]),
                    "plan_sha256": digest((directory / "plan.json").read_bytes())}
    else:
        raise ValueError("Expected a prepared ternary run or portable evidence bundle")
    identities = [row["id"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate canonical session identity")
    for row in rows:
        if row["protocol"].startswith("function-"):
            from parabox.benchmark.functions.evidence import validate
            validate(row)
            identity = f"{row['protocol']}/{row['seats']}-agent/{row['chain']}/{row['generation']}/{row['seat']}"
            if row['id'] != identity:
                raise ValueError("Canonical function identity differs")
            continue
        if row["protocol"] not in ("ternary-terminal", "ternary-repeated", "persistent-wiki"):
            raise ValueError("Unknown experiment protocol")
        for name in ("chain", "model", "condition"):
            if row[name] != row['end'][name]:
                raise ValueError("Session identity differs from terminal record")
        end = row['end']
        if row["protocol"] == "persistent-wiki":
            expected = {"generation": end["position"] + 1, "seat": 0, "seats": 1,
                        "initial_score": end["score"], "package": end["package"], "block": end["block"]}
            if row.get("grading") is not None:
                bound = digest(json.dumps(end, sort_keys=True, ensure_ascii=False).encode())
                if row['grading'].get('end_sha256') != bound:
                    raise ValueError("Grading does not bind the session end")
        else:
            expected = {"generation": end["generation"], "seat": end["seat"], "prefix": int(end["prefix"])}
            if any(row.get(key) != end.get(key) for key in TERNARY_DESIGN):
                raise ValueError("Session design differs from terminal record")
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError("Session assignment differs from terminal record")
        if row.get('seats') not in (1, 4) or not 0 <= row['seat'] < row['seats']:
            raise ValueError("Invalid population assignment")
        identity = f"{row['protocol']}/{row['seats']}-agent/{row['chain']}/{row['generation']}/{row['seat']}"
        if row['id'] != identity:
            raise ValueError("Canonical identity differs from assignment")
    if manifest.get("protocol_counts") is not None and dict(Counter(row['protocol'] for row in rows)) != manifest['protocol_counts']:
        raise ValueError("Protocol denominators differ from manifest")
    return manifest, rows
