# Architecture

A session gives one model a task, a fresh container and a bounded tool loop.
A study determines which sessions meet through shared artifacts. This
separation lets Parabox compare model compositions and communication policies
without treating every inherited message as an assigned intervention.

## Components

| Package | Contract |
|---|---|
| `parabox.model` | Provider requests on the host; credentials stay outside participant containers |
| `parabox.sandbox`, `parabox.workspace` | Container execution and bounded, confined artifact access |
| `parabox.tasks` | Task files, operational instructions, tools and task-specific grading |
| `parabox.session` | Standard tool loop and native request, response and submission evidence |
| `parabox.execution` | Start admission, generation barriers, runtime adapters and handoff policies |
| `parabox.benchmark` | Fixed development plan, frozen materials, authorized execution and grading |
| `parabox.studies.unified` | Custom Python single-session, chain and population designs |
| `parabox.records` | Read-only import and inspection of saved benchmark evidence |

The standard `Task` interface works with `SessionState` and `run_session`.
The wiki has a separate runtime because tool charges and terminal submission
are part of its task. Both can return an `Outcome` through an execution engine.
The engine owns execution; the orchestrator owns scheduling and transport.

## Two kinds of shared state

The core population record is cumulative. Each generation starts from the same
prior record; new files are added, modified versions are retained separately,
and deletions do not erase earlier material. The default includes every author.
Custom acceptance-selected merging uses the author's last verifier result,
not the independent audit.

The wiki is mutable. A successor receives actual exported files, so edits and
deletions affect the next workspace. The default removes an unchanged original
founder note at the handoff, but retains a rewritten note. Unified chains also
copy final directory state rather than applying cumulative population merging.
These policies make different claims about what can persist or be corrected.

## Design, execution and evidence

Preparation binds assignments, prompts, task bytes, source records, model
configurations and implementation hashes. Execution additionally requires an
authorized cap, deadline and verified local image. Host grading is a later
operation; task-verifier acceptance is not its substitute.

Saved records preserve native outcomes, resources and handoff evidence with
source hashes. The public importer currently supports benchmark execution
directories. Historical study modules keep their own evidence formats and
protocols; sharing implementation code does not make their designs equivalent.
Some older board studies use overlapping sessions rather than generation
barriers.

See [shared work](shared-work.md) for the fixed design and
[adding a task](adding-a-task.md) for extension contracts. Changes to a frozen
experiment require a new design and run, not replacement of its recorded inputs.
