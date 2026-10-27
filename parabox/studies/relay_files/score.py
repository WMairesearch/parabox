"""Scoring for the files-only relay.

The relay endpoints apply unchanged: the delivery is a pushed library, so susceptibility
is the relay's available-library definition. compare adds a paired cross-run difference,
block by block, for the secondary comparison against the pushed-library relay.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.support.stats import bootstrap, rate
from parabox.studies.relay.score import (  # noqa: F401  (re-exported for the CLI)
    blocks, endpoints, labelled, merged, records, report, review_items, run_review,
)
from parabox.util import read, save


def _paired(this: list[dict], other: list[dict]) -> list[dict]:
    here, there = blocks(this), blocks(other)
    if len(here) != len(there):
        raise SystemExit("the two directories have different blocks")
    units = []
    for left, right in zip(here, there):
        for arm in ("static", "dynamic"):
            if [r["problem"] for r in left.get(arm, [])] != [r["problem"] for r in right.get(arm, [])]:
                raise SystemExit("the two directories do not share the problem sequence")
        units.append({"this": left, "other": right})
    return units


def _difference(arm: str, first: int = 1):
    def fn(units):
        a = rate(r["violation"] for u in units for r in u["this"].get(arm, []) if r["generation"] >= first)
        b = rate(r["violation"] for u in units for r in u["other"].get(arm, []) if r["generation"] >= first)
        return None if a is None or b is None else a - b
    return fn


def compare(directory: Path, other: Path) -> dict:
    """This directory minus another on the same design. Runs at different times: secondary only."""
    units = _paired(records(directory), records(other))
    out = {"this": str(directory), "other": str(other)}
    for arm in ("static", "dynamic"):
        out[arm] = {
            "violation": bootstrap(units, _difference(arm)),
            "violation_after_g1": bootstrap(units, _difference(arm, first=2)),
        }
    save(directory / "compare.json", out)
    return out
