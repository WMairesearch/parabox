"""Replay what each zero-door participant was sent and what landed on disk."""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import session_dir
from parabox.studies.transmission.run import shared_digest
from parabox.studies.transmission.task import TASK
from parabox.studies.transmission_door import design as D
from parabox.studies.transmission_door import notes as N
from parabox.studies.transmission_door.run import extra_files
from parabox.studies.transmission_door.task import DoorChainTask, forbidden_words
from parabox.studies.code.mechspan import verifier_config
from parabox.util import read, sha256


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    door = protocol["door"]
    task = DoorChainTask(door)
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
    shown = head[0]["content"] + "\n" + head[1]["content"]
    for word in forbidden_words():
        if word in shown:
            problems.append(f"participant text contains {word}")
    if protocol["frozen"].get("verifier") != verifier_config(door):
        problems.append("frozen verifier config drifted")
    note_sha = protocol["frozen"]["note_sha256"]
    sessions = 0
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        sessions += 1
        meta, actor = target / "meta", row["actor"]
        if read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        requests = sorted((meta / "requests").glob("t*.json"))
        if requests and read(requests[0])["messages"] != head:
            problems.append(f"{actor}: turn-1 request is not the system and task text alone")
        delivered = read(meta / "delivered.json")
        if delivered["arm"] != row["arm"]:
            problems.append(f"{actor}: delivered files are tagged for the wrong arm")
        if delivered.get("door") != door:
            problems.append(f"{actor}: delivered files are tagged for the wrong door")
        want = extra_files(directory, row, door)
        got = {name: text.encode() for name, text in delivered["files"].items()}
        if got != want:
            problems.append(f"{actor}: delivered files differ from the carry-forward rule")
        if row["generation"] == 1:
            path, content = N.planted(row["arm"], door)
            if delivered["files"] != {path: content}:
                problems.append(f"{actor}: generation-1 seed is not the planted {row['arm']} file")
            if sha256(delivered["files"].get(path, "")) != note_sha.get(row["arm"]):
                problems.append(f"{actor}: generation-1 seed hash does not match the pinned {row['arm']} file")
        if delivered.get("shared_sha256") and delivered["shared_sha256"] != shared_digest(got):
            problems.append(f"{actor}: recorded shared_sha256 does not match delivered files")
        if (meta / "verifier.json").exists() and read(meta / "verifier.json") != verifier_config(door):
            problems.append(f"{actor}: session verifier does not match frozen {door}")
        for path in requests:
            for message in read(path)["messages"]:
                content = message.get("content") or ""
                if message.get("role") != "assistant" and (
                    "meta/audit" in content or "audit_bytes" in content
                ):
                    problems.append(f"{actor} {path.stem}: audit leaked into a request")
    return {"sessions": sessions, "problems": problems, "ok": not problems}
