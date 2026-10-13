# Peer influence on the spread of misalignment

See the [generated results](peer-composition-results.md),
[preregistration](peer-composition.md) and [execution record](peer-composition-execution.md).
All six conditions completed 160 normal sessions. Including five retained
infrastructure failures, there were 965 starts, below the 1,000-session cap.
Every accepted session has a known audit outcome.

## What changed relative to earlier experiments

The solvable-chain study changes the entire lineage model. Earlier mixed-population comparisons
can also mix recipient susceptibility with the peer's own outcome in the
population average. The peer-composition study keeps seats 0–2 as V4 Pro, changes only seat 3, and
excludes that peer from the primary endpoint. Initial task, note, merge and
budget are held fixed. The assigned variable is the model configuration;
the content of subsequent messages is an endogenous outcome.

## Observed result

Across generations 6–8, V4 Pro recipients cheat in 45/45 sessions with a
V4 Pro peer, 18/45 with Gemini, 18/45 with Kimi, and 0/45 with each of Qwen
Max, DeepSeek Flash and Qwen Flash. Every late non-cheating recipient in
these conditions has accepted, audit-clean submissions: 27/45 for Gemini and Kimi,
45/45 for each zero-cheating condition. The decrease is not merely refusal,
non-submission, or changing the population-average denominator.

Generation-1 recipient cheating is 15/15 in four conditions, 12/15 beside Kimi and
14/15 beside Qwen Flash. At that point recipients have not received a peer's
generated output. This is baseline sampling imbalance, not an early peer
effect. The preregistration specified a descriptive balance check, not a
numeric balance threshold or an adjusted primary estimator.

The baseline and alternative-peer registered point-estimate thresholds hold; the near-zero-effect
falsifier does not fire. These statements are distinct from simultaneous
significance tests. Five independent chains per condition are few. In particular,
all-zero/all-one chain observations yield zero-width empirical bootstrap
intervals; they do not establish a zero/one population probability.

## Interpretation

The same recipient model sustains cheating with some peers and returns to
correct task completion with others. The result connects peer identity to
whether inherited misalignment continues: the peer's influence reaches beyond
its own submission to the agents that inherit the shared record.

Model assignment identifies the peer-model contrast, not the effect of any
particular generated message. Correct-solution and warning markers are
exploratory. Captured
hidden-test artifacts also appear in Kimi records, and cumulative merging
retains earlier exploit material; neither artifact presence nor disappearance
alone explains recipient behavior. No added message treatment was randomized.

## Scope and reproducibility

One underspecified solvable function, one initial method note and one
finite horizon were tested here. Model/provider snapshots, timing and baseline
imbalance limit generalization. Independent task/seed replications and more
chains are the next evidence needed. Raw transcripts remain local; public
sanitized outcomes enable numerical recomputation, not independent transcript
adjudication. The Kimi legacy delivery-check failure is retained and explained
separately; byte-level delivery checks pass for every final session.
