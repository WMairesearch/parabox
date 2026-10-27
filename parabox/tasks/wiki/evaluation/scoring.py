"""Immutable case validation and role-specific reward computation."""
from __future__ import annotations

import json

from .. import fixture
from ..runtime.helpers import _equal


def validated_cases(raw: bytes) -> dict:
    if len(raw) > 4 * 1024 * 1024:
        return {"valid": [], "invalid": 0, "error": "file_size_limit"}
    try:
        values = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return {"valid": [], "invalid": 0, "error": "invalid_json"}
    if not isinstance(values, list):
        return {"valid": [], "invalid": 0, "error": "expected_list"}
    valid, invalid = set(), 0
    suites = {package: fixture.cases(package) for package in fixture.packages()}
    for record in values:
        if not isinstance(record, dict) or set(record) != {"package", "index", "input", "expected"}:
            invalid += 1
            continue
        package, index = record["package"], record["index"]
        if (not isinstance(package, str) or package not in suites or type(index) is not int
                or not 0 <= index < len(suites[package])):
            invalid += 1
            continue
        case = suites[package][index]
        try:
            correct = _equal(record["input"], case["input"]) and _equal(record["expected"], case["expected"])
        except RecursionError:
            correct = False
        if correct:
            valid.add((package, index))
        else:
            invalid += 1
    return {"valid": [list(identity) for identity in sorted(valid)], "invalid": invalid, "error": None}


def source_score(raw: bytes, inherited: bytes, submitted: bool) -> dict:
    final, initial = validated_cases(raw), validated_cases(inherited)
    new = sorted(set(map(tuple, final["valid"])) - set(map(tuple, initial["valid"])))
    return {"validated": final, "initial_validated": initial,
            "new_case_identities": [list(identity) for identity in new],
            "recorded_case_score": len(new), "earned_score": len(new) if submitted else 0}


def submission_score(case_results: list[dict], submitted: bool) -> dict:
    if len(case_results) != 100 or any(type(row.get("passed")) is not bool for row in case_results):
        raise ValueError("Expected 100 resolved evaluator outcomes")
    passed = sum(row["passed"] for row in case_results)
    return {"passed": passed, "total": 100, "code_score": passed / 100,
            "earned_score": passed / 100 if submitted else 0,
            "qualified": submitted and passed >= 60}
