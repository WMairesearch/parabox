# Installation and quick start

For a locked host environment, install uv and run `uv sync --locked --extra report --group dev`.
The checked-in `uv.lock` records runtime, report and build dependencies with hashes.
The isolated build backend is also pinned in `pyproject.toml`; build release
archives with `.venv/bin/python -m build --no-isolation` after the locked sync.
After populating the cache, the same command accepts `--offline`; initial installation
requires downloading dependencies. The Python task image pins its base digest and
hashed Python requirements. These are release build inputs, not a reconstruction
of the historical experiment image; preserve the original image identity for that purpose.

Valid conditions are `control`, `note`, `method`, `goal`, `hint`, `prohibit`,
`c1`, `c3`, `inject`, `cue`, and `mixed-method`. Historical population aliases
`v4pro-all`, `v4pro-selected`, `mixed-all`, `mixed-selected`, `all`, and `selected`
retain their location-hint seed and merge behavior. Method/goal/hint/prohibition
and condemnation texts require the harness or open gate. Conditions must be
unique; use repetitions or chains for independent repeats. Counts and budgets
must be positive. Hard stops require a timezone, for example `2026-10-14T12:00:00Z`.

## Requirements

- Python 3.12 or newer, with `venv` and pip.
- Linux with rootless Podman for participant execution and independent audit.
- Model-provider credentials only for explicitly requested live runs.
- For slides: TeX Live with Beamer, `latexmk`, `biber`, and the Latin Modern fonts.

From a source checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.studies.unified --help
```

`parabox-eval` is the installed unified-study command. Historical commands
remain available through `python -m parabox` / `parabox` for old protocols.
The source checkout carries research configuration, tables and documentation;
the wheel carries framework code and packaged task assets.
The source distribution also includes final-study outcome tables and current
deck figure assets for offline analysis; private run evidence is never bundled.
It also includes the retained historical seeds and frozen corpus. Only the
seed needed by the unified runner's shared modules is also packaged in the
wheel; other historical inputs require a source checkout and any additional
evidence named in their protocols.

## Offline design tests

```sh
.venv/bin/python -m unittest tests.test_unified_peer tests.test_population
```

No API key or container is needed for these design/merge checks. The full
suite has image-dependent tests and should be run with Podman installed:

```sh
.venv/bin/python -m unittest discover -s tests -t .
```

## Build and verify the Python instrument

Building downloads the base image and pytest. Subject and audit containers
run without network access; installation/build-time networking is separate.

```sh
podman build -t localhost/parabox-code:py312 parabox/tasks/code/image
.venv/bin/python -m parabox.studies.unified selftest
```

Selftest uses repository-authored fixtures and no model calls. It checks
gate separation, hidden-case rejection, correct-solution acceptance and
independent audit of the skip-hook fixture. Keep the resulting image ID with
the protocol. A tag alone is not an immutable image reference.

## Explicit opt-in: a small paid run

For a no-cost configuration example after building the image, run only
`prepare` and `check` below using `examples/model.example.json`. The placeholder
provider is intentionally unusable; do not run it. Preparation/checking do not
contact a model provider. Use a different run directory for the real experiment.

Copy `examples/model.example.json` to a private configuration and set its
provider URL and model ID. Set `PARABOX_API_KEY` in the host environment.
Do not put the secret value in the JSON. The first command below freezes
configuration; `run` is the command that contacts the provider.

```sh
.venv/bin/python -m parabox.studies.unified prepare runs/example \
  --mode single --gate open --conditions control,method --problems second_item \
  --reps 1 --turns 50 --concurrency 1 --model /path/to/private-model.json
.venv/bin/python -m parabox.studies.unified check runs/example
.venv/bin/python -m parabox.studies.unified run runs/example
.venv/bin/python -m parabox.studies.unified audit runs/example
.venv/bin/python -m parabox.studies.unified score runs/example --out runs/example/outcomes.csv
.venv/bin/python -m parabox.studies.unified check runs/example
```

This is a two-session engineering example, not an adequately powered study.
Use a fresh directory for a new design. Explicitly set a UTC `--hard-stop`
for bounded live work. Preserve abnormal sessions before retrying them;
normal refusals and truncations are outcomes, not infrastructure retries.
Host-side artifact access uses POSIX descriptor-relative operations; Windows
execution is not supported. Use a disposable Linux VM for adversarial runs.

## Historical Lean work

Lean requires a separate image and task corpus; its historical protocols are
not distributed in this copy. The image Dockerfile remains under
`parabox/tasks/lean/image/`. The Python quick start does not validate Lean
theorem assets or establish their redistribution license.
