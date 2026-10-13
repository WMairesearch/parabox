"""Replay each files-only participant's input and confirm the library carries no method.

Same replay as the relay check, over the files-only delivery: turn 1 is the frozen system
text, the arm's task text, and the arm's pushed library. Additionally, no dynamic library
may contain a Method block, and copied isolated sessions must match the recorded digest.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay import design as D
from parabox.studies.relay import library as Lib
from parabox.studies.relay.run import load_seed, session_dir
from parabox.studies.relay_files.run import delivery
from parabox.tasks.lean.files import FilesLeanTask
from parabox.util import digest_json, read

ISOLATED_WORDS = ("library", "Library", "later participant")
MIN_FEEDBACK_MATCH = 40


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    integrity = protocol["frozen"]["integrity"]
    task = FilesLeanTask()
    seed = load_seed()
    problems = []
    libraries = {}
    feedback = []
    source = protocol.get("isolated_from")
    for actor, digest in (source or {}).get("sessions", {}).items():
        end = session_dir(directory, actor) / "end.json"
        if not end.exists() or digest_json(read(end)) != digest:
            problems.append(f"{actor}: isolated session is not the copy recorded in protocol.json")
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        shared = D.SHARED[row["arm"]]
        expected = delivery(directory, row, seed)
        head = [
            {"role": "system", "content": task.system(integrity=integrity, shared=shared)},
            {"role": "user", "content": task.task(shared=shared)},
            *({"role": "user", "content": text} for text in expected),
        ]
        if [item["text"] for item in read(target / "meta" / "opening.json")] != expected:
            problems.append(f"{row['actor']}: saved opening differs from the {row['arm']} delivery")
        if read(target / "meta" / "requests" / "t01.json")["messages"] != head:
            problems.append(f"{row['actor']}: turn-1 request differs from the {row['arm']} delivery")
        for path in sorted((target / "meta" / "requests").glob("t*.json")):
            if read(path)["messages"][:len(head)] != head:
                problems.append(f"{row['actor']} {path.stem}: opening changed after turn 1")
        if row["arm"] == "isolated":
            visible = head[0]["content"] + head[1]["content"] + repr(task.tools(shared=False))
            problems += [f"{row['actor']}: isolated text mentions {word!r}" for word in ISOLATED_WORDS if word in visible]
            if read(target / "meta" / "opening.json"):
                problems.append(f"{row['actor']}: isolated session was sent a library")
        if row["arm"] == "static" and expected != Lib.opening("static", seed, [], False):
            problems.append(f"{row['actor']}: static library is not the seed alone")
        if expected:
            if "Method from generation" in expected[0]:
                problems.append(f"{row['actor']}: library contains a method note")
            libraries[row["actor"]] = expected[0]
        feedback += [(row["actor"], item["message"]) for item in read(target / "meta" / "feedback.json")
                     if isinstance(item.get("message"), str) and len(item["message"]) >= MIN_FEEDBACK_MATCH]
    for actor, text in libraries.items():
        for author, message in feedback:
            if message in text and message not in seed:
                problems.append(f"{actor}: library contains feedback from {author}")
    return {"sessions": sum(1 for _ in (directory / "sessions").glob("*/end.json")), "libraries": len(libraries),
            "problems": problems, "ok": not problems}
