# Resource allocation during method transmission

Inherited methods change how agents spend actions on their own task, what the verifier accepts, and what they leave for successors. This report connects those observations without treating resource savings as legitimate success or additional work as harmful by definition.

## Evidence and units

The numeric export contains 992 archived sessions: 192 independent method-exposure sessions and 800 sessions nested in 100 eight-generation chains. A separate 720-session view follows three fixed recipients in each generation of 30 eight-generation peer-composition chains. The contributing model varies; the recipient model stays DeepSeek V4 Pro.

All resource budgets here are native model turns. Means displayed to two decimals use half-up rounding. They are not the shared-wiki service's charged operation units, monetary costs, or successful operations. Command and submission dispatches count selected actions. Feature counts describe overlapping activity signatures, not intentions.

## One encounter: expenditure and violating methods

The exposure study uses contradictory functions, 16 sessions per condition and model, and a 24-turn ceiling. It measures shortcut susceptibility, not success on a genuinely solvable task.

| Model | Condition | Sessions | Mean turns | Sessions with acceptance | Sessions with recorded violation |
| --- | --- | ---: | ---: | ---: | ---: |
| deepseek-flash | method-exposure | 16 | 13.63 | 0 | 0 |
| deepseek-flash | no-method | 16 | 18.00 | 0 | 0 |
| deepseek-v4-pro | method-exposure | 16 | 16.69 | 12 | 12 |
| deepseek-v4-pro | no-method | 16 | 23.63 | 2 | 2 |
| gemini-3.1-pro-preview | method-exposure | 16 | 21.19 | 6 | 6 |
| gemini-3.1-pro-preview | no-method | 16 | 23.88 | 1 | 1 |
| kimi-k3 | method-exposure | 16 | 20.94 | 8 | 8 |
| kimi-k3 | no-method | 16 | 22.81 | 0 | 0 |
| qwen3.8-flash | method-exposure | 16 | 16.19 | 0 | 0 |
| qwen3.8-flash | no-method | 16 | 17.00 | 0 | 0 |
| qwen3.8-max | method-exposure | 16 | 16.50 | 0 | 0 |
| qwen3.8-max | no-method | 16 | 20.13 | 0 | 0 |

Exposure reduces average turns for every included model, but audited violations rise only for some. DeepSeek V4 Pro moves from 2 to 12 recorded violations while mean turns fall from 23.63 to 16.69. Savings and misalignment are therefore distinct outcomes.

## Eight generations: task outcomes and continued allocation

Each condition below contains ten independent chains, eight generations, and a 50-turn ceiling. The code task has a successful reference implementation, while its original short-list convention is not fully stated to participants. Acceptance is the participant verifier's decision; recorded violations indicate accepted submissions that failed the saved independent audit.

| Model | Condition | Sessions / chains | Mean turns | Sessions with acceptance | Sessions with recorded violation | Mean command dispatches | Mean submit dispatches |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| deepseek-flash | method-exposure | 80 / 10 | 23.98 | 70 | 0 | 5.96 | 2.19 |
| deepseek-flash | no-method | 80 / 10 | 24.73 | 76 | 0 | 6.68 | 1.95 |
| deepseek-v4-pro | method-exposure | 80 / 10 | 22.28 | 79 | 66 | 3.88 | 2.45 |
| deepseek-v4-pro | no-method | 80 / 10 | 40.28 | 41 | 0 | 18.43 | 4.04 |
| gemini-3.1-pro-preview | method-exposure | 80 / 10 | 18.10 | 80 | 15 | 5.78 | 2.63 |
| gemini-3.1-pro-preview | no-method | 80 / 10 | 18.91 | 77 | 11 | 6.68 | 3.09 |
| gemini-3.8-flash | method-exposure | 80 / 10 | 33.69 | 54 | 0 | 16.40 | 2.61 |
| gemini-3.8-flash | no-method | 80 / 10 | 46.73 | 14 | 0 | 32.36 | 1.98 |
| kimi-k3 | method-exposure | 80 / 10 | 27.48 | 39 | 17 | 6.69 | 2.86 |
| kimi-k3 | no-method | 80 / 10 | 24.23 | 63 | 0 | 6.46 | 2.78 |

Three patterns coexist. DeepSeek V4 Pro's method condition combines fewer actions with more acceptance and violations. Gemini Flash improves acceptance and uses fewer turns without recorded violations. Kimi spends more turns while acceptance falls and violations appear. Resource accounting locates these different paths through the same task rather than collapsing them into a safety score.

Within method-exposed chains, DeepSeek V4 Pro's mean falls from 31.1 turns in generation one to 20.4 in generation eight; Gemini Flash moves from 50.0 to 21.0. These are descriptive trajectories within dependent chains. Carried material can include the original note: later recurrence is not automatically a newly authored transmission or an isolated causal effect of generation.

## Fixed recipients: from task work to contributions

The next table preserves the contributing-model comparison. Each setting has five independent chains; the first window contains 15 recipient sessions and the late window 45. Counts are summed dispatch signatures, except mean turns and the audit denominator. First-generation recipients have not yet received any generated peer outputs; differences in that first window are not responses to the contributing model's generated material.

| Contributing model | Window | Sessions | Mean turns | Own writes | Verifier writes | Tests | Shared writes | Post-acceptance nonterminal actions | Violating sessions / sessions with known audits |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deepseek-flash | first | 15 | 25.73 | 16 | 48 | 117 | 7 | 9 | 15 / 15 |
| deepseek-v4-pro | first | 15 | 26.47 | 17 | 41 | 111 | 8 | 10 | 15 / 15 |
| gemini-3.1-pro-preview | first | 15 | 25.67 | 18 | 32 | 117 | 5 | 8 | 15 / 15 |
| kimi-k3 | first | 15 | 27.47 | 21 | 51 | 91 | 8 | 9 | 12 / 15 |
| qwen3.8-flash | first | 15 | 25.27 | 18 | 30 | 87 | 3 | 4 | 14 / 14 |
| qwen3.8-max | first | 15 | 26.53 | 17 | 43 | 117 | 6 | 7 | 15 / 15 |
| deepseek-flash | late | 45 | 17.71 | 90 | 12 | 123 | 5 | 7 | 0 / 45 |
| deepseek-v4-pro | late | 45 | 21.00 | 47 | 79 | 164 | 16 | 17 | 45 / 45 |
| gemini-3.1-pro-preview | late | 45 | 20.49 | 72 | 45 | 138 | 15 | 16 | 18 / 45 |
| kimi-k3 | late | 45 | 19.84 | 72 | 68 | 122 | 12 | 14 | 18 / 45 |
| qwen3.8-flash | late | 45 | 18.13 | 91 | 1 | 121 | 9 | 10 | 0 / 45 |
| qwen3.8-max | late | 45 | 17.51 | 91 | 11 | 109 | 16 | 20 | 0 / 45 |

Under Flash and Qwen contributors, late recipients allocate more actions to their own implementation and fewer to the verifier surface than under the V4 Pro contributor. Verifier writes can include repairs or removal of a bypass; their direction is interpreted alongside the saved audits, not from the write count alone.

Post-acceptance nonterminal actions show that activity continues after obtaining acceptance. Shared writes provide a route for later agents to encounter methods or corrections. These counts do not identify which advice was endorsed or used: those questions require the separate publication and lineage evidence. These allocations describe participation in shared work alongside own-task completion.

## Provenance and reproduction

The CSVs are allowlisted numeric projections of saved research censuses, not newly executed audits. They contain pseudonymous episode/chain IDs, original source-array indices and canonical source-row digests. Snapshot digests are retained in `provenance.json`; original snapshots and raw traces are not distributed here. Public reproduction verifies the shipped projections and reconstructs every aggregate, not the unavailable raw judgments.

All 992 selected archived traces reconcile. One session has incomplete argument coverage; its argument-derived counts remain empty rather than zero. The peer view contains 19 sessions without accepted submissions; their saved audit flags remain null, not missing required audits or audit-clean successes. Published archive violation flags and peer audit flags retain their distinct definitions; they are never pooled.

From the repository root:

```sh
python scripts/resource_report.py --check
python scripts/resource_report.py --output-dir /tmp/resource-report
```

The check verifies CSV digests and regenerates `summary.json` and this report byte-for-byte. A fresh output directory receives regenerated aggregates and prose; existing outputs are not overwritten. No model, tool, or grader is executed.
