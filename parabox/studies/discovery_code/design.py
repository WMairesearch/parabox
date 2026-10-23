"""Design for discovery on the code/pytest task.

No generations and no relay: every session is independent. A block is one (problem, replicate)
pair; the three arms in a block share the same problem so control, help, and method are compared
on like problems. Problems are the impossible pytest pool: honest code cannot pass.
"""
from __future__ import annotations

import random

from parabox.tasks.code.spec.problems import IMPOSSIBLE

ARMS = ("control", "help", "method")
DESIGN_SEED = 2026100602
BASELINE_SEED = 2026100701
BASELINE_SEED_B = 2026100702
DEFAULT_PROBLEMS = list(IMPOSSIBLE)
DEFAULT_REPLICATES = 4
BASELINE_REPLICATES = 24
BASELINE_REPLICATES_B = 12


def design(problems: list[str], replicates: int, seed: int = DESIGN_SEED,
           arms: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    chosen = tuple(arms) if arms is not None else ARMS
    unknown = [arm for arm in chosen if arm not in ARMS]
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
