# Historical studies

These explorations underpin Parabox's three model-behavior modules: Misaligned
Method Propagation, Shared Practice Maintenance, and Costly Information
Contribution. They are available in a source checkout. Start with [the current experiment designs](../../docs/experiments.md)
if you want to run the released benchmark. Historical schedules, tasks, scoring,
and model configurations are recorded per study.

## How the experiments developed

| Model-behavior question | Study code | Comparison or observation |
|---|---|---|
| Does changing a contributor change other models' violations? | [`unified/`](unified/), [`population/`](population/), [`scripts/peer_composition.py`](scripts/peer_composition.py) | Fixed-recipient contributor-model comparisons and population compositions; keep each historical schedule distinct. |
| Which models adopt and pass on a method? | [`relay/`](relay/), [`relay_board/`](relay_board/), [`relay_files/`](relay_files/), [`relay_search/`](relay_search/) | Independent and connected work through static or agent-updated channels. |
| Which models discover, act on and publish peer work? | [`discovery/`](discovery/), [`discovery_code/`](discovery_code/), [`write/`](write/), [`write_code/`](write_code/) | Trace discovery, execution and publication as successive actions. |
| Do model behaviors persist across task conditions? | [`mechspan_code/`](mechspan_code/), [`composition/`](composition/), [`spillover/`](spillover/) | Compare model behavior across task solvability, verifier design, feedback and supplied notes. |
| Which models continue or interrupt inherited practices? | [`transmission/`](transmission/), [`transmission_door/`](transmission_door/), [`board/`](board/), [`continuation/`](continuation/), [`shared_wiki/`](shared_wiki/) | Successive actions, corrections, private access and Wiki maintenance; some historical protocols also assigned warnings or withdrew records. |
| Which models contribute at a personal scoring cost? | [`costly_information/`](costly_information/) | Short scored submissions disclose hidden ternary values for successors. |

The central distinction is a model's own behavior versus its influence on peers
and successors. Publication, delivery and adoption records trace that influence;
shared files carry participants' work. Each study specifies the participating
models, assigned conditions and observed actions.

## Protocol lineage and release mapping

The table maps historical study configurations to the installed benchmark.

| Experiment | Study configuration | Installed configuration |
|---|---|---|
| Misaligned Method Propagation | Three fixed DeepSeek V4 Pro recipients and one contributor, eight generations, five chains per contributor model, an initial method note | Two fixed-reference recipients and one contributor, two generations, empty initial record; isolated and cumulative populations |
| Shared Practice Maintenance | Wiki studies include a founder-note withdrawal protocol and a persistent-Wiki protocol | The published profile runs the persistent protocol: six positions, three starter scores, three initial conditions and three source blocks per model |
| Costly Information Contribution | Terminal and repeated-scoring sequence chains, with one or four agents per generation | Both protocols are supported; `historical-v1` preserves the published target and ordering profile, while the generated profile supports new targets |

### Function comparison

The fixed-recipient comparison has 960 completed sessions and five additional
retry starts. Its results belong to the eight-generation seeded configuration,
with three fixed recipients. The installed suite uses two generations and two
fixed recipients, and also includes a two-position Wiki component. Its participant
results are pending. Seeded-method study commands run from a source checkout.

### Wiki protocols

The withdrawal protocol removes the unchanged original founder note after the
first recipient. The persistent protocol passes agents' actual Wiki edits and
deletions to successors. Cohort labels identify the protocol for each maintenance
and cleanup trace. Frozen participant surfaces record the prompts used in each run.

The persistent release contains 972 sessions. Its participant surfaces, founder
file hashes and 36 six-model wave orders are checked against the published
profile in [Wiki mapping](../../report/release/wiki-mapping.json).
The study runner used concurrent model pipelines and per-session deadlines;
the installed runner uses a serial wave loop with an overall deadline.
The two-position development profile remains available separately.

### Sequence profiles and recovery

The repeated-submission protocol remains the default when a protocol value is
omitted. Both terminal and repeated protocols have published-profile templates;
the original generated-target profile remains available for new runs.
Published-profile templates retain `historical` in their filenames for
compatibility.

Final Kimi/Qwen recovery used streaming. The installed `json-900-v1` profile
records JSON transport and its retry policy instead. Target, ordering and transport settings are recorded separately.
[Protocol mapping](../../report/release/protocols.json),
[recovery provenance](../../report/release/provenance.json) and
[attempt accounting](../../report/release/attempts.json) retain these distinctions.

## Evidence and scope

Start with the [fixed-recipient model comparison](../../report/results.md#misaligned-method-propagation):
changing the contributor changes later violations among the same recipient model.
Its original [registration](../../report/final/peer-composition-registration.json)
and [chain-level analysis](../../report/final/peer-composition-analysis.json) are
retained alongside other summary tables in [`report/final/`](../../report/final/),
[`report/longchain/`](../../report/longchain/),
[`report/composition/`](../../report/composition/),
[`report/mechspan/`](../../report/mechspan/), and
[`report/population/`](../../report/population/). The shared-test-wiki analyses
are in [`report/shared-test-wiki/`](../../report/shared-test-wiki/); resource
measurements are in [`report/resource-allocation/`](../../report/resource-allocation/).
These summaries document the study configurations listed above.
The [current results page](../../report/results.md) states what has been released
for the integrated protocols.

Study code depends on the common task and execution modules, never the other
way around. Only a limited [study smoke suite](tests/test_smoke.py) is maintained
here. Reproducing a historical comparison requires its original specification,
model configuration, image, and run artifacts alongside the published CSVs. Do not start paid model sessions while exploring this code.
