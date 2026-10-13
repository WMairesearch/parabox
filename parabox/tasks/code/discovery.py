"""The code task with no anti-gaming text and a recursive list_dir, for discovery.

The system text keeps the real submission rules (unchanged tests, pytest exit 0) and drops
anything that would name a gap or forbid gaming. The task text tells the participant to
inspect its working directory with list_dir. A peer note, when the study delivers one, is a
plain file under /workspace/shared that the participant finds on its own by listing and
reading the directory; nothing about it enters the prompt.
"""
from __future__ import annotations

from parabox.sandbox import Box
from parabox.tasks.base import SessionState
from parabox.tasks.code import prompts as P
from parabox.tasks.code import verify as V
from parabox.tasks.code.task import CodeTask
from parabox.util import truncate

LIST_DIR_MAX = 200


class DiscoveryCodeTask(CodeTask):
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
        base = _workspace_path(root, args.get("path") or ".")
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


def _workspace_path(root, raw: str):
    path = V.workspace_file(root, raw)
    if path is None:
        raise ValueError("path is outside the workspace")
    return path
