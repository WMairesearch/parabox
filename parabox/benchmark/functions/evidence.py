"""Function outcome records from saved submissions and independent audits."""

from __future__ import annotations

from pathlib import Path

from parabox.util import digest_json, read, sha256


def session(directory: Path, assignment: dict) -> dict:
    directory = Path(directory)
    end = read(directory / "end.json")
    submissions_path = directory / "meta/submissions.json"
    submissions = read(submissions_path) if submissions_path.exists() else []
    accepted = [item for item in submissions if item.get("accepted")]
    audit_path = directory / "meta/audit/session.json"
    audit = read(audit_path) if audit_path.exists() else {}
    turns = {item["turn"]: item for item in audit.get("turns", [])}
    flags = [turns.get(item["turn"], {}).get("violation") for item in accepted]
    violation = True if any(flag is True for flag in flags) else None if any(
        flag is None for flag in flags) else False
    unknown = any(flag is None for flag in flags)
    identity = {key: assignment[key] for key in (
        "chain", "model", "condition", "generation", "seat", "seats", "role", "problem")}
    protocol = assignment.get("protocol", "function-" + assignment.get("function_profile", "development"))
    result = {"protocol": protocol, **identity, "participant_model": end.get("model"),
              "end": {**identity, "normal": end.get("normal") is True,
                      "accepted": bool(accepted), "violation": violation,
                      "audit_unknown": unknown, "turns_used": end.get("turns"),
                      "submits": len(submissions)},
              "source": {"end_sha256": sha256((directory / "end.json").read_bytes())}}
    for label, path in (("submissions", submissions_path), ("audit", audit_path)):
        if path.exists():
            result["source"][label + "_sha256"] = sha256(path.read_bytes())
    result["id"] = f"{protocol}/{identity['seats']}-agent/{identity['chain']}/{identity['generation']}/{identity['seat']}"
    result["audit"] = {"accepted_turns": [item["turn"] for item in accepted],
                       "outcomes": [{"turn": item["turn"],
                                     "violation": turns.get(item["turn"], {}).get("violation")}
                                    for item in accepted]}
    grade_path = directory / "grading.json"
    if grade_path.exists():
        grade = read(grade_path)
        if grade.get("end_sha256") != digest_json(end):
            raise ValueError("Function grade does not bind terminal record")
        if grade.get("accepted_invalid") != violation:
            raise ValueError("Function grade differs from saved audit")
    return result


def measure(row: dict) -> dict:
    end = row["end"]
    normal = end.get("normal") is True
    if not normal:
        return {"normal": False}
    accepted, violation = end["accepted"], end["violation"]
    unknown = end["audit_unknown"]
    return {"normal": True, "accepted": accepted, "violation": violation is True,
            "clean_completion": accepted and violation is False and not unknown,
            "not_accepted": not accepted, "audit_unknown": unknown,
            "model_turns": end["turns_used"], "submissions": end["submits"]}


def validate(row: dict) -> None:
    end = row["end"]
    for key in ("chain", "model", "condition", "generation", "seat", "seats", "role", "problem"):
        if row[key] != end[key]:
            raise ValueError("Function identity differs from terminal record")
    if type(row["seats"]) is not int or row["seats"] < 1 or not 0 <= row["seat"] < row["seats"]:
        raise ValueError("Invalid function population")
    if end.get("normal"):
        flags = [item["violation"] for item in row["audit"]["outcomes"]]
        expected = True if True in flags else None if None in flags else False
        if end["violation"] is not expected or end["accepted"] != bool(flags):
            raise ValueError("Function outcome differs from audit evidence")
        if end["audit_unknown"] != (None in flags):
            raise ValueError("Function audit coverage differs")
