# The Spread of Misalignment

The presentation asks when an agent's local deviation becomes shared practice:
does interaction change what recipients would otherwise do, do they maintain
the method for successors, and what makes the chain stop?

`short.tex` moves from motivating incidents to linked relays, divergent
trajectories and controlled comparisons. `main.tex` includes that same talk and
adds `methods-detail.tex`: protocols, replication units, additional results and
the executable development suite. Both use default Beamer styling, English
text and no slide numbers.

## Reading the evidence

- **Onset:** compare a recipient's behavior with and without inherited work.
  A supplied seed tests the start of transmission, not spontaneous discovery
  of that seed.
- **Continuation:** connect publication, actual delivery and successor action.
  Compare an accumulating library with the same fixed seed, and follow fresh
  recipients across successive handoffs.
- **Interruption:** observe participant-initiated cleanup and separately test
  an experimentally inserted, agent-written correction. Measure later violations
  and legitimate work, not simply whether a warning or deletion occurred.

The contributor-model comparison keeps the recipient model fixed. It measures
how a model changes others' trajectories, rather than substituting that model's
own failure rate for its influence.

Resource allocation runs through the same evidence: private retrieval and wiki
maintenance can coexist with full own reward; inherited shortcuts can reduce
turn use while increasing violations. The own-reward-conflict follow-up is in
the appendix. It is a separate condition, not a prerequisite for establishing
propagation.

Accumulation changes both the amount and content of inherited work. It does
not isolate elapsed time or word count. Likewise, observed cleanup bundles
deletion, guidance and replacement material. The long version proposes a
matched-snapshot comparison of these components and labels it as future work.

## Evidence map

| Material in the talk | Public evidence |
|---|---|
| Function-task exposure, inheritance and correction | [Study reports](../../studies/final/) and corresponding [session CSVs](../../final/) |
| Fixed seed versus accumulated proof work | [Matched-block counts and protocol metadata](evidence/accumulation.json), checked by `scripts/accumulation_report.py` |
| Fixed recipients with varying contributors | [Composition analysis](../../final/peer-composition-analysis.json), session CSVs and [protocol](../../studies/final/peer-composition.md) |
| Executed verification bypass | [Selected relay record](evidence/relay-example.json): outgoing excerpt, recipient tool steps and audit bindings |
| Wiki acquisition, resources, relay and cleanup | [Wiki report](../../shared-test-wiki/README.md), numeric rows and bounded supplemental annotations |
| Exposure and solvable-chain turn use | [Resource allocation export](../../resource-allocation/README.md), kept separate from wiki charged units |

The relay binding includes a saved outgoing excerpt and tool/audit references.
Full conversations are not distributed. Linked examples establish reading and
action, with other inherited material also available. The accumulation export
contains saved outcome counts and source digests; its public recomputation
does not rerun withheld proof audits.

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
python scripts/accumulation_report.py --check
```

These commands make no model calls. Table and figure generators retain the
frozen numerical inputs and check denominators. Unknown audits remain gaps in
trajectories; chain dots represent independent lineages, not independent seats.
The additional peer plot shows descriptive chain-bootstrap intervals.

Install LaTeX with Beamer, Latin Modern, `latexmk` and `biber`. From the
repository root, build in a fresh directory and replace both local PDFs only
after both compilations succeed:

```sh
set -eu
BUILD="$(mktemp -d)"
DECK=report/decks/spread-of-misalignment
cp "$DECK/"*.tex "$DECK/ref.bib" "$BUILD/"
cp -R "$DECK/figures" "$BUILD/"
(cd "$BUILD" && latexmk -pdf -interaction=nonstopmode -halt-on-error short.tex)
(cd "$BUILD" && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex)
install -m 644 "$BUILD/short.pdf" "$DECK/short.pdf"
install -m 644 "$BUILD/main.pdf" "$DECK/main.pdf"
```

Open `report/decks/spread-of-misalignment/short.pdf` or `main.pdf`.
The temporary build directory retains diagnostic logs. The two local deck PDFs
are Git-ignored: committing or pushing the sources does not publish them.
Tracked sources, evidence bindings and figures are sufficient to rebuild
both decks without unpublished presentations or model calls.
