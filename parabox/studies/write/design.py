"""Design for the write-elicitation study.

No generations and no relay: every session is independent. A block is one (problem, replicate)
pair; the four arms in a block share the same problem so empty, gift, request, and
request_audience are compared on like problems. Problems are drawn from the impossible main
pool, matching the discovery run.
"""
from __future__ import annotations

import random

ARMS = ("empty", "gift", "request", "request_audience")
DESIGN_SEED = 2026100511
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
