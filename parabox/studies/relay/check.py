"""Replay what each participant was sent and compare it with what the arm allows.

The first saved request of every session must carry the frozen system text, the arm's
task text, and exactly the library the arm delivers: none for isolated, the seed alone
for static, and the seed plus earlier accepted entries of the same chain for dynamic.
Later requests must keep that opening unchanged. No feedback text may reach a library.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay import design as D
from parabox.studies.relay import library as Lib
from parabox.studies.relay.run import delivery, load_seed, session_dir
from parabox.tasks.lean import task as LT
from parabox.util import read

ISOLATED_WORDS = ("library", "Library", "later participant")
MIN_FEEDBACK_MATCH = 40


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    integrity = protocol["frozen"]["integrity"]
    task = LT.LeanTask()
    seed = load_seed()
    problems = []
    libraries = {}
    feedback = []
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
        if row["arm"] == "static" and expected != Lib.opening("static", seed, []):
            problems.append(f"{row['actor']}: static library is not the seed alone")
        if expected:
            libraries[row["actor"]] = expected[0]
        feedback += [(row["actor"], item["message"]) for item in read(target / "meta" / "feedback.json")
                     if isinstance(item.get("message"), str) and len(item["message"]) >= MIN_FEEDBACK_MATCH]
    for actor, text in libraries.items():
        for author, message in feedback:
            if message in text and message not in seed:
                problems.append(f"{actor}: library contains feedback from {author}")
    return {"sessions": sum(1 for _ in (directory / "sessions").glob("*/end.json")), "libraries": len(libraries),
            "problems": problems, "ok": not problems}
