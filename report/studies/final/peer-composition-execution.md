# Peer composition execution

This reader-facing execution record is separate from the original registered
protocol. Its descriptive names do not alter the archived registration bytes.

## Launch

- User approved peer-composition design: three fixed V4 Pro recipients,
  one peer model, six conditions. No researcher-varying messages or recipes.
- Original time window expired before any peer composition model call. User explicitly
  extended execution by six hours at about 01:38 UTC on 2026-10-12.
- New start cutoff: 06:35 UTC; analysis/integration window ends about 07:38.
- Design/merge unit tests passed (18). The full container instrument
  selftest returned `ok=true`, no problems before launch.
- Six conditions started at about 01:40:35 UTC, concurrency 8 per condition.
- Registration, frozen configurations, full local requests/responses,
  submissions and audit evidence live under `runs/peer-composition/`.
- Initial instrument archive SHA-256:
  `92cdf92a53601075b079c207538bbc38115c85a6c2ad803662c8d24849890dcd`.

## Infrastructure retries

`scripts/peer_continue.py` reserves retry slots under a file lock before
calling the existing retry command. The conservative maximum is the 960
original planned starts plus all reserved retries, even if some reserved
starts never reach a model. The ledger is `runs/peer-composition/retry-budget.json`.
Original failed sessions remain in each condition's `retried/` directory.

- Gemini-peer condition: three generation-1 recipient sessions failed with two
  `IncompleteRead` errors and one `RemoteDisconnected`. Reserved and
  retried on 2026-10-12.
- DeepSeek-flash-peer condition: one generation-1 peer session failed with
  `RemoteDisconnected`. Reserved and retried; original records retained.
- Kimi-peer condition: one generation-5 recipient session failed at turn 9 with
  `IncompleteRead(0 bytes read)`. After the original process, audit and score
  finished, one retry was reserved and launched at about 02:58 UTC.

## Binary delivery-check limitation

Kimi's cumulative record contains participant-produced binary `.pyc` files.
The frozen legacy checker converts the lossy UTF-8 preview in `delivered.json`
back to bytes, then compares it with the original binary. It reports delivery
mismatches even though the byte-level `shared_sha256` agrees with the source
record. At the first Kimi stop, all 100 delivery digests matched; 12 previews
were lossy. No binary artifact or participant outcome was removed or changed.
The offline evidence validator checks the original byte digest and compares
the preview with the same documented decoding operation. It has a binary
regression test. Final reports must retain the legacy check failure and the
independent byte-level verification, not describe the legacy check as passing.

These are infrastructure retries, not replacement of normal unfavorable
outcomes. Total retry starts: five; all original failures are retained.

## Terminal evidence

The last normal subject session ended at `2026-10-12T03:39:04.210482+00:00`.
All six conditions completed 160 normal sessions, 960 total, with 965 starts
including retries. No planned cells remain missing and no final accepted
session has an unknown audit. Normal-session acceptance counts are V4 Pro
160, Gemini 160, Kimi 152, Qwen Max 145, DeepSeek Flash 154 and Qwen Flash 152.

Final independent evidence checks pass on all 960 sessions, including original
delivery digests. The legacy Kimi preview check remains a documented failure;
the other five legacy delivery checks pass. `runs/peer-composition/execution.json` records
the original orchestrator commands, not the later successful explicit retries.
`report/final/peer-composition-verification.json` records the final evidence check.

Every registered source file still matched its initial hash through completion.
Raw submission/audit counts independently matched the late endpoint and
generation curves in the exported outcomes. Offline recomputation reproduced
`peer-composition-analysis.json` byte-for-byte. The manuscript reports the imperfect
generation-1 balance and does not interpret it as a peer effect.

## Analysis and release tooling

No subject task, model assignment, planted message, generation rule or
turn budget was changed during subject execution. New offline analysis/evidence tools,
documentation and packaging work are release changes, not changes to the
running instrument. Do not represent the final release commit as the exact
unmodified source used at registration; the source archive identifies that.

Record-text markers are exploratory: literal hook strings, `return None`,
and warning words near a hook. The seed itself contains hook strings; a
marker is not endorsement, an honest function, or a causal mediator.
The primary endpoint and independent-chain bootstrap follow the protocol.

After all subjects and audits had terminated, release code was hardened with
descriptor-relative artifact access, bounded regular-file snapshots and safe
hidden-test/cache cleanup. Regression tests cover task entry points and
symlink/FIFO attacks. These changes were not active in peer composition and do not retrofit
its raw evidence. New runs must register the release code and its limits;
historical results remain tied to the initial archived instrument.
The release unified checker also uses original-byte delivery digests instead
of round-tripping binary previews. Its new result must not replace the frozen
checker's original Kimi failure log.
