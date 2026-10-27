"""Design rows for single, chain, and population cells.

Single: 4 problems x 4 replicates. Chain: 4 lineages x 4 generations.
Population: K agents x G generations x chains. Order is shuffled with the
design seed, within a generation for chain and population.
"""
from __future__ import annotations

import random

from parabox.studies.unified import notes as N
from parabox.studies.unified.task import VERIFIER
from parabox.tasks.code.spec.problems import PROBLEMS as ALL_PROBLEMS

PROBLEMS = ("double", "label_zero", "first_char", "choose_case")
REPS = 4
LINEAGES = 4
CHAIN_GENERATIONS = 4
AGENTS = 4
POP_GENERATIONS = 8
CHAINS = 2
DESIGN_SEED = 2026100901
MODES = ("single", "chain", "population")
ARMS = (
    "control", "note", "method", "goal", "hint", "prohibit", "c1", "c3",
    "inject", "cue",
)


def assign_problem(index: int, problems=PROBLEMS) -> str:
    return problems[index % len(problems)]


def positive_count(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _models_for(arm: str, models) -> list | None:
    if not models:
        return None
    if isinstance(models, dict):
        found = models.get(arm)
        return list(found) if found else None
    return list(models)


def _attach_model(row: dict, arm: str, agent: int, models) -> dict:
    chosen = _models_for(arm, models)
    if chosen:
        row["model_config"] = chosen[agent % len(chosen)]
        row["models"] = list(chosen)
    return row


def design(*, mode: str, arms, gate: str, seed: int = DESIGN_SEED,
           problems=None, reps: int = REPS, lineages: int = LINEAGES,
           generations: int | None = None, agents: int = AGENTS,
           chains: int = CHAINS, merge: str = "all", models=None) -> list[dict]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if gate not in VERIFIER:
        raise ValueError(f"unknown gate {gate!r}")
    chosen = tuple(arms or ())
    if not chosen or len(set(chosen)) != len(chosen):
        raise ValueError("conditions must be nonempty and unique; use reps for repetitions")
    for condition in chosen:
        N.content_arm(condition)
    if merge not in ("all", "selected"):
        raise ValueError("merge must be all or selected")
    counts = {"reps": reps} if mode == "single" else {"lineages": lineages} if mode == "chain" else {"chains": chains, "agents": agents}
    if generations is not None:
        counts["generations"] = generations
    for name, value in counts.items():
        positive_count(name, value)
    pool = tuple(problems) if problems is not None else PROBLEMS
    if not pool:
        raise ValueError("problems must be nonempty")
    unknown_p = [name for name in pool if name not in ALL_PROBLEMS]
    if unknown_p:
        raise ValueError(f"unknown problems: {', '.join(unknown_p)}")
    verifier = VERIFIER[gate]
    if mode == "single":
        rows = []
        for arm in chosen:
            for index, problem in enumerate(pool):
                planted = N.planted_digests(arm, problem, gate)
                for replicate in range(1, reps + 1):
                    row = {
                        "actor": f"{arm}-p{index:02d}-r{replicate}",
                        "arm": arm,
                        "gate": gate,
                        "problem": problem,
                        "problem_index": index,
                        "replicate": replicate,
                        "generation": 1,
                        "agent": None,
                        "chain": None,
                        "verifier": verifier,
                        "planted": planted,
                        "merge": None,
                    }
                    _attach_model(row, arm, 0, models)
                    rows.append(row)
        rng = random.Random(seed)
        rng.shuffle(rows)
        return rows

    if mode == "chain":
        gens = CHAIN_GENERATIONS if generations is None else generations
        schedule = []
        for arm in chosen:
            for index in range(lineages):
                problem = assign_problem(index, pool)
                chain = f"{arm}-c{index:02d}"
                planted = N.planted_digests(arm, problem, gate)
                for generation in range(1, gens + 1):
                    row = {
                        "actor": f"{chain}-g{generation:02d}",
                        "arm": arm,
                        "gate": gate,
                        "problem": problem,
                        "problem_index": index,
                        "replicate": None,
                        "generation": generation,
                        "agent": None,
                        "chain": chain,
                        "chain_index": index,
                        "verifier": verifier,
                        "planted": planted,
                        "merge": None,
                    }
                    _attach_model(row, arm, 0, models)
                    schedule.append(row)
        ordered = []
        rng = random.Random(seed)
        for generation in range(1, gens + 1):
            rows = [row for row in schedule if row["generation"] == generation]
            rng.shuffle(rows)
            ordered.extend(rows)
        return ordered

    gens = POP_GENERATIONS if generations is None else generations
    schedule = []
    for arm in chosen:
        rule = N.merge_rule(arm, merge)
        for index in range(chains):
            problem = assign_problem(index, pool)
            chain = f"{arm}-c{index:02d}"
            planted = N.planted_digests(arm, problem, gate)
            for generation in range(1, gens + 1):
                for agent in range(agents):
                    row = {
                        "actor": f"{chain}-g{generation:02d}-a{agent}",
                        "arm": arm,
                        "gate": gate,
                        "problem": problem,
                        "problem_index": index,
                        "replicate": None,
                        "generation": generation,
                        "agent": agent,
                        "chain": chain,
                        "chain_index": index,
                        "verifier": verifier,
                        "planted": planted,
                        "merge": rule,
                    }
                    _attach_model(row, arm, agent, models)
                    schedule.append(row)
    ordered = []
    rng = random.Random(seed)
    for generation in range(1, gens + 1):
        rows = [row for row in schedule if row["generation"] == generation]
        rng.shuffle(rows)
        ordered.extend(rows)
    return ordered


def by_generation(schedule: list[dict]) -> list[list[dict]]:
    last = max((row["generation"] for row in schedule), default=0)
    return [[row for row in schedule if row["generation"] == g] for g in range(1, last + 1)]


def chains_in(rows: list[dict]) -> list[str]:
    seen = []
    for row in rows:
        chain = row.get("chain")
        if chain and chain not in seen:
            seen.append(chain)
    return seen
