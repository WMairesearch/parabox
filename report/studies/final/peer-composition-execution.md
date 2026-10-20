# Execution provenance for the fixed-recipient comparison

This editorial reconstruction separates historical execution evidence from the rewritten scientific account. The original registration and instrument archive remain the source of execution identity.

## Authorized launch

The approved comparison fixed three V4 Pro recipients and varied one contributor across six model configurations, without researcher-varying messages. After the original window expired with no participant calls, execution was extended by six hours at about 2026-10-12 01:38 UTC. The revised start cutoff was 06:35 UTC, with analysis/integration through about 07:38 UTC.

Before launch, 18 design/merge tests passed and the full container selftest returned `ok=true` with no problems. All six conditions began at about 01:40:35 UTC, concurrency 8 each. Registration, configurations, requests/responses, submissions and audits were retained under `runs/peer-composition/`. The initial instrument archive hash was `92cdf92a53601075b079c207538bbc38115c85a6c2ad803662c8d24849890dcd`.

## Retry accounting

The file-locked reservation in `scripts/peer_continue.py` preceded the existing retry command. `runs/peer-composition/retry-budget.json` counted 960 planned starts plus every reserved retry, including a reservation that might not reach a provider. Failed originals stayed in condition-specific `retried/` directories.

Five infrastructure retries were recorded on 2026-10-12:
- Three generation-1 recipients in the Gemini-contributor condition failed with two `IncompleteRead` errors and one `RemoteDisconnected`.
- One generation-1 DeepSeek Flash contributor failed with `RemoteDisconnected`.
- One generation-5 recipient in the Kimi-contributor condition failed at turn 9 with `IncompleteRead(0 bytes read)`. Its retry was reserved around 02:58 UTC after the preceding process, audit and score completed.

None replaced a normal unfavorable behavioral outcome.

## Binary delivery discrepancy

Kimi records included participant-produced `.pyc` files. The frozen legacy checker round-tripped lossy UTF-8 previews in `delivered.json` and therefore reported mismatches despite matching original-byte `shared_sha256` values. At the first Kimi stop, all 100 delivery digests agreed and 12 previews were lossy.

The offline validator instead checked original bytes and the documented preview decoding, with a binary regression test. It did not remove artifacts or alter outcomes. The historical Kimi legacy-check failure remains part of the record; byte-level verification is a separate successful check, not a retrospective pass for the old checker.

## Terminal evidence and recomputation

The last normal participant ended at `2026-10-12T03:39:04.210482+00:00`. Every condition completed 160 normal sessions, totaling 960, with 965 starts including retries. No planned outcome remained missing, and every accepted session had a known audit. Normal-session acceptance totals by contributor were V4 Pro 160, Gemini 160, Kimi 152, Qwen Max 145, DeepSeek Flash 154 and Qwen Flash 152.

Independent evidence checks passed for all 960 final sessions and their original delivery digests. Five legacy delivery checks passed; Kimi's preview failure remained. `runs/peer-composition/execution.json` preserves the original orchestration commands rather than the later explicit retries; `report/final/peer-composition-verification.json` records the final verification.

Registered source hashes matched through completion. Submission/audit records reproduced the late endpoint and generation curves, and offline recomputation reproduced `peer-composition-analysis.json` byte for byte. Generation-1 imbalance is retained as sampling imbalance before peer-output delivery, not attributed to the assigned contributor's yet-unseen output.

## Release changes versus historical execution

No participant task, model assignment, planted message, generation rule or turn limit changed during calls. Offline analysis, evidence checks and release packaging were developed separately. The release commit must not be substituted for the archived execution source.

After participants and audits finished, release code added descriptor-relative artifact access, bounded regular-file snapshots and safer hidden-test/cache cleanup, with task-entry, symlink and FIFO regression tests. Those improvements were not active in this study. The release checker also adopted original-byte delivery comparison; its output does not erase the frozen Kimi failure log.

Record-text markers—hook strings, `return None` and nearby warning terms—remain exploratory. The seed can supply a hook string, and a marker alone is neither a correct implementation nor demonstrated mediation.
