# Run and extend

Use Python 3.12+ and Linux with rootless Podman for participant execution.
Provider credentials stay on the host in environment variables; never put them
in model configuration JSON or mount them into a container. The example model
file is a template, not a working provider account.

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
The public release contains no hosted-model result table for this runner yet.

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
