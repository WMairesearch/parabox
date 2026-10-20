"""Recompute accumulation counts and paired block-bootstrap intervals using only the standard library."""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path


DEFAULT_DATA = (
    Path(__file__).resolve().parents[1]
    / "report/decks/spread-of-misalignment/evidence/accumulation.json"
)
CONDITIONS = ("isolated", "static", "dynamic")
MODELS = {"gemini": "gemini-3.1-pro-preview", "deepseek": "deepseek-flash"}
PROTOCOL_COUNTS = {
    "blocks_per_model": 12,
    "generations": 5,
    "sessions_per_block_condition": 5,
    "sessions_per_model_condition": 60,
    "turn_limit": 20,
    "submission_limit": 10,
    "design_seed": 2026092611,
}
BOOTSTRAP = {
    "unit": "matched_block",
    "contrast": ["dynamic", "static"],
    "draws": 20000,
    "seed": 2026092612,
    "random_generator": "python.random.Random",
    "block_order": "ascending",
    "reset_rng_per_model": True,
    "confidence_level": 0.95,
    "quantile_indices": [500, 19500],
}
SOURCE_LABELS = {
    f"{model}_{kind}"
    for model in MODELS
    for kind in ("frozen_protocol", "session_schedule", "matched_chains", "saved_endpoints")
}


def require_fields(value, fields, context):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{context}: expected fields {', '.join(sorted(fields))}")


def require_integer(value, minimum, maximum, context):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{context}: expected an integer in {minimum}..{maximum}")


def validate(data):
    require_fields(data, {
        "schema_version", "description", "endpoint", "protocol", "conditions", "models",
        "bootstrap", "provenance", "source_files", "blocks", "expected",
    }, "evidence")
    require_integer(data["schema_version"], 1, 1, "schema_version")
    require_fields(data["conditions"], CONDITIONS, "conditions")
    if data["models"] != MODELS:
        raise ValueError("Expected the two recorded model IDs")
    protocol = data["protocol"]
    require_fields(protocol, set(PROTOCOL_COUNTS) | {
        "task_family", "matching", "interpretation",
    }, "protocol")
    for field, expected in PROTOCOL_COUNTS.items():
        require_integer(protocol[field], expected, expected, f"protocol.{field}")
    bootstrap = data["bootstrap"]
    require_fields(bootstrap, set(BOOTSTRAP) | {"convention"}, "bootstrap")
    if any(bootstrap[field] != value for field, value in BOOTSTRAP.items()):
        raise ValueError("Unsupported bootstrap convention")
    for field in ("draws", "seed"):
        require_integer(bootstrap[field], BOOTSTRAP[field], BOOTSTRAP[field], f"bootstrap.{field}")
    for index, expected in zip(bootstrap["quantile_indices"], BOOTSTRAP["quantile_indices"]):
        require_integer(index, expected, expected, "bootstrap.quantile_indices")
    descriptions = [
        data["description"], data["endpoint"], data["provenance"],
        protocol["task_family"], protocol["matching"], protocol["interpretation"],
        bootstrap["convention"], *data["conditions"].values(),
    ]
    if any(not isinstance(text, str) or not text.strip() for text in descriptions):
        raise ValueError("Evidence descriptions must be nonempty strings")
    sources = data["source_files"]
    if not isinstance(sources, list) or len(sources) != len(SOURCE_LABELS):
        raise ValueError("Expected eight source-file bindings")
    labels = set()
    for source in sources:
        require_fields(source, ("label", "sha256"), "source file")
        label = source["label"]
        if not isinstance(label, str) or label not in SOURCE_LABELS or label in labels:
            raise ValueError("Source labels must be unique, descriptive identifiers")
        checksum = source["sha256"]
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Invalid source-file SHA256")
        labels.add(label)
    records = data["blocks"]
    if not isinstance(records, list) or len(records) != 24:
        raise ValueError("Expected 24 matched-block records")
    seen = {model: set() for model in MODELS}
    for row in records:
        require_fields(row, ("model", "block", "sessions_per_condition", "violations"), "block")
        model = row["model"]
        if not isinstance(model, str) or model not in MODELS:
            raise ValueError("Unknown block model")
        require_integer(row["block"], 0, 11, "block number")
        if row["block"] in seen[model]:
            raise ValueError(f"Duplicate block for {model}")
        seen[model].add(row["block"])
        require_integer(row["sessions_per_condition"], 5, 5, "block sessions_per_condition")
        require_fields(row["violations"], CONDITIONS, "block conditions")
        for condition, count in row["violations"].items():
            require_integer(count, 0, 5, f"block {condition} count")
    if any(blocks != set(range(12)) for blocks in seen.values()):
        raise ValueError("Expected 12 unique blocks per model")
    require_fields(data["expected"], MODELS, "expected models")
    for expected in data["expected"].values():
        require_fields(expected, ("sessions_per_condition", "violations", "dynamic_minus_static"),
                       "expected result")
        require_integer(expected["sessions_per_condition"], 60, 60, "expected sessions_per_condition")
        require_fields(expected["violations"], CONDITIONS, "expected conditions")
        for condition, count in expected["violations"].items():
            require_integer(count, 0, 60, f"expected {condition} count")
        contrast = expected["dynamic_minus_static"]
        require_fields(contrast, ("value", "low", "high"), "expected contrast")
        if any(type(value) not in (int, float) or not -1 <= value <= 1
               for value in contrast.values()):
            raise ValueError("Expected contrast values must be finite numbers in -1..1")
        if contrast["low"] > contrast["high"]:
            raise ValueError("Expected interval endpoints are reversed")


def load(path=DEFAULT_DATA):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(data)
    return data


def recompute(data):
    validate(data)
    results = {}
    settings = data["bootstrap"]
    for model in MODELS:
        blocks = sorted((row for row in data["blocks"] if row["model"] == model),
                        key=lambda row: row["block"])
        denominator = sum(row["sessions_per_condition"] for row in blocks)
        totals = {
            condition: sum(row["violations"][condition] for row in blocks)
            for condition in CONDITIONS
        }
        rng = random.Random(settings["seed"])
        samples = []
        for _ in range(settings["draws"]):
            selected = [blocks[rng.randrange(len(blocks))] for _ in blocks]
            dynamic = sum(row["violations"]["dynamic"] for row in selected)
            static = sum(row["violations"]["static"] for row in selected)
            samples.append(dynamic / denominator - static / denominator)
        samples.sort()
        low_index, high_index = settings["quantile_indices"]
        results[model] = {
            "sessions_per_condition": denominator,
            "violations": totals,
            "dynamic_minus_static": {
                "value": totals["dynamic"] / denominator - totals["static"] / denominator,
                "low": samples[low_index],
                "high": samples[high_index],
            },
        }
    return results


def check_expected(data, results):
    for model in MODELS:
        if results[model] != data["expected"][model]:
            raise ValueError(f"{model}: recomputed totals or interval differ from expected values")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Block evidence JSON")
    parser.add_argument("--check", action="store_true", help="Check exact totals, effects and intervals")
    args = parser.parse_args(argv)
    try:
        data = load(args.data)
        results = recompute(data)
        if args.check:
            check_expected(data, results)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.check:
        print("Accumulation counts, effects and block-bootstrap intervals verified.")
    else:
        print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
