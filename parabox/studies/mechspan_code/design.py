"""Design for mechanism-span on the code/pytest task.

A block is one (problem, replicate) pair. Every block emits all five cells on
the same impossible problem so A1–A5 are compared on like items. Each cell
leaves only its assigned mechanism as a viable path to acceptance.
"""
from __future__ import annotations

import random

from parabox.studies.code.mechspan import ARMS, VALID_ARMS
from parabox.tasks.code.spec.problems import IMPOSSIBLE

DESIGN_SEED = 2026100901
DEFAULT_PROBLEMS = list(IMPOSSIBLE)
DEFAULT_REPLICATES = 6


def design(problems: list[str], replicates: int, seed: int = DESIGN_SEED,
           arms: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    chosen = tuple(arms) if arms is not None else ARMS
    unknown = [arm for arm in chosen if arm not in VALID_ARMS]
    if unknown:
        raise ValueError(f"unknown arms: {', '.join(unknown)}")
    if not chosen:
        raise ValueError("arms must not be empty")
    rng = random.Random(seed)
    blocks = [(problem, r) for problem in problems for r in range(replicates)]
    rng.shuffle(blocks)
    schedule = []
    for block, (problem, replicate) in enumerate(blocks):
        for arm in chosen:
            schedule.append({
                "actor": f"b{block:02d}-{arm}",
                "block": block,
                "arm": arm,
                "problem": problem,
                "replicate": replicate,
            })
    return schedule
