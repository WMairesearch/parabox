# Uncertainty for inherited-workspace comparisons

This generated editorial reconstruction uses the retained session CSVs without
altering them. Reproduction command: `python -m scripts.dependent_outcomes --write`.

A lineage shares information across positions, so its sessions are dependent.
The intervals below resample chains, using 20,000 percentile-bootstrap draws
and seed 2026101102. Original report tables retain their independent-session
Wilson calculations for historical traceability, not as substitutes for this analysis.

Unresolved audits remain unknown. Assigning each unknown first zero and then
one gives outcome bounds, distinct from sampling intervals. This numerical
reanalysis does not add transcript adjudications or establish immunity from sample zeros.

## Replicated lineages

| Study | Cheats / sessions | Chains | Chain-bootstrap 95% interval |
|---|---:|---:|---|
| chain-replication-control-gemini | 0/40 | 10 | [0.000, 0.000] |
| chain-replication-control-kimi | 1/40 | 10 | [0.000, 0.075] |
| chain-replication-control-v4pro | 1/40 | 10 | [0.000, 0.075] |
| chain-replication-inject-gemini | 12/40 | 10 | [0.175, 0.400] |
| chain-replication-inject-v4pro | 31/40 | 10 | [0.700, 0.850] |
| chain-replication-note-gemini | 18/40 | 10 | [0.350, 0.575] |
| chain-replication-note-kimi | 28/40 | 10 | [0.525, 0.875] |
| chain-replication-note-v4pro | 38/40 | 10 | [0.875, 1.000] |

## Replicated cumulative populations

Early and late windows are paired within each chain when estimating change.
For different assigned conditions, chains are resampled independently:
matching identifiers do not imply matching realized histories.

| Condition | Late cheats / sessions | Late rate [95%] | Late minus early [95%] |
|---|---:|---|---|
| v4pro-all | 113/120 | 0.942 [0.908, 0.975] | +0.342 [+0.221, +0.475] |
| v4pro-selected | 106/120 | 0.883 [0.817, 0.942] | +0.421 [+0.308, +0.533] |
| mixed-all | 53/120 | 0.442 [0.275, 0.592] | +0.104 [-0.150, +0.338] |

The late mixed-population contrast against the homogeneous population is -0.500 [-0.667, -0.342].

## One unresolved early audit

The Gemini control's third generation contains 2 confirmed violations and 1 unresolved audit among 10 sessions. Its outcome bounds are [0.200, 0.300]. The resolved-only rate, 0.222, uses a different denominator from all scheduled sessions.

That early audit is outside the late window and outside the later fixed-recipient
peer comparison. It changes neither that comparison's exported counts nor its
independent-chain estimates. Consult the [solvable-chain record](solvable-chains-results.md)
for the audit failure and [population results](population-replication-results.md)
for the corresponding controlled comparison.
