# The Spread of Misalignment

The presentation follows a method from its first user into another agent's
actions, then examines diverging trajectories and comparisons that promote or
interrupt propagation. Influence can cross systems and tasks; it does not
require membership in one group.

`short.tex` is the talk. `main.tex` uses the same narrative and adds
`methods-detail.tex`, covering study designs, handoff rules, outcome definitions
and replication. Both use the default Beamer appearance without slide numbers.

## Reading the evidence

- **Relay:** a published verification bypass is executed by a successor; a
  consecutive wiki pair transfers private sampling from inventory to access logs.
- **Divergence:** inherited methods persist in some lineages, while other
  recipients delete acquisition files and publish corrective task material.
- **Comparison:** exposure, a scheduled correction and contributor-model
  composition change subsequent behavior under their respective protocols.

Resources describe how agents participate in these processes. Private retrieval
can coexist with full own reward, and exposure can reduce the turns used by a
violating recipient. Jointly measuring actions, own outcomes and onward work
reveals these different forms of participation. The separate reward-zeroing
follow-up records acquisition under an explicit personal cost and appears
alongside the later comparisons.

Observed cleanup combines deletion, warnings and replacement material.
The talk proposes a matched snapshot comparison to separate their effects;
it does not present that comparison as completed.

## Evidence map

| Material in the talk | Public evidence |
|---|---|
| Function-task exposure, inheritance and correction | [Study reports](../../studies/final/) and corresponding [session CSVs](../../final/) |
| Fixed recipients with varying contributors | [Composition analysis](../../final/peer-composition-analysis.json), session CSVs and [protocol](../../studies/final/peer-composition.md) |
| Executed verification bypass | [Selected relay record](evidence/relay-example.json): outgoing excerpt, recipient tool steps and audit bindings |
| Wiki acquisition, resources, relay and cleanup | [Wiki report](../../shared-test-wiki/README.md), numeric rows and bounded supplemental annotations |
| Exposure and solvable-chain turn use | [Resource allocation export](../../resource-allocation/README.md), kept separate from wiki charged units |

The displayed outgoing quotation is a saved evidence excerpt, not new
participant-facing guidance. Full conversations are not distributed. The
linked examples establish reading and action, while retaining the fact that
other inherited material was available.

Incident accounts are attributed in `ref.bib`. The opening combines the
Hugging Face intrusion and theorem-proving collective; the next slide places
DseWiki and UK AISI activity alongside publication-dated reports. These accounts
motivate the experiments rather than supply their outcome denominators.

Historical findings are not results of the new default suite. That suite plans
`36 + 72N` sessions for `N` candidates and has no reported model outcomes yet.
Its 108-session single-candidate plan is also distinct from the historical
108-recipient reward-conflict follow-up.

## Rebuild from the published inputs

Install the `report` extra, then run from the repository root:

```sh
python -m scripts.deck_tables --write
python -m scripts.deck_tables
python -m scripts.spread_figures
python -m scripts.peer_figures
python -m scripts.wiki_report --check
python scripts/resource_report.py --check
```

These commands make no model calls. Table and figure generators retain the
frozen numerical inputs and check denominators. Unknown audits remain gaps in
trajectories; chain dots represent independent lineages, not independent seats.
The additional peer plot shows descriptive chain-bootstrap intervals.

Compile outside the source tree:

```sh
BUILD="$(mktemp -d)"
DECK=report/decks/spread-of-misalignment
cp "$DECK/"*.tex "$DECK/ref.bib" "$BUILD/"
cp -R "$DECK/figures" "$BUILD/"
(cd "$BUILD" && latexmk -pdf -interaction=nonstopmode -halt-on-error short.tex)
(cd "$BUILD" && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex)
```

The build directory contains the PDFs and auxiliary files. The sources retain
the talk, its methods extension, evidence bindings and reproducible figures;
they do not depend on unpublished draft presentations.
