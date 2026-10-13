# Report and evidence

This directory contains the current presentation, study protocols, results and
supporting evidence. Runtime inputs belong in [`data/`](../data/README.md).

| Path | Purpose |
|---|---|
| `decks/spread-of-misalignment/` | Presentation sources, generated tables and figures |
| `studies/final/` | Protocols, results, execution deviations and limitations |
| `final/` | Session tables and peer-composition registration, outcomes, verification and analysis |
| `mechspan/profiles.csv` | Historical reference-gate comparison supporting the study history |
| `composition/` | Historical condemnation/writeback comparisons |
| `longchain/`, `population/` | Historical generational contrasts, not pooled with current results |

From the repository root, regenerate the narrative figures with
`python -m scripts.spread_figures`, check tables with `python -m scripts.deck_tables`,
and recompute peer-composition statistics with `python -m scripts.peer_analysis`.
`python -m scripts.peer_figures` regenerates the supplemental interval plot.
Figure generation requires the `report` extra. See the
[presentation instructions](decks/spread-of-misalignment/README.md).

Evidence files were relocated without changing their contents. Paths, study
identifiers and hashes embedded in frozen records describe the original runs,
not necessarily this public layout. Protocols are reader-facing editorial
editions; see [provenance](../docs/history.md).

Sanitized outcomes support numerical recomputation, not independent raw-trace
adjudication. Raw runs, internal review, exploratory continuations, unrelated
results and old report drafts remain in the original repository. Retained
historical comparisons are included only to interpret the current report.
See [evidence limits](../docs/reproducibility.md) and [third-party notices](../THIRD_PARTY.md).
