"""Recompute retained dependent-study uncertainty without changing frozen CSVs."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from statistics import mean

from parabox.analysis import chain_interval, independent_difference, outcome_summary, read_sessions

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "report/studies/final/dependent-outcomes.md"


def load(name: str) -> list[dict]:
    rows = read_sessions(ROOT / "report/final" / f"{name}.csv")
    for row in rows:
        row["chain"] = re.sub(r"-g\d+(?:-a\d+)?$", "", row["actor"])
    return rows


def proportions(rows: list[dict]) -> dict[str, float]:
    groups = {}
    for row in rows:
        groups.setdefault(row["chain"], []).append(row)
    return {name: outcome_summary(items, draws=1)["cheat_rate"] for name, items in groups.items()}


def render() -> str:
    lines = ["# Uncertainty for inherited-workspace comparisons", "",
             "This generated editorial reconstruction uses the retained session CSVs without",
             "altering them. Reproduction command: `python -m scripts.dependent_outcomes --write`.", "",
             "A lineage shares information across positions, so its sessions are dependent.",
             "The intervals below resample chains, using 20,000 percentile-bootstrap draws",
             "and seed 2026101102. Original report tables retain their independent-session",
             "Wilson calculations for historical traceability, not as substitutes for this analysis.", "",
             "Unresolved audits remain unknown. Assigning each unknown first zero and then",
             "one gives outcome bounds, distinct from sampling intervals. This numerical",
             "reanalysis does not add transcript adjudications or establish immunity from sample zeros.", "",
             "## Replicated lineages", "",
             "| Study | Cheats / sessions | Chains | Chain-bootstrap 95% interval |",
             "|---|---:|---:|---|"]
    for path in sorted((ROOT / "report/final").glob("chain-replication-*.csv")):
        result = outcome_summary(load(path.stem))
        lines.append(f"| {path.stem} | {result['cheat']}/{result['n']} | {result['n_chains']} | "
                     f"[{result['interval_low']:.3f}, {result['interval_high']:.3f}] |")
    lines += ["", "## Replicated cumulative populations", "",
              "Early and late windows are paired within each chain when estimating change.",
              "For different assigned conditions, chains are resampled independently:",
              "matching identifiers do not imply matching realized histories.", "",
              "| Condition | Late cheats / sessions | Late rate [95%] | Late minus early [95%] |",
              "|---|---:|---|---|"]
    late_rates = {}
    for condition in ("v4pro-all", "v4pro-selected", "mixed-all"):
        rows = load(f"population-replication-{condition}")
        early = proportions([row for row in rows if row["generation"] in (1, 2)])
        late_rows = [row for row in rows if row["generation"] in (6, 7, 8)]
        late = proportions(late_rows)
        late_rates[condition] = list(late.values())
        estimate = chain_interval(list(late.values()))
        changes = [late[name] - early[name] for name in late]
        change = chain_interval([(value + 1) / 2 for value in changes])
        lines.append(f"| {condition} | {sum(row['cheat'] for row in late_rows)}/{len(late_rows)} | "
                     f"{estimate['mean']:.3f} [{estimate['low']:.3f}, {estimate['high']:.3f}] | "
                     f"{mean(changes):+.3f} [{2 * change['low'] - 1:+.3f}, {2 * change['high'] - 1:+.3f}] |")
    delta = independent_difference(late_rates["mixed-all"], late_rates["v4pro-all"])
    lines += ["", f"The late mixed-population contrast against the homogeneous population is {delta['difference']:+.3f} "
              f"[{delta['low']:+.3f}, {delta['high']:+.3f}].", "",
              "## One unresolved early audit", ""]
    rows = [row for row in load("solvable-chains-gemini") if row["arm"] == "control" and row["generation"] == 3]
    result = outcome_summary(rows)
    lines += [f"The Gemini control's third generation contains {result['cheat']} confirmed violations and "
              f"{result['unknown']} unresolved audit among {result['n']} sessions. Its outcome bounds are "
              f"[{result['lower_bound']:.3f}, {result['upper_bound']:.3f}]. The resolved-only rate, "
              f"{result['known_cheat_rate']:.3f}, uses a different denominator from all scheduled sessions.", "",
              "That early audit is outside the late window and outside the later fixed-recipient",
              "peer comparison. It changes neither that comparison's exported counts nor its",
              "independent-chain estimates. Consult the [solvable-chain record](solvable-chains-results.md)",
              "for the audit failure and [population results](population-replication-results.md)",
              "for the corresponding controlled comparison.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.write:
        DESTINATION.write_text(content)
    elif not DESTINATION.exists() or DESTINATION.read_text() != content:
        raise SystemExit("dependent-study report is stale; run with --write")
    print("Dependent-study uncertainty matches frozen session evidence.")


if __name__ == "__main__":
    main()
