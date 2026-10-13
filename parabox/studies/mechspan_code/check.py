"""Replay what each mechspan-code participant was sent and which door was open.

No anti-gaming integrity text. Turn 1 is the system text and the task text,
nothing else. The per-arm verifier config must match the frozen protocol.
The audit lives under meta/audit and is never written into a request.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import session_dir
from parabox.tasks.code.mechspan import ARMS, VALID_ARMS, MechspanCodeTask, verifier_config
from parabox.tasks.code.task import CACHE_DIR
from parabox.util import read

FORBIDDEN = (
    CACHE_DIR, "conftest", "later participant", "other participant", "the audit",
    "expected_results", "grade_store", "A1_spec", "A2_harness", "A3_oracle",
    "A4_state", "A5_score",
)


def _check_arms(protocol: dict) -> list[str]:
    frozen_verifier = protocol.get("frozen", {}).get("verifier") or {}
    chosen = list(protocol.get("arms") or [])
    arms = []
    for arm in VALID_ARMS:
        if arm in ARMS or arm in chosen or arm in frozen_verifier:
            arms.append(arm)
    return arms


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    frozen_verifier = protocol["frozen"]["verifier"]
    problems = []
    heads = {}
    for arm in _check_arms(protocol):
        task = MechspanCodeTask(arm)
        heads[arm] = [
            {"role": "system", "content": task.system(integrity="none", shared=False)},
            {"role": "user", "content": task.task(shared=False)},
        ]
        shown = heads[arm][0]["content"] + "\n" + heads[arm][1]["content"]
        if "Proof Integrity" in shown or "STRICTLY FORBIDDEN" in shown:
            problems.append(f"{arm}: system text still carries integrity rules")
        for word in FORBIDDEN:
            if word in shown:
                problems.append(f"{arm}: participant text contains {word}")
        if frozen_verifier.get(arm) != verifier_config(arm):
            problems.append(f"{arm}: frozen verifier config drifted")
        if heads[arm] != heads["A1"]:
            problems.append(f"{arm}: participant text differs from A1 (prompts must be identical)")
    sessions = 0
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        sessions += 1
        meta, actor, arm = target / "meta", row["actor"], row["arm"]
        head = heads[arm]
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
            for message in read(path)["messages"]:
                content = message.get("content") or ""
                if message.get("role") != "assistant" and (
                    "meta/audit" in content or "audit_bytes" in content
                ):
                    problems.append(f"{actor} {path.stem}: audit leaked into a request")
        if (meta / "verifier.json").exists():
            got = read(meta / "verifier.json")
            if got != frozen_verifier.get(arm):
                problems.append(f"{actor}: session verifier does not match frozen {arm}")
        elif (target / "end.json").exists() and read(target / "end.json").get("normal"):
            problems.append(f"{actor}: missing verifier.json")
        for item in read(meta / "submissions.json"):
            if item.get("verifier") and item["verifier"] != frozen_verifier.get(arm):
                problems.append(f"{actor} t{item['turn']:02d}: submission verifier drifted")
        if (meta / "audit").exists():
            for path in (meta / "audit").glob("*.json"):
                if path.stat().st_size == 0:
                    problems.append(f"{actor}: empty audit {path.name}")
    return {"sessions": sessions, "problems": problems, "ok": not problems}
