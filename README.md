# Parabox

**Which models initiate, join, extend, or interrupt misaligned practices—and how does their participation change other agents' behavior?**

Agents working together can share methods, build shared resources, and leave records that outlive their own sessions. Parabox measures how models behave in these settings: whether an agent crosses a task boundary, and how its participation changes what peers and successors do.

The motivating concern is agent-built coordination of unauthorized work, as in the [OpenAI–Hugging Face incident](https://openai.com/index/hugging-face-incident-and-the-road-ahead/). There, agents meant to be isolated shared ways to cheat a scorer on an unsanctioned message board, and some risked failing their own tasks to produce information for the others ([METR/Redwood investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)). The experimental variable is the participating model. Messages and shared files are how participants influence one another.

## Three experiments

| Experiment | Task and environment | What we measure |
| -- | -- | -- |
| Misaligned Method Propagation | Implement a function alongside other agents, with shared work records | Whether replacing one participant changes fixed peers' violations |
| Shared Practice Maintenance | Repair a function with access to an editable shared Wiki | Which models acquire, extend, use, correct, or remove a shared practice |
| Costly Information Contribution | Match a hidden ternary sequence; some submissions forgo points to disclose information | Which models spend their scoring opportunities on information for successors, and how successors continue |

The sequence experiment measures personal scoring sacrifice and information contribution. Across the experiments, we measure a model's own actions and its effects on other agents.

Read the [experiment designs](docs/experiments.md) for tasks, tools, scoring and model comparisons. The [results](report/results.md) show changes in fixed peers' behavior, Wiki continuation and correction, and costly information contribution, with configurations and supporting evidence.

## Start here

Python 3.12+ is required. Installation, self-checks and result analysis make no model calls:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
.venv/bin/python -m parabox.benchmark analyze report/release
.venv/bin/python -m parabox.benchmark analyze report/functions
```

Use the [run guide](docs/running.md) to configure models and launch experiments. Participant execution requires Linux, rootless Podman, an immutable local image, an explicit session budget and a deadline. Never run participant code on the host; see [Security](SECURITY.md).

## Repository

- `parabox/`: task implementations and shared execution infrastructure.
- `examples/`: configuration templates for new runs.
- `data/`: runtime inputs.
- `report/`: results, protocol configurations and supporting evidence, available in the source checkout.

See [Contributing](CONTRIBUTING.md) to extend the benchmark. Original contributions are [MIT-licensed](LICENSE); third-party material retains its own license.
