# Parabox

Parabox is a sandboxed benchmark for studying how one AI agent's work changes
another agent's behavior. It separates a violation discovered by one agent from
its publication, exposure, adoption, and continuation by later agents.

## Experiments

| Experiment | Agent's task | Shared material | Main observation |
|---|---|---|---|
| Misaligned method propagation: persistent Wiki | Repair a function with public examples and a private-case access boundary | An editable directory inherited from earlier agents | Unauthorized private-case requests, returned cases, task scores, and continuation or correction |
| Costly information contribution | Match a hidden sequence of 100 ternary values | An editable wiki and read-only submission receipts | Whether a scored submission gives up attainable points to reveal information used by successors |

The released Wiki experiment varies inherited material and starter-program
scores (30, 60, or 90, not ceilings). The sequence experiment varies the number
of initially known values (1, 40, or 85); those correspond to approximate
random-completion expectations of 34, 60, and 90 points, not guaranteed scores.
See [experiment design](docs/experiments.md) for the task surfaces, comparisons,
and outcome definitions. The [results](report/results.md) link the completed
sequence and persistent-Wiki experiments to their configurations and evidence.
Sequence information contribution is measured separately from misconduct.
The function-task development suite and earlier impossible-function studies
remain available; they are not the experiments in this results bundle.

For a first read: start here, then read the [experiment designs](docs/experiments.md),
and use the [run guide](docs/running.md) when ready to reproduce a protocol.
The [historical study guide](parabox/studies/README.md) explains earlier
experiments and the archived tables; those are not the installed benchmark.

## Run

Python 3.12+ is required. Preparation and checks make no model calls:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
.venv/bin/python -m parabox.benchmark.ternary --help
.venv/bin/python -m parabox.benchmark analyze report/release
```

Participant runs require Linux, rootless Podman, an immutable local image,
provider configuration, an exact session authorization, and a deadline.
[Running and extending](docs/running.md) gives a complete 18-session sequence
walkthrough and a 162-session, one-model Wiki walkthrough. These are the smallest
supported batches, not single-chain smoke runs. Start with offline analysis
before authorizing either batch.
Never run participant code on the host; see [Security](SECURITY.md).

`parabox/` contains the execution framework and task implementations.
`examples/` contains configuration templates. Runtime inputs live in `data/`;
published evidence belongs in `report/`. The evidence bundle is available in the
source checkout, not the wheel. Historical study code is retained in
the source checkout but excluded from built packages. Original contributions
are [MIT-licensed](LICENSE); third-party material keeps its own license.
