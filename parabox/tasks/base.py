"""What a study needs from a task.

A task owns the workspace, the tools, the participant-facing verifier, and the research
audit. It knows nothing about arms, libraries, or generations; studies sit above it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from parabox.sandbox import Box
from parabox.util import read


@dataclass
class SessionState:
    problem: str
    workspace: Path
    meta: Path
    shared: bool
    turn: int = 0
    submits: int = 0
    submissions: list[dict] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)
    report: str | None = None
    finished: bool = False
    board_prior: list[dict] = field(default_factory=list)
    board_posts: list[dict] = field(default_factory=list)
    board_reads: list[dict] = field(default_factory=list)


class Task(Protocol):
    name: str
    image: str
    turns: int

    def workspace(self, problem: str) -> dict[str, bytes]: ...

    def system(self, *, integrity: str, shared: bool) -> str: ...

    def task(self, *, shared: bool) -> str: ...

    def tools(self, *, shared: bool) -> list[dict]: ...

    def prompts_record(self, *, integrity: str, shared: bool) -> dict: ...

    def call(self, box: Box, name: str, args: dict, state: SessionState) -> str: ...

    def contribution(self, state: SessionState) -> list[dict]: ...

    def audit(self, raw: bytes, problem: str, scratch: Path) -> dict: ...


def run_audit_session(task: Task, session_dir: Path, spec: dict, scratch: Path) -> dict:
    """Prefer a task-specific session audit. Otherwise audit the last accepted file."""
    method = getattr(task, "audit_session", None)
    if callable(method):
        return method(session_dir, spec, scratch)
    return fallback_audit_session(task, session_dir, spec, scratch)


def fallback_audit_session(task: Task, session_dir: Path, spec: dict, scratch: Path) -> dict:
    submissions = read(Path(session_dir) / "meta" / "submissions.json")
    accepted = [item for item in submissions if item.get("accepted")]
    if not accepted:
        return {"violation": None, "reason": "no_accepted"}
    last = accepted[-1]
    folder = Path(session_dir) / "meta" / "submissions"
    raw_files = [path for path in sorted(folder.glob(f"t{last['turn']:02d}.*")) if path.suffix != ".json"]
    if not raw_files:
        return {"violation": None, "reason": "missing_submission"}
    return task.audit(raw_files[0].read_bytes(), spec["problem"], scratch)
