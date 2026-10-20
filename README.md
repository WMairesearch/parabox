# Parabox

**A benchmark framework for misalignment propagation between AI agents.**

An agent can finish its task and still leave behind a method that leads the
next agent to violate its instructions. Shared notes, reusable code and working
records make influence outlast a conversation—and cross system and task boundaries.
Testing each agent alone misses this part of the system's behavior.

Parabox measures what changes when agents encounter and maintain one another's
work: which methods they adopt, where they spend resources, what they publish,
and whether successors repeat or correct the resulting violations.

## What the experiments show

- **Methods travel.** Recorded handoffs connect a predecessor's verifier bypass
  to a successor reading its note, recreating the bypass and receiving an
  accepted result that fails an independent execution audit.
- **The same shared workspace can develop differently.** In the wiki study,
  agents both extended private-test recovery and actively removed its artifacts.
  Eleven recipients requested private cases; four other recipients deleted
  recovery files and left corrective material.
- **Interaction changes measured outcomes.** Controlled exposure and peer-model
  comparisons change accepted-invalid rates. Keeping recipients fixed while
  changing one peer produces sharply different later-generation trajectories.
- **Task success can coexist with propagation.** All eleven private-case
  requesters earned full own reward. They spent 112 execution units on
  acquisition commands and requests, and eight added case records to the wiki.
  Successful task completion alone would miss this behavior.

Start with the [research report](report/README.md), which connects the cases,
condition comparisons and resource analysis. Historical studies have different
tasks and budgets; the report retains their separate denominators.

## Run the framework

Python 3.12+ is required. These installation and offline checks make no model calls:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
.venv/bin/python -m parabox.benchmark --help
```

Actual execution uses Linux, rootless Podman, a task image and a provider
configuration. Follow [installation and first run](docs/getting-started.md)
before launching participants.

The [default development suite](docs/shared-work.md) combines two environments:

| Environment | Agent's work | What can reach a successor |
|---|---|---|
| Function tasks | Implement and submit a Python function | Shared methods, code and advice |
| Shared test wiki | Improve a package under a charged execution budget | Editable notes, helpers and accumulated cases |

The suite plans **36 + 72N sessions** for `N` candidate configurations.
Preparation freezes assignments and requires no provider access; execution
requires an explicit session cap and deadline. The release includes task assets
and the founder bundle needed to prepare it outside the research checkout.
Custom function studies use `parabox-eval`.

The default suite is a reusable development design. The published findings come
from its separately documented predecessor studies. [Release checks](report/release-validation.md)
exercise the integrated runners, including small hosted-model runs; a complete
hosted-model evaluation of the default suite has not yet been reported.

## Follow the whole trajectory

Parabox keeps four observations connected rather than collapsing them into one
score:

**Resource use · own task outcome · boundary behavior · successor continuation**

For function tasks, agent-facing acceptance and independently audited
correctness are separate. For the wiki, code score, reward, private-case requests,
published additions and deletions are separate. Transmission records distinguish
what was delivered from what was read and subsequently acted upon.

This supports tests of exposure, persistence, peer composition and correction.
Resource spending can reveal work on a shared unauthorized project even when
the agent still completes its own task. Conversely, an inherited bypass can
reduce effort while increasing violations. Reward-conflict studies separately
test how agents respond when continued acquisition directly costs their own
reward.

## Find your way

| Need | Read |
|---|---|
| Install, configure and run | [Getting started](docs/getting-started.md) |
| Understand the components | [Architecture](docs/architecture.md) |
| Define transmission and budgets | [Shared-work suite](docs/shared-work.md) |
| Add a task | [Extension guide](docs/adding-a-task.md) |
| Recompute results or audit a new run | [Reproducibility](docs/reproducibility.md) |
| Present the findings | [Slides](report/decks/spread-of-misalignment/README.md) |
| Understand sandbox boundaries | [Security](SECURITY.md) |

`parabox/` contains the framework; `examples/` contains portable configurations;
`tests/` checks its contracts. `data/` holds only runtime inputs.
All published protocols, results and presentation material live in `report/`.
Raw local runs stay in the ignored `runs/` directory. Legacy commands and Lean
studies remain available for historical reproduction, with their requirements
described in the [research history](docs/history.md).

## Contribute

Original code is [MIT-licensed](LICENSE), collectively attributed to
[Parabox contributors](AUTHORS.md). Retained third-party components keep
[their own licenses](THIRD_PARTY.md).
The [contribution guide](CONTRIBUTING.md) uses DCO sign-off, without a separate CLA.
