"""The Lean task with no integrity text and a list_dir tool, for the discovery study.

The system text drops the proof-integrity rules entirely and the task text tells the
participant to inspect its working directory with list_dir. A peer note, when the study
delivers one, is a plain file under /workspace/shared that the participant finds on its
own by listing and reading the directory; nothing about it enters the prompt.
"""
from __future__ import annotations

from parabox.sandbox import Box
from parabox.tasks.base import SessionState
from parabox.tasks.lean import prompts as P
from parabox.tasks.lean import verify as V
from parabox.tasks.lean.task import LeanTask
from parabox.util import truncate

LIST_DIR_MAX = 200


class DiscoveryLeanTask(LeanTask):
    def system(self, *, integrity: str, shared: bool) -> str:
        return P.discovery_system()

    def task(self, *, shared: bool) -> str:
        return P.discovery_task()

    def tools(self, *, shared: bool) -> list[dict]:
        return P.discovery_tools()

    def prompts_record(self, *, integrity: str, shared: bool) -> dict:
        return P.discovery_record()

    def call(self, box: Box, name: str, args: dict, state: SessionState) -> str:
        if name == "list_dir":
            try:
                return self._list_dir(args, state)
            except ValueError as error:
                return str(error)
        return super().call(box, name, args, state)

    def _list_dir(self, args: dict, state: SessionState) -> str:
        root = state.workspace
        base = V.workspace_path(root, args.get("path") or ".")
        if not base.exists():
            return f"No such path: {args.get('path')}"
        if base.is_file():
            return str(base.relative_to(root.resolve()))
        entries = []
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root.resolve())
            entries.append(f"{rel}/" if path.is_dir() else str(rel))
        if not entries:
            return "(empty)"
        return truncate("\n".join(entries[:LIST_DIR_MAX]))
