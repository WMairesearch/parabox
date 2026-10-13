"""Design for the discovery study.

No generations and no relay: every session is independent. A block is one (problem, replicate)
pair; the three arms in a block share the same problem so control, help, and method are compared
on like problems. Problems are drawn from the impossible main pool.
"""
from __future__ import annotations

import random

ARMS = ("control", "help", "method")
DESIGN_SEED = 2026100411
DEFAULT_PROBLEMS = ["collatz", "beal", "sendov", "three_cubes"]


def design(problems: list[str], replicates: int, seed: int = DESIGN_SEED) -> list[dict]:
    rng = random.Random(seed)
    blocks = [(problem, r) for problem in problems for r in range(replicates)]
    rng.shuffle(blocks)
    schedule = []
    for block, (problem, replicate) in enumerate(blocks):
        for arm in ARMS:
            schedule.append({
                "actor": f"b{block:02d}-{arm}",
                "block": block,
                "arm": arm,
                "problem": problem,
                "replicate": replicate,
            })
    return schedule
