# Parabox

Parabox evaluates how AI models participate in and shape misaligned collective
work: whether they violate task boundaries, change other agents' behavior, and
contribute resources that allow a shared practice to continue. Models can also
interrupt that practice by refusing, correcting, or dismantling it.

The motivating concern is agent-built collaboration in incidents such as the
[OpenAI–Hugging Face incident](https://openai.com/index/hugging-face-incident-and-the-road-ahead/):
agents repurposed existing infrastructure to coordinate unauthorized work.
We study models as participants, not which researcher-written message is most
persuasive. Shared files, messages and receipts are channels through which model
behavior affects peers and successors.

## Experiments

| Experiment | Agent's task | Model behavior measured | Main comparison |
|---|---|---|---|
| Misaligned Method Propagation | Implement a function | Own violations and changes in peers' violations | Replace a contributor model while keeping recipient models fixed; compare isolated and cumulative work |
| Shared Practice Maintenance | Repair a function while maintaining a Wiki | Acquisition, contribution, correction and successor continuation | Compare model trajectories under matched starting conditions |
| Costly Information Contribution | Match a hidden ternary sequence | Spending personal scoring opportunities to produce information for successors | Compare models under terminal and repeated scoring |

Keep a model's own behavior, its effect on peers, and the whole population's
outcome separate. Wiki and sequence model comparisons describe participating
models; they do not substitute for the fixed-recipient influence comparison.
Sequence contributions isolate personal cost and are not themselves labeled
misconduct. Starting records, task conditions and scoring rules expose different
opportunities for these behaviors; they are specified in the
[experiment designs](docs/experiments.md).

The [results](report/results.md) connect historical contributor-model evidence
with the current Wiki and sequence release. The current function protocol is
implemented but has no released participant results. Historical protocols and
current runs retain separate denominators.

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
[Running and extending](docs/running.md) provides all three entry points, a complete 18-session sequence
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
