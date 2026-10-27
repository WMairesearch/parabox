"""Explicit development configuration, without an execution authorization."""

from __future__ import annotations

import copy
import json
import re


def default_spec(candidates: dict[str, str], reference: str | None, image: str, *,
                 historical: bool = False, published: bool = False,
                 function_profile: str | None = None) -> dict:
    if sum((historical, published, function_profile is not None)) > 1:
        raise ValueError("Select one protocol profile")
    spec = {
        "schema_version": 1,
        "suite_id": "shared-work-development-v1" if historical else "shared-work-persistent-v1",
        "candidates": dict(candidates),
        "reference_config": reference,
        "image": image,
        "seed": 20261019,
        "workers_per_model": 4,
        "workers_total": 24,
        "automatic_retries": 0,
        "holdout": {"status": "unavailable", "enabled": False},
        "core": {
            "gate": "open",
            "tasks": ["reverse_words", "second_item", "double"],
            "conditions": ["isolated", "cumulative"],
            "generations": 2,
            "recipients": 2,
            "replicates": 1,
            "turns": 50,
            "max_submits": 8,
            "initial_record": "empty",
        },
        "wiki": {
            "conditions": ["empty_wiki", "full_wiki"],
            "scores": [30, 60, 90],
            "blocks": [0, 1, 2],
            "positions": 2,
            "checkpoint_author": 0,
            "budget": 20,
            "turns": 40,
            "withdraw_after_position": 0 if historical else None,
        },
    }
    if published:
        if reference is not None:
            raise ValueError("The published Wiki-only profile does not use a reference configuration")
        spec["suite_id"] = "shared-work-published-wiki-v1"
        spec["core"] = None
        spec["wiki"]["conditions"] = ["empty_wiki", "artifacts_only", "full_wiki"]
        spec["wiki"]["positions"] = 6
    if function_profile is not None:
        from parabox.benchmark.functions.design import PROFILES, configure
        if function_profile not in PROFILES:
            raise ValueError("Unknown function profile")
        if function_profile != "peer-composition" and reference is not None:
            raise ValueError("Single-model function profiles use only candidate configurations")
        spec = configure(spec, function_profile)
    return spec


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("Expected a suite object")
    candidates = spec.get("candidates")
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError("At least one explicitly configured candidate is required")
    for name, path in candidates.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name)
                or name == "reference" or not isinstance(path, str) or not path):
            raise ValueError("Invalid candidate name or configuration path")
    reference = spec.get("reference_config")
    published = spec.get("suite_id") == "shared-work-published-wiki-v1"
    function_profile = spec.get("function_profile")
    needs_reference = not published and function_profile not in ("solvable-inheritance", "solvable-exposure")
    if needs_reference and (not isinstance(reference, str) or not reference):
        raise ValueError("An explicit fixed reference configuration is required")
    image = spec.get("image")
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("An immutable local image ID sha256:<64 hex digits> is required")
    expected = default_spec(candidates, reference, image,
                            historical=spec.get("suite_id") == "shared-work-development-v1",
                            published=published, function_profile=function_profile)
    if json.dumps(spec, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
        raise ValueError("Unsupported suite variation; use a separately versioned design")
    return copy.deepcopy(spec)
