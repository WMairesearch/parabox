"""Integrity check: protocol digests, prompt words, session status."""
from __future__ import annotations

from pathlib import Path

from parabox.studies.evidence import delivery_problems
from parabox.studies.relay.run import session_dir
from parabox.studies.transmission.task import forbidden_in_prompts
from parabox.studies.unified.run import check_frozen, extra_files, load_plan, merge_path, validate_merge
from parabox.studies.unified.task import make_task
from parabox.util import read


def check(directory: Path) -> dict:
    directory = Path(directory)
    protocol = read(directory / "protocol.json")
    problems = []
    try:
        check_frozen(directory)
    except (SystemExit, ValueError) as exc:
        problems.append(str(exc))
    task = make_task(protocol["gate"], protocol["turns"])
    shown = task.system(integrity="plain", shared=False) + "\n" + task.task(shared=False)
    if f"You have {protocol['turns']} turns" not in task.task(shared=False):
        problems.append("task text does not state the protocol turn count")
    for word in forbidden_in_prompts():
        if word in shown:
            problems.append(f"participant text contains {word}")
    if "list_dir" not in task.task(shared=False):
        problems.append("task text does not tell the participant to use list_dir")
    if "shared/" not in task.task(shared=False):
        problems.append("task text does not name the writable shared folder")
    rows = load_plan(directory) if (directory / "plan.json").exists() else protocol.get("design") or []
    missing_status = []
    for row in rows:
        target = session_dir(directory, row["actor"])
        if protocol["mode"] == "population":
            manifest = merge_path(directory, row["chain"], row["generation"])
            complete = (directory / "status.json").exists() and read(directory / "status.json").get("phase") == "complete"
            if complete and not manifest.exists():
                problems.append(f"{row['chain']}: missing merge checkpoint for generation {row['generation']}")
            elif manifest.exists():
                try:
                    validate_merge(directory, row["chain"], row["generation"])
                except ValueError as exc:
                    problems.append(str(exc))
        if (target / "end.json").exists() and not (target / "meta/delivered.json").exists():
            problems.append(f"{row['actor']}: missing delivery evidence")
        if (directory / "status.json").exists() and read(directory / "status.json").get("phase") == "complete":
            if not (target / "end.json").exists():
                missing_status.append(row["actor"])
        if (target / "end.json").exists() and (target / "meta" / "delivered.json").exists():
            delivered = read(target / "meta" / "delivered.json")
            try:
                want = extra_files(directory, row)
            except (ValueError, RuntimeError) as exc:
                problems.append(str(exc))
                continue
            for kind in delivery_problems(delivered, want):
                problems.append(f"{row['actor']}: {kind}")
    if missing_status:
        problems.append("sessions missing end.json: " + ", ".join(missing_status))
    if (directory / "status.json").exists():
        status = read(directory / "status.json")
        for key in ("done", "total", "running", "failed", "phase", "updated_at"):
            if key not in status:
                problems.append(f"status.json missing {key}")
    return {"sessions": len(rows), "problems": problems, "ok": not problems}
