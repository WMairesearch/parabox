"""Explicit full-matrix design and matched recipient wave order."""
from __future__ import annotations

import copy
import json
import random
import re

from parabox.tasks.wiki.fixture import packages


CONDITIONS = ("empty_wiki", "artifacts_only", "full_wiki")
TRANSPORTS = ("persistent", "historical-withdrawal")


def default_spec(models: dict[str, str], image: str, transport: str = "persistent") -> dict:
    return {"schema_version": 1, "study": "shared_wiki", "models": dict(models),
            "image": image, "transport": transport, "positions": 6,
            "scores": [30, 60, 90], "conditions": list(CONDITIONS), "blocks": [0, 1, 2],
            "checkpoint_author": 0, "budget": 20, "turns": 40, "seed": 20261019,
            "workers_per_model": 4, "workers_total": 24, "automatic_retries": 0}


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("Expected a study specification")
    models = spec.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("At least one explicitly configured model is required")
    for name, config in models.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name)
                or not isinstance(config, str) or not config):
            raise ValueError("Expected a safe model name and configuration path")
    image = spec.get("image")
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Expected an immutable local image ID sha256:<64 hex digits>")
    if spec.get("transport") not in TRANSPORTS:
        raise ValueError("Unknown transport policy")
    expected = default_spec(models, image, spec["transport"])
    if set(spec) != set(expected):
        raise ValueError("Unknown or missing specification fields")
    flexible = {"positions", "scores", "conditions", "blocks", "workers_per_model", "workers_total"}
    for key in set(expected) - flexible:
        if json.dumps(spec[key], sort_keys=True, allow_nan=False) != json.dumps(expected[key], sort_keys=True):
            raise ValueError(f"Unsupported {key}")
    for key, upper in (("positions", 6), ("workers_per_model", 4), ("workers_total", 24)):
        if type(spec[key]) is not int or not 1 <= spec[key] <= upper:
            raise ValueError(f"Expected {key} between 1 and {upper}")
    for key, choices, kind in (("scores", (30, 60, 90), int),
                               ("blocks", (0, 1, 2), int), ("conditions", CONDITIONS, str)):
        values = spec[key]
        if (not isinstance(values, list) or not values
                or any(type(value) is not kind or value not in choices for value in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"Expected unique supported {key}")
    return copy.deepcopy(spec)


def build_plan(spec: dict) -> dict:
    spec = validate_spec(spec)
    assignments = packages()
    rows = []
    for model in sorted(spec["models"]):
        for score in spec["scores"]:
            for condition in spec["conditions"]:
                for block in spec["blocks"]:
                    chain = f"recipient-{model}-{score}-{condition}-{block:02d}"
                    for position in range(spec["positions"]):
                        rows.append({"actor": f"{chain}-{position:02d}", "chain": chain,
                            "model": model, "score": score, "condition": condition, "block": block,
                            "position": position, "package": assignments[(block + position) % 3],
                            "successors": [assignments[(block + later) % 3]
                                           for later in range(position + 1, spec["positions"])],
                            "source": False, "phase": "recipient", "budget": 20})
    orders = {}
    for model in sorted(spec["models"]):
        orders[model] = {}
        for position in range(spec["positions"]):
            wave = sorted((row for row in rows if row["model"] == model and row["position"] == position),
                          key=lambda row: (row["score"], row["condition"], row["block"]))
            random.Random(spec["seed"] + position).shuffle(wave)
            orders[model][str(position)] = [row["actor"] for row in wave]
    return {"sessions": rows, "wave_orders": orders,
            "counts": {"total": len(rows), "chains": len({row["chain"] for row in rows}),
                       "models": len(spec["models"])}}
