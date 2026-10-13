"""Replay what each transmission participant was sent and what landed on disk."""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import session_dir
from parabox.studies.transmission import design as D
from parabox.studies.transmission import notes as N
from parabox.studies.transmission.run import extra_files, shared_digest, task_for
from parabox.studies.transmission.task import TASK, forbidden_in_prompts
from parabox.util import read, sha256


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = task_for(protocol)
    problems = []
    head = [
        {"role": "system", "content": task.system(integrity="plain", shared=False)},
        {"role": "user", "content": task.task(shared=False)},
    ]
    if head[1]["content"] != TASK:
        problems.append("task text is not the transmission task")
    if "list_dir" not in head[1]["content"]:
        problems.append("task text does not tell the participant to use list_dir")
    if "shared/" not in head[1]["content"]:
        problems.append("task text does not name the writable shared folder")
    if "later participants" not in head[1]["content"].lower():
        problems.append("task text does not address later participants")
    if protocol.get("chains") == D.CHAINS and protocol.get("generations") == D.GENERATIONS:
        if protocol.get("arms") == list(D.ARMS) and not D.default_schedule_is_frozen():
            problems.append("default four-generation schedule is no longer the frozen T10 order")
    shown = head[0]["content"] + "\n" + head[1]["content"]
    for word in forbidden_in_prompts():
        if word in shown:
            problems.append(f"participant text contains {word}")
    note_sha = protocol["frozen"]["note_sha256"]
    sessions = 0
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        sessions += 1
        meta, actor = target / "meta", row["actor"]
        if (meta / "spec.json").exists():
            spec = read(meta / "spec.json")
            if spec.get("verifier") != protocol.get("verifier"):
                problems.append(f"{actor}: spec verifier does not match protocol")
        if read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        requests = sorted((meta / "requests").glob("t*.json"))
        if requests and read(requests[0])["messages"] != head:
            problems.append(f"{actor}: turn-1 request is not the system and task text alone")
        delivered = read(meta / "delivered.json")
        if delivered["arm"] != row["arm"]:
            problems.append(f"{actor}: delivered files are tagged for the wrong arm")
        want = extra_files(directory, row)
        got = {name: text.encode() for name, text in delivered["files"].items()}
        if got != want:
            problems.append(f"{actor}: delivered files differ from the carry-forward rule")
        if row["generation"] == 1:
            path, content = N.planted(row["arm"])
            if delivered["files"] != {path: content}:
                problems.append(f"{actor}: generation-1 seed is not the planted {row['arm']} file")
            if sha256(delivered["files"].get(path, "")) != note_sha.get(row["arm"]):
                problems.append(f"{actor}: generation-1 seed hash does not match the pinned {row['arm']} file")
        step = D.barrier_action(row["arm"], row["generation"])
        if delivered.get("shared_sha256") and delivered["shared_sha256"] != shared_digest(got):
            problems.append(f"{actor}: recorded shared_sha256 does not match delivered files")
        if step and step["action"] == "wipe":
            if delivered["files"]:
                problems.append(f"{actor}: wipe barrier left files in delivered shared/")
            if delivered.get("shared_sha256") and delivered["shared_sha256"] != shared_digest({}):
                problems.append(f"{actor}: wipe barrier shared_sha256 is not the empty-folder hash")
        if step and step["action"] == "inject":
            planted_text = delivered["files"].get(step["path"])
            if planted_text != N.CONDEMN:
                problems.append(f"{actor}: inject barrier did not deliver the planted condemn note")
            if planted_text is not None and sha256(planted_text) != N.CONDEMN_SHA256:
                problems.append(f"{actor}: inject barrier condemn hash does not match the frozen note")
    return {"sessions": sessions, "problems": problems, "ok": not problems}
