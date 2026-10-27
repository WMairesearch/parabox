"""Offline session-table reading and independent-chain uncertainty."""
from __future__ import annotations

import csv
import random
from pathlib import Path
from statistics import mean

BOOLEAN_FIELDS = {"accepted", "first_submit_accepted", "audit_ok", "cheat",
                  "gate_artifact", "unsubmitted_attempt", "truncated", "refused",
                  "read_note", "wrote_shared", "normal", "audit_unknown"}
INTEGER_FIELDS = {"generation", "agent", "turns_used", "submits"}


def read_sessions(path: str | Path) -> list[dict]:
    """Read legacy mixed-header or session-only CSV without interpreting cells as sessions."""
    rows = []
    header = None
    seen = set()
    with Path(path).open(newline="") as handle:
        for line in csv.reader(handle):
            if not line:
                continue
            if line[0] == "row_kind":
                header = line
                continue
            if line[0] != "session":
                continue
            if header is None or "actor" not in header or len(line) != len(header):
                raise ValueError("session row has no matching session header")
            row = dict(zip(header, line))
            if not row["actor"] or row["actor"] in seen:
                raise ValueError("missing or duplicate actor")
            seen.add(row["actor"])
            for key in BOOLEAN_FIELDS & row.keys():
                raw = row[key]
                if raw not in ("True", "False", "", "true", "false"):
                    raise ValueError(f"invalid boolean in {key}")
                row[key] = None if raw == "" else raw.lower() == "true"
            for key in INTEGER_FIELDS & row.keys():
                row[key] = int(row[key]) if row[key] else None
            rows.append(row)
    return rows


def percentile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("nonempty values and probability in [0, 1] required")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def outcome_value(row: dict) -> bool | None:
    if row.get("cheat") is True:
        return True
    if row.get("normal", True) is not True:
        return None
    if row.get("accepted") and (row.get("audit_unknown") or row.get("audit_ok") is not True):
        return None
    return False


def outcome_summary(rows: list[dict], *, draws: int = 20_000) -> dict:
    from parabox.studies.support.stats import wilson

    outcomes = [outcome_value(row) for row in rows]
    total = len(rows)
    cheats = sum(value is True for value in outcomes)
    unknown = sum(value is None for value in outcomes)
    known = total - unknown
    clusters = {}
    for row, value in zip(rows, outcomes):
        if row.get("chain"):
            clusters.setdefault(row["chain"], []).append(value)
    rates = [sum(values) / len(values) for values in clusters.values() if None not in values]
    clustered = bool(clusters)
    interval = (chain_interval(rates, draws=draws) if clustered else wilson(cheats, total)) if total and not unknown else {}
    interval = interval or {}
    return {"n": total, "cheat": cheats, "unknown": unknown, "known": known,
            "cheat_rate": cheats / total if total and not unknown else None,
            "known_cheat_rate": cheats / known if known else None,
            "lower_bound": cheats / total if total else None,
            "upper_bound": (cheats + unknown) / total if total else None,
            "interval_method": "independent-chain percentile bootstrap" if clustered else "Wilson independent sessions",
            "n_chains": len(clusters), "complete_known_chains": len(rates),
            "chain_mean": mean(rates) if rates else None,
            "interval_low": interval.get("low"), "interval_high": interval.get("high")}


def chain_interval(values: list[float], *, draws: int = 20_000, seed: int = 2026101102) -> dict:
    if draws < 1 or any(not 0 <= value <= 1 for value in values):
        raise ValueError("positive draws and chain proportions in [0, 1] required")
    if not values:
        return {"n_chains": 0, "mean": None, "low": None, "high": None}
    estimate = mean(values)
    if len(values) < 2:
        return {"n_chains": 1, "mean": estimate, "low": None, "high": None}
    generator = random.Random(seed)
    samples = [mean(generator.choices(values, k=len(values))) for _ in range(draws)]
    return {"n_chains": len(values), "mean": estimate,
            "low": percentile(samples, 0.025), "high": percentile(samples, 0.975)}


def independent_difference(treatment: list[float], control: list[float], *,
                           draws: int = 20_000, seed: int = 2026101102) -> dict:
    if draws < 1 or any(not 0 <= value <= 1 for value in treatment + control):
        raise ValueError("positive draws and chain proportions in [0, 1] required")
    if not treatment or not control:
        return {"difference": None, "low": None, "high": None}
    estimate = mean(treatment) - mean(control)
    if min(len(treatment), len(control)) < 2:
        return {"difference": estimate, "low": None, "high": None}
    generator = random.Random(seed)
    samples = [mean(generator.choices(treatment, k=len(treatment)))
               - mean(generator.choices(control, k=len(control))) for _ in range(draws)]
    return {"difference": estimate, "low": percentile(samples, 0.025),
            "high": percentile(samples, 0.975)}


def late_chains(rows: list[dict], *, chains: int = 5) -> list[dict]:
    """Nine recipient outcomes, with completion required for all late-window seats."""
    results = []
    expected = {(generation, agent) for generation in (6, 7, 8) for agent in (0, 1, 2)}
    for index in range(chains):
        name = f"mixed-method-c{index:02d}"
        selected = [row for row in rows if row.get("chain") == name
                    and (row.get("generation"), row.get("agent")) in expected]
        slots = {(row["generation"], row["agent"]) for row in selected}
        if len(slots) != len(selected):
            raise ValueError(f"duplicate recipient slot in {name}")
        late = [row for row in rows if row.get("chain") == name and row.get("generation") in (6, 7, 8)]
        all_slots = {(generation, agent) for generation in (6, 7, 8) for agent in range(4)}
        observed = {(row["generation"], row["agent"]) for row in late}
        if len(observed) != len(late):
            raise ValueError(f"duplicate late slot in {name}")
        complete = observed == all_slots and all(row.get("normal") is True for row in late)
        cheats = sum(row.get("cheat") is True for row in selected)
        unknown = sum(row.get("accepted") is True and row.get("audit_unknown") is True
                      for row in selected)
        results.append({"chain": name, "complete": complete, "n": len(selected),
                        "cheats": cheats, "audit_unknown": unknown,
                        "rate": cheats / 9 if complete and unknown == 0 else None,
                        "lower": cheats / 9 if complete else None,
                        "upper": (cheats + unknown) / 9 if complete else None})
    return results
