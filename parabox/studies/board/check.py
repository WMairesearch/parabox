"""Replay what a probe was shown.

The first request is only the system text and the task text. Neither names the cache
or conftest. The mounted board matches the frozen node, including after the session.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.board import board as B
from parabox.tasks.code.task import CACHE_DIR
from parabox.util import read

FORBIDDEN = (CACHE_DIR, "conftest")


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    prompts = read(directory / "prompts.json")["payload"]
    problems = []
    shown = prompts["system"] + "\n" + prompts["task"]
    for word in FORBIDDEN:
        if word in shown:
            problems.append(f"participant text contains {word}")
    if protocol["phase"] == "baseline":
        return _baseline(directory, prompts, problems)
    return _probes(directory, prompts, problems)


def _opening_ok(target: Path, prompts: dict, problems: list[str]) -> None:
    first = target / "meta" / "requests" / "t01.json"
    if not first.exists():
        problems.append(f"{target.name} has no first request")
        return
    messages = read(first)["messages"]
    if [item["role"] for item in messages] != ["system", "user"]:
        problems.append(f"{target.name} first request is not system then task")
        return
    if messages[0]["content"] != prompts["system"] or messages[1]["content"] != prompts["task"]:
        problems.append(f"{target.name} was not shown the frozen prompts")
    blob = messages[0]["content"] + "\n" + messages[1]["content"]
    for word in FORBIDDEN:
        if word in blob:
            problems.append(f"{target.name} first request contains {word}")


def _baseline(directory: Path, prompts: dict, problems: list[str]) -> dict:
    for row in read(directory / "schedule.json"):
        target = directory / "sessions" / row["actor"]
        if (target / "end.json").exists():
            _opening_ok(target, prompts, problems)
    return {"ok": not problems, "problems": problems}


def _probes(directory: Path, prompts: dict, problems: list[str]) -> dict:
    manifest = read(directory / "manifest.json")
    for row in read(directory / "schedule.json"):
        target = directory / "sessions" / row["actor"]
        _opening_ok(target, prompts, problems)
        expected = manifest["nodes"][row["node"]]["files"]
        for label, root in (("staged", directory / "nodes" / row["node"]), ("mounted", target / "board")):
            if not root.exists():
                problems.append(f"{row['actor']} is missing the {label} board")
                continue
            got = B.listing(root)
            if got != expected:
                problems.append(f"{row['actor']} {label} board does not match node {row['node']}")
        end = target / "end.json"
        if not end.exists():
            problems.append(f"{row['actor']} has no end.json")
        elif not read(end).get("normal"):
            problems.append(f"{row['actor']} did not end normally")
    return {"ok": not problems, "problems": problems}
