"""Replay what each composition participant was sent and what was planted."""
from __future__ import annotations

import json
from pathlib import Path

from parabox.studies.composition import design as D
from parabox.studies.composition import notes as N
from parabox.studies.composition.run import extra_files, load_plan
from parabox.studies.composition.task import VERIFIER, CompositionTask
from parabox.studies.relay.run import session_dir
from parabox.studies.transmission.task import TASK
from parabox.tasks.code.problems import IMPOSSIBLE
from parabox.tasks.code.task import CACHE_DIR
from parabox.util import read, sha256

FORBIDDEN = ("conftest", CACHE_DIR, "K7", "condemn", "DeepSeek")


def _payload_text(payload: dict) -> str:
    tools = payload.get("tools")
    return "\n".join([
        str(payload.get("system") or ""),
        str(payload.get("task") or ""),
        json.dumps(tools, ensure_ascii=False) if tools is not None else "",
    ])


def _prompt_problems(payload: dict, prefix: str) -> list[str]:
    problems = []
    shown = _payload_text(payload)
    for word in FORBIDDEN:
        if word in shown:
            problems.append(f"{prefix} contains {word}")
    return problems


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = CompositionTask()
    problems = []
    live = task.prompts_record(integrity="plain", shared=False)["payload"]
    problems.extend(_prompt_problems(live, "prompts record"))
    if live.get("task") != TASK:
        problems.append("task text is not the transmission task")
    if (directory / "prompts.json").exists():
        saved = read(directory / "prompts.json")
        payload = saved.get("payload") or saved
        problems.extend(_prompt_problems(payload, "saved prompts"))
    protocol_problems = list(protocol.get("problems") or D.PROBLEMS)
    if protocol_problems != list(D.PROBLEMS):
        problems.append("protocol problems are not the frozen composition order")
    for name in protocol_problems:
        if name not in IMPOSSIBLE:
            problems.append(f"problem {name} is not in IMPOSSIBLE")
    if not all(name in IMPOSSIBLE for name in D.PROBLEMS):
        problems.append("design problems are not all in IMPOSSIBLE")
    if protocol.get("verifier") != VERIFIER:
        problems.append(f"protocol verifier is not {VERIFIER}")
    if protocol.get("frozen", {}).get("verifier") != VERIFIER:
        problems.append(f"frozen verifier is not {VERIFIER}")
    sessions = 0
    rows = load_plan(directory) if (directory / "plan.json").exists() else []
    for row in rows:
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists() and not (target / "meta" / "spec.json").exists():
            continue
        sessions += 1
        meta, actor = target / "meta", row["actor"]
        if (meta / "spec.json").exists():
            spec = read(meta / "spec.json")
            if spec.get("verifier") != VERIFIER:
                problems.append(f"{actor}: spec verifier is not {VERIFIER}")
            want = N.planted_digests(row["arm"], row["problem"])
            if spec.get("planted") != want:
                problems.append(f"{actor}: spec planted hashes do not match the frozen notes")
        if not (target / "end.json").exists():
            continue
        if (meta / "opening.json").exists() and read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        want_files = extra_files(row)
        if (meta / "delivered.json").exists():
            delivered = read(meta / "delivered.json")
            got = {name: text.encode() for name, text in delivered.get("files", {}).items()}
            if got != want_files:
                problems.append(f"{actor}: delivered files differ from the planted {row['arm']} notes")
            for path, data in want_files.items():
                if sha256(delivered.get("files", {}).get(path, "")) != sha256(data):
                    problems.append(f"{actor}: planted {path} hash does not match the frozen note")
    return {"sessions": sessions, "problems": problems, "ok": not problems}
