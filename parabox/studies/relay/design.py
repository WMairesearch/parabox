"""Blocks of three chains that share one problem sequence.

The sequence draw repeats the earlier two-arm design, so block b has the same five
problems it had there. The arm-to-slot draw and the generation order use their own
generators and do not change the sequences.
"""
from __future__ import annotations

import random

ARMS = ("isolated", "static", "dynamic")
SHARED = {"isolated": False, "static": True, "dynamic": True}
DESIGN_SEED = 2026092611


def design(pool: list[str], *, blocks: int = 12, generations: int = 5, seed: int = DESIGN_SEED):
    if len(pool) < 5 or not 1 <= generations <= 5:
        raise ValueError("a chain draws 5 distinct problems and runs at most 5 generations")
    sequences = random.Random(seed)
    arms = random.Random(seed + 101)
    order = random.Random(seed + 202)
    chains = []
    for block in range(blocks):
        sequence = sequences.sample(pool, 5)[:generations]
        # The earlier design drew a two-arm order here; the draw is kept so later blocks keep their sequences.
        sequences.shuffle(["dynamic", "static"])
        slots = list(ARMS)
        arms.shuffle(slots)
        for slot, arm in enumerate(slots):
            chains.append({
                "chain": f"b{block:02d}-s{slot}",
                "block": block,
                "slot": slot,
                "arm": arm,
                "sequence": sequence,
            })
    schedule = []
    for generation in range(1, generations + 1):
        index = list(range(len(chains)))
        order.shuffle(index)
        for i in index:
            chain = chains[i]
            schedule.append({
                "chain": chain["chain"],
                "block": chain["block"],
                "slot": chain["slot"],
                "arm": chain["arm"],
                "generation": generation,
                "problem": chain["sequence"][generation - 1],
                "actor": f"{chain['chain']}-g{generation:02d}",
            })
    return chains, schedule


def by_generation(schedule: list[dict]) -> list[list[dict]]:
    last = max((row["generation"] for row in schedule), default=0)
    return [[row for row in schedule if row["generation"] == g] for g in range(1, last + 1)]
