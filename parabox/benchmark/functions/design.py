"""Registered function comparisons on the shared execution plan."""

from __future__ import annotations

import json
import random
from pathlib import Path


PROFILES = {
    "peer-composition": {"generations": 8, "replicates": 5, "recipients": 3,
                         "conditions": ["method"], "transport": "cumulative_all", "seed": 2026101101},
    "solvable-inheritance": {"generations": 8, "replicates": 10, "recipients": 0,
                             "conditions": ["control", "method"], "transport": "replace", "seed": 2026101005},
    "solvable-exposure": {"generations": 1, "replicates": 16, "recipients": 0,
                          "conditions": ["control", "method"], "transport": "none", "seed": 2026101004},
}


def configure(spec: dict, profile: str) -> dict:
    settings = PROFILES[profile]
    spec["suite_id"] = "function-" + profile + "-v1"
    spec["function_profile"] = profile
    spec["seed"] = settings["seed"]
    spec["core"] = {**settings, "gate": "open", "tasks": ["second_item"],
                    "turns": 50, "max_submits": 8, "initial_record": "condition_seed"}
    spec["wiki"].update(conditions=[], scores=[], blocks=[], positions=0)
    return spec


def initial_files(row: dict) -> dict[str, bytes]:
    if not row.get("function_profile"):
        return {}
    path = Path(__file__).parents[1] / "assets/function-seeds.json"
    seeds = json.loads(path.read_text())
    seed = seeds[row["condition"]]
    return {seed["path"]: seed["content"].encode()}


def build_plan(spec: dict) -> dict:
    core = spec["core"]
    rows, waves = [], []
    for candidate, config in spec["candidates"].items():
        candidate_rows = []
        for condition in core["conditions"]:
            for replicate in range(core["replicates"]):
                chain = f"{candidate}-{condition}-r{replicate:02d}"
                previous = []
                for generation in range(1, core["generations"] + 1):
                    current = []
                    for seat in range(core["recipients"] + 1):
                        actor = f"{chain}-g{generation:02d}-s{seat}"
                        current.append(actor)
                        candidate_rows.append({
                            "actor": actor, "component": "core", "chain": chain,
                            "function_profile": spec["function_profile"],
                            "matched_block": f"second_item-r{replicate:02d}",
                            "replicate": replicate, "problem": "second_item", "task_solvable": True,
                            "condition": condition, "generation": generation, "seat": seat,
                            "seats": core["recipients"] + 1,
                            "role": "recipient" if seat < core["recipients"] else "contributor",
                            "contributor": candidate,
                            "model_config": spec["reference_config"] if seat < core["recipients"] else config,
                            "gate": "open", "verifier": "pytest-open", "turns": 50, "max_submits": 8,
                            "depends_on": list(previous), "incoming_from": list(previous),
                            "transport": core["transport"],
                            "successor_actors": [f"{chain}-g{generation + 1:02d}-s{later}"
                                                 for later in range(core["recipients"] + 1)]
                            if generation < core["generations"] else [],
                        })
                    previous = current
        rng = random.Random(spec["seed"])
        for generation in range(1, core["generations"] + 1):
            group = [row for row in candidate_rows if row["generation"] == generation]
            rng.shuffle(group)
            rows.extend(group)
            waves.append({"id": f"core-{candidate}-g{generation}",
                          "actors": [row["actor"] for row in group],
                          "depends_on_waves": [f"core-{candidate}-g{generation - 1}"] if generation > 1 else []})
    return {"schema_version": 1, "suite_id": spec["suite_id"], "sessions": rows,
            "waves": waves, "contrasts": [],
            "counts": {"core_reference": 0, "core_candidates": len(rows), "wiki": 0,
                       "total": len(rows), "max_core_model_turns": 50 * len(rows),
                       "max_wiki_model_turns": 0, "max_wiki_charged_units": 0},
            "execution_policy": {"automatic_retries": 0, "requires_deadline": True,
                                 "failed_predecessor": "descendants_unavailable_no_replacement",
                                 "core_merge": core["transport"],
                                 "core_generation_inputs": "same_prior_snapshot_for_all_seats"},
            "analysis_contract": {"unit": "chain", "own_and_recipient_outcomes": "separate",
                                  "accepted_invalid": "independent audit of accepted submissions",
                                  "late_generations": [6, 7, 8] if core["generations"] == 8 else [1]}}
