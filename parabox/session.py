"""One participant session: a fresh container, a fixed turn budget, one tool per turn.

Every request is saved before it is sent, so what a participant saw can be replayed
from disk. A failed session is kept as it is and not resumed from the middle.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from parabox.model import Client, assistant_message, parse_args
from parabox.sandbox import Box
from parabox.tasks.base import SessionState, Task
from parabox.util import now, read, save, sha256

NO_TOOL = "Call exactly one tool."
IGNORED = "Only one tool is executed each turn. This call was ignored."


def run_session(task: Task, client: Client, box: Box, directory: Path, spec: dict, *,
                integrity: str, shared: bool, opening: list[str],
                extra_files: dict[str, bytes] | None = None,
                board: list[dict] | None = None, delivered_record: dict | None = None) -> dict:
    """opening holds the user messages sent after the task text, before turn 1.

    extra_files are written into the workspace after the task files. Studies use this
    to place files the task itself does not know about. A mounted directory is separate:
    the caller puts it on the box.

    board is the message board the session starts with, for a task with board tools.
    It is read only by tool call; nothing from it is put in the opening.
    """
    if (directory / "end.json").exists():
        return read(directory / "end.json")
    if any((directory / name).exists() for name in ("workspace", "meta")):
        raise RuntimeError("unfinished session evidence exists; archive the attempt with retry before restarting")
    workspace = directory / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    files = dict(task.workspace(spec["problem"]))
    files.update(extra_files or {})
    for name, data in files.items():
        dest = workspace / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    setup = getattr(task, "setup_workspace", None)
    if callable(setup):
        setup(workspace)
    meta = directory / "meta"
    if meta.exists():
        shutil.rmtree(meta)
    meta.mkdir(parents=True)
    save(meta / "spec.json", spec)
    if delivered_record is not None:
        save(meta / "delivered.json", delivered_record)
    tools = task.tools(shared=shared)
    messages = [
        {"role": "system", "content": task.system(integrity=integrity, shared=shared)},
        {"role": "user", "content": task.task(shared=shared)},
        *({"role": "user", "content": text} for text in opening),
    ]
    save(meta / "opening.json", [{"sha256": sha256(text), "text": text} for text in opening])
    state = SessionState(problem=spec["problem"], workspace=workspace, meta=meta, shared=shared)
    if board is not None:
        state.board_prior = [dict(record) for record in board]
        save(meta / "board-prior.json", state.board_prior)
    transcript = meta / "transcript.jsonl"
    normal, failure = False, None
    started = now()
    box.start()
    try:
        for turn in range(1, task.turns + 1):
            state.turn = turn
            save(meta / "requests" / f"t{turn:02d}.json", {"turn": turn, "messages": messages, "sent_at": now()})
            message, raw = client.complete(messages, tools=tools)
            (meta / "responses").mkdir(exist_ok=True)
            (meta / "responses" / f"t{turn:02d}.json").write_text(json.dumps(raw, ensure_ascii=False))
            messages.append(assistant_message(message))
            calls = message.get("tool_calls") or []
            if not calls:
                messages.append({"role": "user", "content": NO_TOOL})
                _log(transcript, {"turn": turn, "tool": None})
                continue
            call, ignored = calls[0], calls[1:]
            name = call.get("function", {}).get("name")
            try:
                args = parse_args(call)
            except json.JSONDecodeError:
                result = "The tool arguments were not valid JSON."
            else:
                result = task.call(box, name, args, state)
            messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call-{turn}", "content": result})
            for extra in ignored:
                messages.append({"role": "tool", "tool_call_id": extra.get("id") or f"call-{turn}-ignored", "content": IGNORED})
            _log(transcript, {"turn": turn, "tool": name, "ignored": len(ignored)})
            if state.finished:
                break
        normal = True
    except Exception as exc:
        failure = repr(exc)
    finally:
        box.stop()
    contribution = task.contribution(state)
    save(meta / "submissions.json", state.submissions)
    save(meta / "feedback.json", state.feedback)
    save(meta / "contribution.json", contribution)
    if board is not None:
        save(meta / "board-posts.json", state.board_posts)
        save(meta / "board-reads.json", state.board_reads)
    if state.report is not None:
        (meta / "report.txt").write_text(state.report)
    end = {
        **{key: spec[key] for key in spec},
        "started_at": started, "ended_at": now(), "normal": normal, "error": failure,
        "turns": state.turn, "submits": state.submits, "finished": state.finished,
        "accepted": sum(item["accepted"] for item in state.submissions),
        "feedback": len(state.feedback),
        "opening_sha256": [sha256(text) for text in opening],
    }
    save(directory / "end.json", end)
    return end


def _log(path: Path, row: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
