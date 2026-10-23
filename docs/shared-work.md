# Shared-work development suite

The default suite connects two questions: how a contributor changes other
agents' conduct, and how inherited work changes recipients' actions and
spending. It combines function-task populations with a mutable shared wiki.
The complete default has no reported hosted-model results; earlier
[function studies](../report/studies/final/protocol.md) and
[wiki studies](../report/shared-test-wiki/README.md) retain their own designs.

## Fixed comparisons

| Component | Assignment | Sessions |
|---|---|---|
| Function tasks | Two reference-model recipients and one candidate or reference contributor; isolated versus cumulative records | 36 per candidate plus 36 reused reference sessions |
| Wiki | Candidate recipients receive an empty wiki or a founder checkpoint, then pass their exported wiki to one successor | 36 per candidate |

For `N` candidates the plan contains **36 + 72N sessions**: 108 for one
candidate or 324 for four. Reference participants are reused across candidate
contrasts, and wiki source blocks are shared dependencies.

Function populations cross three tasks, two history policies, two generations
and three seats. `reverse_words` and `second_item` have valid solutions; this
version specifies the short-list answer for `second_item`. `double` supplies
contradictory evaluation cases as an impossible-task diagnostic. Every session
has an open verifier, 50 turns and at most eight submissions.

Wiki sessions cross three initial scores (30%, 60%, 90%), three source blocks,
two exposure conditions and two positions. The assigned budget is 20 charged
units and at most 40 model turns; qualification starts at 60%. The task's
separate base runtime uses 60 units, not the default suite's budget.

This is a development comparison, not a held-out ranking. Changing its tasks
or schedules requires a separately versioned design.

## Handoff rules

In the cumulative core condition, each generation receives the same prior
record. All authors' additions are retained, modifications become extra
versions, and deletions leave previous versions intact. The isolated condition
delivers no inherited files.

Wiki transport preserves the predecessor's actual edits and deletions, including
unchanged founder notes. No researcher withdrawal occurs by default. Source bytes and provenance come from the
packaged `parabox/benchmark/assets/wiki-founders.json`, without a private
checkout dependency.

For the original withdrawal rule, pass `--historical` to `default-spec` and
prepare a separate directory. That option removes an unchanged original founder
`NOTES.md` at the successor handoff; a rewritten note remains. Historical JSON
specifications remain supported. Existing prepared runs remain tied to their
recorded source hashes; use their original revision rather than bypassing checks.

The [Shared Wiki protocol](../report/protocols/shared-wiki.md) and
[standalone study commands](information-studies.md) provide the full six-position
matrix separately from this shorter integrated development suite.

The resulting trajectories can include relay, divergence and active correction.
Resource allocation is an outcome in its own right: effort spent retrieving,
testing or publishing shared material matters even when earned reward stays
unchanged. Trace review connects that effort to concrete successor actions.

## Prepare, run and grade

Install and build the image using [getting started](getting-started.md).
Create private candidate and reference configurations using environment-based
credentials, then prepare a fresh directory:

```sh
IMAGE_ID="$(podman image inspect localhost/parabox-code:py312 --format '{{.Id}}')"
IMAGE_ID="sha256:${IMAGE_ID#sha256:}"
python -m parabox.benchmark default-spec \
  --candidate candidate=candidate.json --reference reference.json \
  --image "$IMAGE_ID" > suite.json
python -m parabox.benchmark prepare runs/shared-work --spec suite.json
python -m parabox.benchmark check runs/shared-work
```

Preparation freezes assignments, operational surfaces, source artifacts,
configuration hashes and implementation bindings. Neither preparation nor
checking contacts providers or starts containers.

For this one-candidate plan, explicitly authorize 108 starts and set `DEADLINE`
to a future timezone-aware timestamp:

```sh
python -m parabox.benchmark run runs/shared-work \
  --authorize-session-cap 108 --deadline "$DEADLINE"
python -m parabox.benchmark grade runs/shared-work
```

Only `run` makes participant model calls. It verifies the image, follows
generation barriers and blocks descendants of failed exports. There is no
automatic retry or resume. The core deadline checks before and after each
provider call, but cannot interrupt a request already in flight.

`grade` uses the registered image in offline containers. It audits accepted
function submissions and evaluates archived wiki code, saving session records
and `execution/grading.json`. Acceptance, code score, earned reward and
qualification remain separate fields; unresolved grading stays unavailable.

## Inspect saved execution

```sh
python -m parabox.records import runs/shared-work \
  --output runs/shared-work-records.json
python -m parabox.records check runs/shared-work-records.json \
  --root runs/shared-work
python -m parabox.records summary runs/shared-work-records.json \
  --root runs/shared-work
```

These commands read saved evidence only. They preserve unstarted seats,
native resource units, planned versus recorded handoffs and source hashes.
The public importer supports benchmark execution directories, not every
historical format. See [reproducibility](reproducibility.md) for endpoint
definitions and [release validation](../report/release-validation.md) for
checks of the implementation.
