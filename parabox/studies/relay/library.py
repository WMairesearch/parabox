"""The knowledge library.

The seed recipe stays in every static and dynamic library. In the dynamic arm each
accepted submission adds its file and the method note from that submit call. A session
with no accepted submission adds nothing. Feedback is private and never enters a library.
"""
from __future__ import annotations

from parabox.tasks.lean.prompts import LIBRARY_PREFIX


def _entry_blocks(entries: list[dict], carry_method: bool = True) -> list[str]:
    parts = []
    for item in entries:
        generation, turn, problem = item["generation"], item["turn"], item["problem"]
        file_text = item["file"]
        if not isinstance(file_text, str) or not file_text.strip():
            raise ValueError("accepted library entry needs a file")
        parts.append(f"Accepted file from generation {generation} ({problem}), turn {turn}:\n\n{file_text.rstrip()}\n")
        method = item.get("method") or ""
        if carry_method and isinstance(method, str) and method.strip():
            parts.append(f"Method from generation {generation} ({problem}), turn {turn}:\n\n{method.strip()}\n")
    return parts


def render(seed: str, entries: list[dict], carry_method: bool = True) -> str:
    """Seed recipe first. Each entry is an accepted file and, if written and carried, its method note."""
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("library seed is empty")
    return "\n".join([f"Seed recipe:\n\n{seed.strip()}\n", *_entry_blocks(entries, carry_method)])


def contribution_text(entries: list[dict], carry_method: bool = True) -> str:
    """What one session adds. The seed recipe is not repeated here."""
    return "\n".join(_entry_blocks(entries, carry_method)).strip()


def entries_before(arm: str, generation: int, chain_entries: dict[int, list[dict]]) -> list[dict]:
    """chain_entries maps an earlier generation of the same chain to its accepted entries."""
    if arm != "dynamic":
        return []
    return [item for g in sorted(chain_entries) if g < generation for item in chain_entries[g]]


def opening(arm: str, seed: str, entries: list[dict], carry_method: bool = True) -> list[str]:
    """The user messages that follow the task text on turn 1."""
    if arm == "isolated":
        return []
    return [LIBRARY_PREFIX + render(seed, entries, carry_method)]
