# Run and extend

Use Python 3.12+ and Linux with rootless Podman for participant execution.
Provider credentials stay on the host in environment variables; never put them
in model configuration JSON or mount them into a container. The example model
file is a template, not a working provider account.

Choose one runner before preparing a run: [ternary sequence](#ternary-sequence-experiment)
for costly information contribution, or [function tasks](#function-task-development-suite)
for misaligned method propagation. Their specifications and session caps are not
interchangeable.

## Install and check

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
podman build -t localhost/parabox-code:py312 parabox/tasks/code/image
IMAGE_ID="$(podman image inspect localhost/parabox-code:py312 --format '{{.Id}}')"
IMAGE_ID="sha256:${IMAGE_ID#sha256:}"
```

The selftest is offline. Image building may download dependencies. Record the
immutable image ID for the actual run.

## Provider configuration

For the Responses adapter, copy
[`examples/model.openai-responses.example.json`](../examples/model.openai-responses.example.json)
to a private model configuration and set `OPENAI_API_KEY` on the host.
Its `wire: "responses"` selects the Responses transport; `request_body`
configures reasoning effort and the output-token allowance. Other configurations
retain Chat Completions by default or select Gemini with `wire: "gemini"`.

The Responses adapter replays only the current session's history, including
native reasoning and function-call items, without a shared conversation ID.
Native items are retained as `responses_output` on assistant messages in
`meta/requests/`; unmodified provider responses, including usage, remain in
`meta/responses/`. Tool declarations preserve optional parameters by retaining
non-strict behavior unless the task explicitly requests strict mode.

## Ternary sequence experiment

Copy `examples/ternary.example.json` to a private spec. Replace its image ID
with `$IMAGE_ID` and its model path with a provider configuration based on
`examples/model.example.json`. Keep credentials in the named environment
variable. Preparation fixes one target and schedules all named models against
it; it makes no model calls.

```sh
.venv/bin/python -m parabox.benchmark.ternary prepare runs/ternary --spec private-ternary.json
.venv/bin/python -m parabox.benchmark.ternary check runs/ternary
```

For one model, `seats: 1` plans 18 sessions (three prefixes × six
generations); `seats: 4` plans 144 sessions (three prefixes × two conditions ×
six generations × four seats). With multiple models, multiply by their count.
Use the exact `session_cap` printed by `prepare` and a future timezone-aware
deadline. Only `run` makes provider calls:

```sh
.venv/bin/python -m parabox.benchmark.ternary run runs/ternary \
  --authorize-session-cap 144 --deadline "$DEADLINE"
```

Replace the example cap and deadline with the values for your run. Outputs,
including all scored submissions, actions, wiki transitions, and failed starts,
stay under `runs/ternary/`. There is no automatic replacement or resume.
For the published target and order seeds, use
`examples/ternary.terminal-historical.example.json` or
`examples/ternary.repeated-historical.example.json`. Choose `seats: 1` or
`seats: 4` explicitly. Six models require 108 or 864 sessions respectively;
both populations total 972 per scoring protocol. Provider templates must be
configured before execution. The published target/order profile does not imply
identical remote-model behavior or transport: final historical Kimi/Qwen recovery
used streaming; the public `json-900-v1` profile explicitly records its JSON
transport and retry policy.

## Published persistent-Wiki experiment

Use `examples/wiki.published.example.json`, replace the image and provider paths,
then use the same `prepare`, `check`, `run` and `grade` commands as the function
suite below. Alternatively, generate it with `default-spec --published`, repeated
`--candidate NAME=CONFIG` arguments and `--image "$IMAGE_ID"`; omit `--reference`.
This profile contains six positions and three conditions, with no function-suite
or reference-model sessions. Six models require exactly 972 sessions. The older
two-position development profile remains unchanged.
Participant surfaces, founder file hashes and all 36 six-model wave orders match
the historical schedule. Host execution differs: the historical runner used
concurrent model pipelines and per-session deadlines; this public runner uses
its serial wave loop and the supplied overall deadline. See the machine-readable
[mapping checks](../report/release/wiki-mapping.json).

## Recompute published results

From a source checkout, no model or container is needed for descriptive analysis:

```sh
.venv/bin/python -m parabox.benchmark analyze report/release --output /tmp/parabox-summary.json
```

The same command accepts a newly completed ternary run or a prepared published
Wiki run. Unended and ungraded sessions are not turned into zero-score results.
The bundle contains canonical session records, candidate source artifacts,
selected relay actions, configuration mapping and attempt accounting. Strings
in `sources.json` identify historical source records; they are not local links.

To independently regrade the published Wiki candidates using the installed
per-case sandbox evaluator (no provider calls):

```sh
.venv/bin/python -m parabox.benchmark grade-evidence report/release \
  --image "$IMAGE_ID" --cache runs/regrade-cache --output runs/regrade.json
```

This can be expensive. Published missing grades used the existing qualified
batch evaluator (one container per candidate, fresh interpreter per case);
the public regrade command uses per-case containers and reports disagreements
rather than overwriting the published grades. Candidate artifacts must never
be imported or executed directly on the host.

## Function-task development suite

The installed suite includes solvable functions, an impossible diagnostic, and
a separate wiki component. It is not a replay of historical seeded-method
studies. Prepare an explicit candidate and reference model configuration:

```sh
.venv/bin/python -m parabox.benchmark default-spec \
  --candidate candidate=private-candidate.json \
  --reference private-reference.json --image "$IMAGE_ID" > suite.json
.venv/bin/python -m parabox.benchmark prepare runs/shared-work --spec suite.json
.venv/bin/python -m parabox.benchmark check runs/shared-work
```

For one candidate the full suite plans 108 sessions. Its `run` command requires
`--authorize-session-cap 108 --deadline <future-UTC-time>`; `grade` performs
the independent audit afterward. Historical seeded-method commands require a
source checkout and are not part of the installed package.

## Reproduce and extend

Run offline tests with `.venv/bin/python -m unittest discover -s tests -t .`.
Container tests need the built image; no test should make a paid model call.
Prepared manifests, model-config hashes, source hashes, session records and
receipts remain with a run. Keep technical failures and unavailable descendants
in denominators instead of turning them into clean outcomes. Hosted models may
not reproduce byte-identical traces.

For a new function task, implement the `Task` contract in
`parabox/tasks/base.py`: workspace, operational prompts and tools, tool dispatch,
contribution export, and an independent audit. For a different terminal
submission lifecycle, add a task runtime and expose its output through the
execution ledger. Change participant inputs or scoring in a versioned design;
do not silently relabel earlier runs. See [Security](../SECURITY.md) before
handling participant artifacts.
