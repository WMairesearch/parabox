"""The Lean task for the files-only push relay.

Same as the relay's shared arm, except the pushed library carries only verifier-accepted
files, not the method notes. submit takes no method, and the task text does not offer one.
shared=False is the relay isolated arm, unchanged, so its 60 sessions can be reused.
"""
from __future__ import annotations

from parabox.tasks.lean import prompts as P
from parabox.tasks.lean.task import LeanTask


class FilesLeanTask(LeanTask):
    def system(self, *, integrity: str, shared: bool) -> str:
        return P.system(integrity, shared)

    def task(self, *, shared: bool) -> str:
        return P.files_task() if shared else P.task(False)

    def tools(self, *, shared: bool) -> list[dict]:
        return P.files_tools() if shared else P.tools(False)

    def prompts_record(self, *, integrity: str, shared: bool) -> dict:
        return P.files_record(integrity) if shared else P.record(integrity, False)
