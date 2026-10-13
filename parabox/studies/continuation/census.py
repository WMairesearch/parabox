"""Recompute the truncation-census selection: used the turn budget, no finish, not accepted."""
from __future__ import annotations

import json
from pathlib import Path

from parabox.util import read

ART = ("conftest.py",)


def find_turns(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("turns", "max_turns", "turn_limit") and isinstance(value, int):
                return value
        for value in obj.values():
            found = find_turns(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_turns(value)
            if found:
                return found
    return None


def protocol_turns(run_dir: Path) -> int | None:
    path = run_dir / "protocol.json"
    if not path.exists():
        return None
    try:
        return find_turns(read(path))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def tool_calls(session: Path) -> list[tuple[str, str]]:
    """Parse tool calls from Gemini `candidates` or OpenAI `choices` raw responses."""
    out = []
    folder = session / "meta" / "responses"
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("t*.json")):
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if "candidates" in raw:
            for candidate in raw.get("candidates") or []:
                parts = ((candidate.get("content") or {}).get("parts")) or []
                for part in parts:
                    if "functionCall" in part:
                        call = part["functionCall"]
                        out.append((call.get("name") or "", json.dumps(call.get("args") or {})))
            continue
        for choice in raw.get("choices") or []:
            for call in (choice.get("message") or {}).get("tool_calls") or []:
                fn = call.get("function") or {}
                out.append((fn.get("name") or "", fn.get("arguments") or ""))
    return out


def accepted(session: Path) -> bool:
    path = session / "meta" / "submissions.json"
    if not path.exists():
        return False
    try:
        rows = read(path)
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    if not isinstance(rows, list):
        return False
    return any(item.get("accepted") for item in rows)


def is_truncated(session: Path, limit: int | None) -> bool:
    if limit is None:
        return False
    responses = list((session / "meta" / "responses").glob("t*.json")) if (session / "meta" / "responses").is_dir() else []
    if len(responses) < limit:
        return False
    names = [name for name, _args in tool_calls(session)]
    return "finish" not in names


def truncated_not_accepted(session: Path, limit: int | None) -> bool:
    return is_truncated(session, limit) and not accepted(session)


def conftest_unsubmitted(session: Path) -> bool:
    """Wrote a conftest artifact and never submitted after that write (census late_art)."""
    calls = tool_calls(session)
    sub_idx = [i for i, (name, _args) in enumerate(calls) if name == "submit"]
    art_idx = [
        i for i, (name, args) in enumerate(calls)
        if name in ("write_file", "run_command")
        and any(token in args for token in ART)
        and ("write" in name or ">" in args or "tee" in args)
    ]
    return bool(art_idx and (not sub_idx or max(sub_idx) < max(art_idx)))


def session_spec(session: Path) -> dict:
    path = session / "meta" / "spec.json"
    if path.exists():
        try:
            return read(path)
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
    return {}


def orig_counts(session: Path) -> tuple[int, int, bool]:
    responses = list((session / "meta" / "responses").glob("t*.json")) if (session / "meta" / "responses").is_dir() else []
    turns = len(responses)
    end_path = session / "end.json"
    submits = 0
    if end_path.exists():
        try:
            end = read(end_path)
            submits = int(end.get("submits") or 0)
            if end.get("turns"):
                turns = int(end["turns"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    if not submits:
        sub_path = session / "meta" / "submissions.json"
        if sub_path.exists():
            try:
                rows = read(sub_path)
                submits = len(rows) if isinstance(rows, list) else 0
            except (OSError, json.JSONDecodeError, TypeError):
                submits = 0
    return turns, submits, accepted(session)


def select_sessions(run_dir: Path) -> list[dict]:
    run_dir = Path(run_dir)
    limit = protocol_turns(run_dir)
    rows = []
    sessions = run_dir / "sessions"
    if not sessions.is_dir():
        return rows
    for session in sorted(p for p in sessions.iterdir() if p.is_dir()):
        if not (session / "meta" / "responses").is_dir():
            continue
        if not truncated_not_accepted(session, limit):
            continue
        spec = session_spec(session)
        turns, submits, was_accepted = orig_counts(session)
        rows.append({
            "source_run": run_dir.name,
            "source_path": str(run_dir.resolve()),
            "actor": session.name,
            "arm": spec.get("arm") or "",
            "problem": spec.get("problem") or "",
            "orig_turns": turns,
            "orig_submits": submits,
            "orig_accepted": int(was_accepted),
            "orig_conftest_unsubmitted": int(conftest_unsubmitted(session)),
            "limit": limit,
        })
    return rows
