# Release integration record

This record describes the 2026-10-20 validation of the 0.2.0 candidate.
It answers whether the packaged components can prepare, execute, grade and
record experiments together. Scientific findings are documented in the
[research report](README.md); these integration runs have a separate purpose.

## Paths exercised

| Layer | Recorded check |
|---|---|
| Python compatibility | On both Python 3.12 and 3.13: 524 tests collected, 519 passed, five optional skips |
| Container execution | 22 image-enabled integration tests passed |
| Participant interface | Golden checks cover operational text, tools, fixtures and founder bytes |
| Wiki evaluator | Twelve fixtures cover three packages at 30%, 60%, 90% and 100%, with the expected scores |
| End-to-end default plan | 108 scripted sessions executed in real containers; all 108 graded and imported into source-verified records |
| Provider integration | 24 wiki sessions and six function sessions using Gemini 3.8 Flash and Kimi K3 |
| Installed wheel | Preparation and source verification outside the checkout, plus a scripted wiki service/export/grading run |
| Published artifacts | Wiki arithmetic, generated presentation tables and compilation of both deck entrypoints |

The scripted runs exercise execution without provider calls. Hosted-model runs
check the same interfaces against model outputs.

## What the model checks produced

The wiki check consists of twelve two-session chains, covering empty/full
wiki inputs and the three initial scores. Founder block and initial score
are coupled in this small configuration. All 24 participants submit code
scoring 100/100; one makes ten logged private-case requests, each returning
a case.

The function check is a single two-generation chain with three seats per
generation on `reverse_words`. All six accepted submissions pass the
independent execution audit.

These runs demonstrate completed task, boundary-event and evidence paths.
Their allocation does not support a model ranking or an estimate of an
exposure effect, and they are not a complete hosted-model default-suite run.

## Corrections verified

Integration testing found two interpretation defects: a session's used turns
were compared to its assigned maximum as though they must be equal, and an
incomplete service log could be treated as a complete event count.
Regression tests now distinguish budget from usage and retain unknown counts
when logs cannot establish completeness.

Core artifact-delivery metadata was added for subsequent runs. The scripted
default plan exercises that path; earlier model sessions were left unchanged,
without reconstructed delivery records.

The [machine-readable record](release-validation.json) stores the check counts,
immutable image identity and hashes of locally retained evidence.
It is a dated validation snapshot, not a live count of tests after later
documentation or analysis changes. To repeat available checks, use
[getting started](../docs/getting-started.md) and
[reproducibility](../docs/reproducibility.md).
