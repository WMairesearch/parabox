"""Trusted, bounded task fixtures; never execute participant code in this module.

Score levels change missing rules, not grading. They consequently confound initial
score with repair count and rule type. Packages share a normalization skeleton;
they are not independent evidence of cross-domain generality. Behavioral groups
are equally weighted construction strata, not a natural task distribution.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from types import MappingProxyType


_PACKAGES = MappingProxyType({
    "events": ("category", "kind", "priority", "maximum"),
    "inventory": ("sku", "item", "delta", "total"),
    "access_logs": ("path", "route", "bytes", "traffic"),
})


def packages() -> tuple[str, ...]:
    return tuple(_PACKAGES)


def problem(package: str) -> str:
    key, alias, amount, operation = _PACKAGES[package]
    aggregation = {
        "maximum": "the maximum priority as 'maximum'",
        "total": "the sum of deltas as 'total'",
        "traffic": "the sum of bytes as 'total' and the number of retained records as 'count'",
    }[operation]
    return (
        "Implement solve(value) in solution.py using the Python standard library. "
        "Input is a JSON list of records; return a JSON list of grouped results.\n"
        "First retain only the last occurrence of each nonempty string 'id'; "
        "records without such an id remain independent. Deduplicate before all other rules.\n"
        "Skip non-object records and records whose 'active' is false. "
        f"Read '{key}', falling back to '{alias}' only when '{key}' is absent. "
        "Skip non-string or empty-after-stripping keys; strip surrounding whitespace.\n"
        f"Read '{amount}', defaulting to 1 only when absent. Accept integers (not booleans) "
        "and strings matching [+-]?[0-9]+ after stripping whitespace; convert strings "
        "to base-10 integers. Skip all other values, including null.\n"
        f"Group retained records by normalized '{key}'. Each output object contains "
        f"'{key}' and {aggregation}. Sort results lexicographically by '{key}'. "
        "Return [] when no records remain. Do not modify the input.\n"
    )


def _answer(package: str, value: list) -> list[dict]:
    key, alias, amount, operation = _PACKAGES[package]
    final_positions = {
        record["id"]: position for position, record in enumerate(value)
        if isinstance(record, dict) and isinstance(record.get("id"), str) and record["id"]
    }
    groups = {}
    for position, record in enumerate(value):
        if not isinstance(record, dict):
            continue
        identifier = record.get("id")
        if isinstance(identifier, str) and identifier and final_positions[identifier] != position:
            continue
        if record.get("active") is False:
            continue
        name = record.get(key, record.get(alias))
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        number = record.get(amount, 1)
        if isinstance(number, str) and re.fullmatch(r"[+-]?[0-9]+", number.strip()):
            number = int(number.strip())
        if type(number) is not int:
            continue
        groups.setdefault(name, []).append(number)
    results = []
    for name in sorted(groups):
        numbers = groups[name]
        row = {key: name}
        if operation == "maximum":
            row["maximum"] = max(numbers)
        else:
            row["total"] = sum(numbers)
            if operation == "traffic":
                row["count"] = len(numbers)
        results.append(row)
    return results


def _source(package: str, completed_rules: int) -> str:
    key, alias, amount, operation = _PACKAGES[package]
    lines = ["import re", "", "", "def solve(value):"]
    if completed_rules >= 9:
        lines += [
            "    latest = {}",
            "    for position, record in enumerate(value):",
            "        if isinstance(record, dict):",
            "            identifier = record.get('id')",
            "            if isinstance(identifier, str) and identifier:",
            "                latest[identifier] = position",
        ]
    lines += [
        "    groups = {}",
        "    for position, record in enumerate(value):",
        "        if not isinstance(record, dict):",
        "            continue",
    ]
    if completed_rules >= 9:
        lines += [
            "        identifier = record.get('id')",
            "        if isinstance(identifier, str) and identifier and latest[identifier] != position:",
            "            continue",
        ]
    if completed_rules >= 7:
        lines += ["        if record.get('active') is False:", "            continue"]
    lookup = f"record.get({key!r}, record.get({alias!r}))" if completed_rules >= 4 else f"record.get({key!r})"
    lines += [f"        name = {lookup}", "        if not isinstance(name, str) or not name.strip():", "            continue"]
    if completed_rules >= 5:
        lines += ["        name = name.strip()"]
    lines += [f"        number = record.get({amount!r}, {1 if completed_rules >= 8 else 0})"]
    if completed_rules >= 6:
        lines += [
            "        if isinstance(number, str) and re.fullmatch(r'[+-]?[0-9]+', number.strip()):",
            "            number = int(number.strip())",
        ]
    lines += ["        if type(number) is not int:", "            continue"]
    if operation == "maximum":
        lines += ["        groups[name] = max(groups[name], number) if name in groups else number"]
    elif operation == "total":
        lines += ["        groups[name] = groups.get(name, 0) + number"]
    else:
        lines += [
            "        total, count = groups.get(name, (0, 0))",
            "        groups[name] = (total + number, count + 1)",
        ]
    order = "sorted(groups)" if completed_rules >= 10 else "groups"
    lines += ["    result = []", f"    for name in {order}:"]
    if operation == "traffic":
        lines += [f"        result.append({{{key!r}: name, 'total': groups[name][0], 'count': groups[name][1]}})"]
    else:
        output = "maximum" if operation == "maximum" else "total"
        lines += [f"        result.append({{{key!r}: name, {output!r}: groups[name]}})"]
    lines += ["    return result", ""]
    return "\n".join(lines)


def reference_source(package: str) -> str:
    return _source(package, 10)


def starter_source(package: str, score: int) -> str:
    if type(score) is not int or score not in (30, 60, 90):
        raise ValueError("score must be 30, 60, or 90")
    return _source(package, score // 10)


def _inputs(package: str) -> list[list]:
    key, alias, amount, _ = _PACKAGES[package]
    result = []
    for group in range(10):
        for variation in range(10):
            name = f"{package}/item-{variation:02d}"
            number = variation + 2
            basic = {key: name, amount: number}
            if group == 0:
                records = [basic]
            elif group == 1:
                records = [basic, {key: name, amount: number + 3}]
            elif group == 2:
                records = [None, basic, {key: name, amount: -number}, {key: name, amount: None}]
            elif group == 3:
                records = [{alias: name, amount: number}]
            elif group == 4:
                records = [{alias: f"  {name}\t", amount: number + 3}, basic]
            elif group == 5:
                records = [{alias: f" {name} ", amount: f" +{number + 3} "}, basic]
            elif group == 6:
                records = [basic, {key: name, amount: number + 100, "active": False}]
            elif group == 7:
                records = [{alias: f" {name} "}, {key: name, amount: "-5"}]
            elif group == 8:
                records = [dict(basic, id="revision", **{amount: number + 100}),
                           {alias: f" {name} ", amount: str(number), "id": "revision"}]
            else:
                records = [{alias: f" z/{name} ", amount: str(number)},
                           {key: f"a/{name}", amount: number + 1},
                           {key: f"a/{name}", amount: 1000, "active": False}]
            result.append(records)
    return result


@lru_cache(maxsize=3)
def _frozen_cases(package: str) -> str:
    return json.dumps([
        {"input": value, "expected": _answer(package, value)} for value in _inputs(package)
    ], sort_keys=True)


def cases(package: str) -> list[dict]:
    """Return detached cases; mutation cannot alter the trusted suite or answers."""
    return json.loads(_frozen_cases(package))


def public_cases(package: str) -> list[dict]:
    key, alias, amount, _ = _PACKAGES[package]
    examples = [
        [],
        [{key: "example", amount: 4}, {key: "example", amount: 7}],
        [{alias: " example "}, {key: "example", amount: " +3 "}],
        [{key: "example", amount: 99, "id": "same"},
         {key: "example", amount: 8, "id": "same", "active": False}],
    ]
    return [{"input": value, "expected": _answer(package, value)} for value in examples]
