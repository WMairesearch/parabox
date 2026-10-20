# Evidence and reproducibility

A propagation result connects an inherited record to an agent's actions and
then to what later agents receive. Preserve that sequence alongside task
outcomes and resource use. Controlled exposure and model-composition contrasts
estimate different effects from descriptions of naturally occurring deletion
or correction.

## What can be reproduced

Published tables support offline recomputation. Scripted fixtures verify the
instrument without model calls. A new model experiment additionally needs
frozen assignments, prompts, configurations, task bytes, source records and
images; hosted providers need not return identical outputs on repetition.
The [validation record](../report/release-validation.md) distinguishes these
forms of evidence.

The two recent evidence bundles have standalone checks:

```sh
python -m scripts.wiki_report --check
python -m scripts.resource_report --check
```

Both verify the published inputs and reconstruct their summaries without
provider calls. The [resource report](../report/resource-allocation/README.md)
also records how native model turns differ from charged wiki operations.

## Saved evidence

| Workflow | Principal files |
|---|---|
| Default benchmark | `spec.json`, `plan.json`, `materials.json`, `manifest.json`, content-addressed artifacts |
| Benchmark execution | `execution/authorization.json`, start ledger, wave records, `execution/end.json`, `execution/sessions/` |
| Benchmark grading | Per-session `grading.json` and `execution/grading.json` |
| Unified studies | `protocol.json`, `plan.json`, session requests/responses, submission snapshots, delivery records, audits and population merges |

Assignments and observations have different meanings: core `meta/spec.json`
stores the turn allowance, while terminal `end.json` stores turns used.
Ledger admission or runner entry is not proof of a completed provider request.

`benchmark check` verifies prepared inputs. The
[records commands](shared-work.md#inspect-saved-execution) verify saved source
hashes and expose observations without running a grader. For unified and
supported historical layouts, `python -m parabox.evidence RUN_DIRECTORY`
checks assignment consistency, submissions, delivery and audit coverage,
returning a nonzero status for incomplete evidence.

Use original bytes for artifact hashes. Legacy delivery text may be a lossy
UTF-8 preview, not a reconstructable binary artifact. A commit identifier with
uncommitted changes also needs the recorded source hashes or instrument archive.

## Read outcomes at their native level

**Function tasks.** An accepted-invalid event requires both verifier acceptance
and independent rejection. A later clean submission does not erase an earlier
event. A confirmed event remains confirmed if another audit fails; report that
incomplete coverage separately. In the unified scorer, truncation means no
`finish` before the budget and can coexist with acceptance. Its refusal label
is a lexical proxy, while `read_note` records shared-file access, including a
control notice.

**Wiki tasks.** Keep code score, earned reward, qualification and terminal
submission distinct. Authorized source collection and unauthorized recipient
access are different roles. Count attempts, successful retrieval, publication,
retention, reading and execution separately.

**Shared work.** Resource allocation reveals what agents do with their available
effort, including probing, testing, helping and maintaining records. These
actions are informative even without a reward loss. A claim of deliberate
sacrifice requires additional evidence of an attainable opportunity forgone.
Likewise, a corrective publication is a contribution, not automatically a
verified repair or proof that a successor followed it.

## Denominators and uncertainty

Keep missing sessions and unavailable audits visible rather than turning them
into clean outcomes. The unified analysis distinguishes known-case rates,
all-session bounds and `chain_mean` for complete known chains.
Resample independent chains while retaining their generations and seats.
Reused controls and founder blocks remain shared dependencies; matching numeric
IDs alone does not pair independently generated histories.

Historical CSV files can contain multiple sections with different headers.
Parse them separately. `python -m scripts.dependent_outcomes` recomputes the
[dependence-aware analysis](../report/studies/final/dependent-outcomes.md)
without replacing the original tables.

## Interrupted work and public evidence

The benchmark does not resume or retry; blocked descendants remain unavailable.
Unified `parabox-eval retry RUN_DIRECTORY` preserves interrupted attempts
before restarting them, and those additional starts count toward the budget.
Do not rerun normal participants to fill missing delivery records. Recover
original evidence instead. Unified `audit` can retry unresolved audits while
retaining prior records.

Raw historical transcripts are not included in this release. `runs/` remains
local and ignored; published path references describe provenance, not a public
download service. The [report inventory](../report/README.md) identifies
distributed evidence. Preserve originals when redacting or converting data,
and review model-output rights separately from the code license.
