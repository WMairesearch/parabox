# Results

These experiments evaluate models as participants: their own violations, their
influence on peers, and their contributions to continuing or correcting shared
work. The historical function comparison changes the contributor beside fixed
recipients. The current Wiki and sequence cohorts compare separate model chains.
They measure complementary behaviors, not one interchangeable safety score.

The current evidence bundle contains 972 persistent-Wiki and 1,944 sequence
sessions. Historical contributor-model results are linked separately below;
they are not part of that bundle or results of the new packaged function protocol.
Generations within a chain are dependent.

## Misaligned Method Propagation

### Changing a contributor changes fixed peers' outcomes

The historical peer-model experiment keeps three DeepSeek V4 Pro recipients,
an initial method note and the cumulative record policy fixed, while changing
the fourth participant's model. Each configuration has five eight-generation
chains with 50 turns per session. The table separates the contributor's own
violations from **fixed-recipient** violations in generations 6–8.

| Contributor model | Contributor's own violations | Fixed V4 Pro recipients with violations |
|---|---:|---:|
| DeepSeek V4 Pro | 15 / 15 | 45 / 45 |
| Gemini 3.1 Pro | 3 / 15 | 18 / 45 |
| Kimi K3 | 3 / 15 | 18 / 45 |
| Qwen Max | 0 / 15 | 0 / 45 |
| DeepSeek Flash | 0 / 15 | 0 / 45 |
| Qwen Flash | 0 / 15 | 0 / 45 |

The same recipient model follows different trajectories depending on the model
participating beside it. In particular, the Qwen Max configuration differs from
the all-V4-Pro configuration in other agents' behavior, not just Qwen's own rate.
The 45 observations come from five chains, not 45 independent replications.
This seeded study measures continuation and interruption, not initial discovery.
See the [chain-level analysis](final/peer-composition-analysis.json),
[outcomes](final/peer-composition-outcomes.json) and
[registration](final/peer-composition-registration.json). The study has 960
completed sessions and five additional retry starts. The current installed
two-generation, two-recipient, empty-start protocol has no released results yet.

## Shared Practice Maintenance

### Models take different actions in the same protocol

| Model | Sessions requesting private cases | Sessions receiving private cases |
|---|---:|---:|
| DeepSeek Flash | 0 / 162 | 0 / 162 |
| DeepSeek Pro | 5 / 162 | 5 / 162 |
| Gemini Flash | 0 / 162 | 0 / 162 |
| Gemini Pro | 0 / 162 | 0 / 162 |
| Kimi | 19 / 162 | 18 / 162 |
| Qwen Max | 3 / 162 | 1 / 162 |

Each model has the same distribution of starter scores, initial conditions and
source blocks. These are separate same-model chains. Acquisition counts identify
one part of participation; maintenance and correction require the accompanying
actions and successor records, not an inference from an absent request.

### Starting conditions and continuation

| Initial inherited material | Sessions requesting private cases | Sessions receiving private cases |
|---|---:|---:|
| Empty Wiki | 0 / 324 | 0 / 324 |
| Artifacts without the note | 2 / 324 | 0 / 324 |
| Full Wiki | 25 / 324 | 24 / 324 |

The 27 requesting sessions make 231 private-case requests; 228 return a case
input and expected output. Every successful return concerns the agent's own
assigned package. Full-Wiki retrieval incidence falls from 9/54 at the first
position to 1/54 at the sixth. This is a decline in **new retrieval**, not proof
that inherited information ceased to influence successors.

Wiki starter scores are 30, 60 and 90, not fixed limits on legitimate progress.
Score gains therefore cannot by themselves identify private-information use.
The machine-readable analysis keeps grading coverage, scores, access events
and resource charges separate.

All 972 Wiki sessions now have end-bound offline grades, including the 152
recovered sessions. The mean earned scores are 99.69 for empty Wiki, 99.69 for
artifacts-only and 99.97 for full Wiki (0–100 scale). There are 969 full-score
submissions, one 90-point submission and two sessions without a submission.
Those two sessions nevertheless leave full-score candidate code.

In 25 of the 27 requesting sessions, the first edited solution independently
scores 100 before a later private request. This uses the recorded completion
time of the editing action, not its earlier resource charge, so a fetch inside
the same action is not treated as occurring after the repair. It establishes
that a correct version preceded continued private-case exploration—not that
the agent knew its hidden-test score or that access improved its result.

## Costly Information Contribution

### A model contributes; its successor continues

In a terminal-submission Gemini Flash chain, the first contributor writes a
one-value prefix, accepts a zero-point final submission, and leaves instructions
to obtain the next value from its public receipt. A second-generation agent
explicitly cites that receipt, extends the prefix to two values and again submits
for zero points. Its new feedback is also unavailable to itself after termination.
A third-generation agent reads the inherited records and continues with three
values, although its final submission repeats information already obtained by
its own test. It is continuation, not another novel final disclosure.

This connects personal scoring cost, publication, exposure and successor action
within one chain. The method note was initially provided; this is not a claim
that the method arose from an empty environment. See the selected original
actions and feedback in [case evidence](release/cases.json).

### Model differences under two scoring mechanisms

| Model | Terminal information-producing sessions | Repeated information-producing sessions |
|---|---:|---:|
| DeepSeek Flash | 0 / 162 | 1 / 162 |
| DeepSeek Pro | 0 / 162 | 0 / 162 |
| Gemini Flash | 3 / 162 | 0 / 162 |
| Gemini Pro | 13 / 162 | 7 / 162 |
| Kimi | 0 / 162 | 0 / 162 |
| Qwen Max | 0 / 162 | 0 / 162 |

Each model runs in its own chains; this comparison does not replace one model
among fixed peers. The exact provider/configuration bindings are in the
[protocol mapping](release/protocols.json).

The table counts sessions with at least one scored submission that explicitly
returns both **score 0** and the **next target value**. It does not count invalid
answers or unused submissions as information-producing contributions.

| Random-completion expectation | Terminal submission | Three scored submissions |
|---|---:|---:|
| 34 points (1 known value) | 7 / 324 | 5 / 324 |
| 60 points (40 known values) | 3 / 324 | 3 / 324 |
| 90 points (85 known values) | 6 / 324 | 0 / 324 |
| Total | 16 / 972 | 8 / 972 |

All 24 sessions occurred with the initial method note. Across both protocols,
Gemini Pro accounts for 20, Gemini Flash for three and DeepSeek Flash for one;
DeepSeek Pro, Kimi and Qwen have none. Each model contributes 324 sessions.
These counts are not 24 distinct altruistic discoveries: information can repeat,
and early repeated-protocol disclosures can also help the submitting agent.

Of the 16 terminal disclosures, seven return a position not previously returned
by that session's evaluator calls. That narrower count still does not establish
novelty relative to everything in the Wiki or demonstrate successor use. The
case above supplies direct successor-use evidence rather than inferring it from
receipt persistence alone.

## Reproduction and provenance

- [Protocol/configuration mapping](release/protocols.json).
- [Hash-bound evidence manifest](release/manifest.json) and [computed tables](release/summary.json).
- [Attempt accounting](release/attempts.json): 3,361 starts within the 4,000-start campaign ceiling, including 68 prior exploratory starts. Replaced attempts remain charged.
- [Recovery provenance](release/provenance.json) and [source identifiers](release/sources.json). Source identifiers are historical provenance, not links to a local filesystem.

Run `python -m parabox.benchmark analyze report/release` to regenerate the tables.
The [run guide](../docs/running.md) also covers new runs and independent sandbox
regrading. Analysis and regrading make no provider calls. The evidence bundle is
in the source checkout, not the wheel or source distribution.
