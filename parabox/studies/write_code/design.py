"""Design for the code-domain write-elicitation study.

Independent sessions. A block is one (problem, replicate) pair; the four arms share
the problem. Problems are the impossible pytest pool, matching the board study.
"""
from __future__ import annotations

import random

from parabox.tasks.code.problems import IMPOSSIBLE

ARMS = ("empty", "gift", "request", "request_audience")
DESIGN_SEED = 2026100601
DEFAULT_PROBLEMS = list(IMPOSSIBLE)


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
