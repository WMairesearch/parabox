"""Replay what each write participant was sent and what it was given on disk.

The prompt carries no integrity text and names no other participant: turn 1 is the system text
and the task text and nothing else. The only thing that differs across arms is the single file
planted in shared/, which the frozen protocol pins per arm. The participant reaches it only by
listing and reading its workspace, never through the prompt.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import session_dir
from parabox.studies.write import notes as N
from parabox.tasks.lean.discovery import DiscoveryLeanTask
from parabox.util import read, sha256


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = DiscoveryLeanTask()
    problems = []
    head = [
        {"role": "system", "content": task.system(integrity="none", shared=False)},
        {"role": "user", "content": task.task(shared=False)},
    ]
    if "Proof Integrity" in head[0]["content"] or "STRICTLY FORBIDDEN" in head[0]["content"]:
        problems.append("system text still carries integrity rules")
    if "list_dir" not in head[1]["content"]:
        problems.append("task text does not tell the participant to use list_dir")
    note_sha = protocol["frozen"]["note_sha256"]
    sessions = 0
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        sessions += 1
        meta, actor, arm = target / "meta", row["actor"], row["arm"]
        if read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        if (meta / "board-prior.json").exists():
            problems.append(f"{actor}: a board prior was delivered")
        requests = sorted((meta / "requests").glob("t*.json"))
        if requests and read(requests[0])["messages"] != head:
            problems.append(f"{actor}: turn-1 request is not the system and task text alone")
        for path in requests:
            if read(path)["messages"][:len(head)] != head:
                problems.append(f"{actor} {path.stem}: opening changed")
        delivered = read(meta / "delivered.json")
        if delivered["arm"] != arm:
            problems.append(f"{actor}: delivered file is tagged for the wrong arm")
        want_path, want_content = N.planted(arm)
        if delivered["files"] != {want_path: want_content}:
            problems.append(f"{actor}: delivered file differs from the {arm} file")
        got = sha256(delivered["files"].get(want_path, ""))
        if got != note_sha.get(arm):
            problems.append(f"{actor}: delivered file hash does not match the pinned {arm} file")
    return {"sessions": sessions, "problems": problems, "ok": not problems}
