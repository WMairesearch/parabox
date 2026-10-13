# Architecture

The reusable unit is a **session**: one model conversation, one fresh
offline container, and a fixed sequence of tool opportunities. A study
connects sessions by copying or merging artifacts at generation barriers.

| Layer | Modules | Responsibility |
|---|---|---|
| Providers | `parabox/model/` | Host-side API requests; credentials do not enter participant containers |
| Execution | `parabox/session.py`, `parabox/sandbox.py` | Workspace preparation, request/response evidence, tool loop, container lifecycle |
| Tasks | `parabox/tasks/base.py`, `parabox/tasks/code/`, `parabox/tasks/lean/` | Problem files, tools, participant verifier and independent research audit |
| Studies | `parabox/studies/unified/` | Assignment, frozen protocol, generation barriers, run/audit/check/score |
| Transmission | `parabox/studies/population/merge.py` | Deterministic artifact admission, collision handling and cumulative record |
| Artifacts | `parabox/workspace.py` | Confined descriptor-relative reads/writes, bounded snapshots, safe cleanup |
| Analysis | `parabox/analysis.py`, `parabox/evidence.py`, study scorers | Outcome extraction, evidence completeness and independent-chain uncertainty |

## Interfaces and boundaries

`Task` in `tasks/base.py` defines workspace, prompts, tools, calls,
contributions and audits. `SessionState` holds tool-visible execution state.
`run_session` records requests before calls and snapshots accepted/rejected
submissions through the task. The research audit is never shown to agents.

`unified.design.design` creates deterministic schedules for single sessions,
chains and populations. `prepare` records these schedules and frozen
configuration. `run` checks that the frozen inputs still match, then executes
sessions. `audit`, `check` and `score` are separate steps; scoring alone is
not evidence that audits exist or that the run completed.

Population merge starts with the prior record. It admits new files and
stores modified versions separately; deletions are ignored. Selection uses
the author's last submission acceptance, not the independent audit. Chain
inheritance instead copies the entire final directory including deletions.
These are different experimental interventions.

## Supported versus historical studies

The unified instrument is the entry point for new controlled file-channel
studies. Older `relay*`, `discovery*`, `transmission*`, `composition`, and
other modules retain their commands and experimental designs for reproduction.
They are not interchangeable instruments; their protocols define their scope.
Code reuse across tracks does not imply identical prompts or verifier gates.
Post-peer composition shared safety helpers change handling of symlinks, special files and
oversized artifacts. Use the frozen source archive for exact historical
instrument bytes, in an isolated environment; do not assume the release tree
is byte-identical to the earlier running code. Historical track-specific
orchestration and scorers have a narrower review status than the supported
unified path; see `SECURITY.md`.

## Extension discipline

Add a task through the task interface, a model through provider configuration,
and a treatment through an explicit study design. Test assignment, delivery,
acceptance, independent audit and outcome extraction. A new gate must accept
its intended fixture and reject other gates' fixtures. Never modify a frozen
run to accommodate a new implementation: create a new run and protocol.
