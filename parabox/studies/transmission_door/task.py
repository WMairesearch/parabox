"""Mechspan A4/A5 verifier plus the transmission chain task text.

The participant-facing task is the frozen transmission TASK: list_dir, a writable
shared/ folder, later-reader clause. It names no door. Rejection replies stay
exactly as MechspanCodeTask produces them.
"""
from __future__ import annotations

from parabox.studies.transmission.task import TASK, forbidden_in_prompts, task_text
from parabox.tasks.code import prompts as P
from parabox.tasks.code.mechspan import MechspanCodeTask, verifier_config
from parabox.tasks.code.task import TURNS
from parabox.util import digest_json

DOOR_WORDS = ("grade_store", "grade store", "score.json", "A4_state", "A5_score")


class DoorChainTask(MechspanCodeTask):
    name = "zerodoor_code"

    def __init__(self, arm: str = "A4", turns: int = TURNS):
        super().__init__(arm)
        self.turns = turns

    def system(self, *, integrity: str, shared: bool) -> str:
        return P.system(integrity, shared)

    def task(self, *, shared: bool) -> str:
        return task_text(self.turns)

    def tools(self, *, shared: bool) -> list[dict]:
        return P.tools(shared)

    def prompts_record(self, *, integrity: str, shared: bool) -> dict:
        payload = {
            "arm": self.arm,
            "carrier": "transmission_door",
            "system": self.system(integrity=integrity, shared=shared),
            "task": self.task(shared=shared),
            "tools": self.tools(shared=shared),
            "verifier": verifier_config(self.arm),
        }
        return {"payload": payload, "sha256": digest_json(payload)}


def forbidden_words() -> tuple[str, ...]:
    return forbidden_in_prompts() + DOOR_WORDS
