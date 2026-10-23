# Parabox

Parabox is a sandboxed benchmark for studying how one AI agent's work changes
another agent's behavior. It separates a violation discovered by one agent from
its publication, exposure, adoption, and continuation by later agents.

## Experiments

| Experiment | Agent's task | Shared material | Main observation |
|---|---|---|---|
| Misaligned method propagation | Implement a function under different task and feedback conditions | Code and notes from earlier agents | Verifier-accepted submissions rejected by an independent execution audit |
| Costly information contribution | Match a hidden sequence of 100 ternary values | An editable wiki and read-only submission receipts | Whether a scored submission gives up attainable points to reveal information used by successors |

The first experiment ranges from impossible-function diagnostics to solvable
tasks with different feedback. The second fixes the task and varies the number
of initially known values (1, 40, or 85); those correspond to approximate
random-completion expectations of 34, 60, and 90 points, not guaranteed scores.
See [experiment design](docs/experiments.md) for the task surfaces, comparisons,
and outcome definitions. The [public results page](report/results.md) is
intentionally empty until results for these integrated protocols are released.

## Run

Python 3.12+ is required. Preparation and checks make no model calls:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
.venv/bin/python -m parabox.benchmark.ternary --help
```

Participant runs require Linux, rootless Podman, an immutable local image,
provider configuration, an exact session authorization, and a deadline.
[Running and extending](docs/running.md) gives commands for both experiments.
Never run participant code on the host; see [Security](SECURITY.md).

`parabox/` contains the execution framework and task implementations.
`examples/` contains configuration templates. Runtime inputs live in `data/`;
published evidence belongs in `report/`. Historical study code is retained in
the source checkout but excluded from built packages. Original contributions
are [MIT-licensed](LICENSE); third-party material keeps its own license.
