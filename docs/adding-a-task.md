# Extending the task instrument

Keep the participant's job, the execution mechanism and the study assignment
separate. A task should state what can be done and how it is evaluated; the
study decides who receives whose artifacts.

## Standard tool-loop tasks

Implement `Task` from `parabox/tasks/base.py` under `parabox/tasks/`.

| Interface | Required behavior |
|---|---|
| `name`, `image`, `turns` | Identify the task, container image and turn allowance |
| `workspace(problem)` | Return initial workspace files as bytes |
| `system(...)`, `task(...)`, `tools(...)` | Describe the actual assignment, available tools and communication |
| `prompts_record(...)` | Expose the operational surfaces used in preparation |
| `call(box, name, args, state)` | Dispatch a tool and update `SessionState` |
| `contribution(state)` | Describe task contributions for the study's sharing rule |
| `audit(raw, problem, scratch)` | Evaluate an archived artifact independently of the participant |

An optional `audit_session` can evaluate the full session. The generic fallback
uses only the last accepted artifact, so studies measuring any earlier
accepted-invalid submission need a session-aware audit.

`run_session` places `extra_files` after task files. Define their allowed paths
and collision behavior deliberately. Container mounts belong to the caller;
cross-session selection and delivery belong to the study.

## Tasks with a different lifecycle

Terminal submission, metered services or other execution rules can use a
dedicated runtime, as the wiki does. Wrap it in an engine accepting
`(Invocation, incoming)` and returning `Outcome(end, files, accepted)`.
Declare supported handoff `policies`; acceptance is required only for
acceptance-selected merging.

Save the native terminal record and export bounded bytes after participant
execution stops. The common ledger handles admission and the orchestrator
handles barriers. Keep tool costs, shutdown behavior and grading inside the
task contract rather than changing global budgets.

## Verification checklist

- Test a legitimate solution, a rejection and any intended verifier weakness
  against the independent grader.
- Check exact delivered and exported bytes, modifications, deletions and
  unavailable predecessors.
- Exercise termination and infrastructure failure without assigning a false
  behavioral outcome.
- Record resource units explicitly and test missing grading as unknown.
- Use scripted fixtures for default tests; provider calls require a separate
  authorized experiment.

The fixed benchmark does not discover arbitrary tasks automatically. Introduce
a new versioned design when changing its task inventory or participant inputs.
