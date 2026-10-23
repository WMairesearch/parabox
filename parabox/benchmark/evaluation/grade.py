"""Independent task-specific grading of saved execution, without model calls."""

from __future__ import annotations

from pathlib import Path

from parabox.benchmark.prepare import check
from parabox.benchmark.protocol.prompts import core_task
from parabox.benchmark.run import verify_image
from parabox.util import digest_json, now, read, save, sha256


def grade(directory: Path, *, image_verifier=None) -> dict:
    directory = Path(directory).resolve()
    checked = check(directory)
    execution = directory / "execution"
    ended = read(execution / "end.json")
    if ended.get("manifest_sha256") != checked["manifest_sha256"]:
        raise ValueError("Execution differs from prepared manifest")
    plan, spec = read(directory / "plan.json"), read(directory / "spec.json")
    image = spec["image"]
    (image_verifier or verify_image)(image)
    from parabox.tasks.wiki import grader as wiki_grader
    from parabox.tasks.code import audit

    implementation = {
        "benchmark_grade": sha256(Path(__file__).read_bytes()),
        "core_audit": sha256(Path(audit.__file__).read_bytes()),
        "wiki": wiki_grader.implementation_hashes(),
    }
    rows = []
    for row in plan["sessions"]:
        target = execution / "sessions" / row["actor"]
        end_path = target / "end.json"
        result = {"actor": row["actor"], "component": row["component"],
                  "status": "unavailable", "image": image}
        try:
            if not end_path.exists():
                result["reason"] = "not_ended"
            else:
                end_raw = end_path.read_bytes()
                end = read(end_path)
                identity = {key: value for key, value in row.items()
                            if row["component"] != "core" or key != "turns"}
                if any(end.get(key) != value for key, value in identity.items()):
                    raise ValueError("Terminal assignment differs from plan")
                if row["component"] == "core":
                    assigned = read(target / "meta/spec.json")
                    if any(assigned.get(key) != value for key, value in row.items()):
                        raise ValueError("Saved assignment differs from plan")
                    used, limit = end.get("turns"), row.get("turns")
                    if (type(used) is not int or type(limit) is not int
                            or not 0 <= used <= limit):
                        raise ValueError("Actual turns exceed or lack their planned budget")
                if end.get("normal") is not True:
                    result["reason"] = "abnormal_execution"
                elif row["component"] == "wiki":
                    judged = wiki_grader.session(
                        target, image=image, cache=execution / "grading-cache" / "wiki",
                    )
                    result.update(status="graded", result=judged)
                else:
                    task = core_task(row)
                    task.image = image
                    judged = task.audit_session(
                        target, {**row, "audit_image_id": image},
                        execution / "grading-cache" / "core" / row["actor"],
                    )
                    save(target / "meta/audit/session.json", judged)
                    submissions = read(target / "meta/submissions.json")
                    accepted = [item for item in submissions if item.get("accepted")]
                    clean = any(item.get("violation") is False for item in judged["turns"])
                    violation = judged["violation"] if accepted else False
                    record = {
                        "actor": row["actor"], "end_sha256": digest_json(end),
                        "accepted_invalid": violation,
                        "audit_clean_accepted": True if clean else
                            None if accepted and judged.get("audit_incomplete",
                                                           judged["violation"] is None) else False,
                        "accepted_submissions": len(accepted), "task_audit": judged,
                        "image": image, "implementation": implementation,
                        "graded_at": now(),
                    }
                    save(target / "grading.json", record)
                    result.update(status="graded", result=record)
                if end_path.read_bytes() != end_raw:
                    raise ValueError("Terminal record changed during grading")
        except Exception as error:
            result.update(status="unavailable", reason=type(error).__name__)
            result.pop("result", None)
        rows.append(result)
    result = {
        "manifest_sha256": checked["manifest_sha256"], "image": image,
        "implementation": implementation, "graded_at": now(), "sessions": rows,
        "graded": sum(row["status"] == "graded" for row in rows),
        "unavailable": sum(row["status"] != "graded" for row in rows),
    }
    save(execution / "grading.json", result)
    return result
