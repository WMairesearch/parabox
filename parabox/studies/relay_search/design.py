"""Blocks of three chains that all run one problem for every generation.

Unlike the relay design, where a chain draws five distinct problems, here each chain keeps
a single problem across its generations. This matches the Hugging Face setting where many
agents worked the same task and could reuse one another's artifacts directly. Because the
blocks no longer share the relay's five-problem sequences, a search run is not block-paired
with the earlier runs. Arms, the shared flag, and the generation grouping are the relay's.
"""
from __future__ import annotations

import random

from parabox.studies.relay.design import ARMS, SHARED, by_generation  # noqa: F401  (re-exported)

DESIGN_SEED = 2026100111


def _block_problems(pool: list[str], blocks: int, rng: random.Random) -> list[str]:
    """One problem per block, each pool problem used as evenly as the block count allows."""
    repeated = (pool * (blocks // len(pool) + 1))[:blocks]
    rng.shuffle(repeated)
    return repeated


def design(pool: list[str], *, blocks: int = 12, generations: int = 5, seed: int = DESIGN_SEED):
    if not pool or not 1 <= generations <= 5:
        raise ValueError("a chain runs at most 5 generations over a nonempty pool")
    problems = random.Random(seed)
    arms = random.Random(seed + 101)
    order = random.Random(seed + 202)
    block_problems = _block_problems(pool, blocks, problems)
    chains = []
    for block in range(blocks):
        problem = block_problems[block]
        slots = list(ARMS)
        arms.shuffle(slots)
        for slot, arm in enumerate(slots):
            chains.append({
                "chain": f"b{block:02d}-s{slot}",
                "block": block,
                "slot": slot,
                "arm": arm,
                "problem": problem,
                "sequence": [problem] * generations,
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
                "problem": chain["problem"],
                "actor": f"{chain['chain']}-g{generation:02d}",
            })
    return chains, schedule
