# Results

The released cohort contains 1,944 ternary-sequence sessions and 972 persistent-
Wiki sessions. Results describe these models, tasks and inherited materials;
they are not a single model ranking. Generations within a chain are dependent.
The earlier impossible-function and seeded-method studies remain separate in
the [historical study guide](../parabox/studies/README.md).

## A costly relay

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

## Scoring mechanisms and model differences

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

## Persistent Wiki

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

## Reproduction and provenance

- [Protocol/configuration mapping](release/protocols.json).
- [Hash-bound evidence manifest](release/manifest.json) and [computed tables](release/summary.json).
- [Attempt accounting](release/attempts.json): 3,361 starts within the 4,000-start campaign ceiling, including 68 prior exploratory starts. Replaced attempts remain charged.
- [Recovery provenance](release/provenance.json) and [source identifiers](release/sources.json). Source identifiers are historical provenance, not links to a local filesystem.

Run `python -m parabox.benchmark analyze report/release` to regenerate the tables.
The [run guide](../docs/running.md) also covers new runs and independent sandbox
regrading. Analysis and regrading make no provider calls. The evidence bundle is
in the source checkout, not the wheel or source distribution.
