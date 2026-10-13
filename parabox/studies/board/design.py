"""Schedule for the board study. Counts are fixed before any model call."""
from __future__ import annotations

import random

from parabox.tasks.code.problems import IMPOSSIBLE, POSSIBLE, PROBLEMS

MAX_AGENTS = 150
BASELINE_WAVES = 13
BASELINE_WIDTH = 5
ENG_PER_NODE = 1
FORMAL_PER_NODE = 16
NODES = ("n0", "n1", "n2", "n3", "n4")
BASELINE_SEED = 2026092910
FORMAL_SEED = 2026092911
# Seats 0, 1 and 3 in each wave get an impossible problem.
IMPOSSIBLE_SEATS = frozenset({0, 1, 3})


def budget(nodes: tuple[str, ...] | list[str] = NODES) -> int:
    return BASELINE_WAVES * BASELINE_WIDTH + (ENG_PER_NODE + FORMAL_PER_NODE) * len(nodes)


def baseline_schedule() -> list[dict]:
    rows = []
    impossible_i = 0
    possible_i = 0
    for wave in range(BASELINE_WAVES):
        for seat in range(BASELINE_WIDTH):
            if seat in IMPOSSIBLE_SEATS:
                problem = IMPOSSIBLE[impossible_i % len(IMPOSSIBLE)]
                impossible_i += 1
            else:
                problem = POSSIBLE[possible_i % len(POSSIBLE)]
                possible_i += 1
            rows.append({
                "actor": f"base-w{wave:02d}-s{seat}",
                "phase": "baseline",
                "wave": wave,
                "seat": seat,
                "problem": problem,
                "possible": PROBLEMS[problem]["possible"],
                "node": None,
                "block": None,
            })
    return rows


def _blocks(per_node: int, seed: int) -> list[str]:
    """Half possible and half impossible when per_node is even. Each problem repeats as evenly as it can."""
    if per_node < 2 or per_node % 2:
        raise ValueError("per_node must be an even integer of at least 2")
    half = per_node // 2
    possible = [POSSIBLE[i % len(POSSIBLE)] for i in range(half)]
    impossible = [IMPOSSIBLE[i % len(IMPOSSIBLE)] for i in range(half)]
    rows = possible + impossible
    random.Random(seed).shuffle(rows)
    return rows


def probe_schedule(nodes: list[str], per_node: int, seed: int, phase: str) -> list[dict]:
    if per_node == 1:
        problems = ["reverse_words"]
    else:
        problems = _blocks(per_node, seed)
    rows = []
    for block, problem in enumerate(problems):
        for node in nodes:
            rows.append({
                "actor": f"{node}-b{block:02d}",
                "phase": phase,
                "wave": None,
                "seat": None,
                "problem": problem,
                "possible": PROBLEMS[problem]["possible"],
                "node": node,
                "block": block,
            })
    return rows
