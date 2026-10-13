# Third-party material inventory

This inventory records known provenance. It does not grant rights to material
owned by others, or certify that every imported notice has been preserved.

| Material | Local location | Source and license evidence | Release action |
|---|---|---|---|
| Formal Conjectures statements | `parabox/tasks/lean/image/Problems/*.lean` | Files identify source paths and commit `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`; [pinned LICENSE](https://github.com/google-deepmind/formal-conjectures/blob/1b567c2f96e2aa86328094c4b9ca57f72a0d886e/LICENSE) is Apache-2.0, copied to `licenses/Formal-Conjectures-Apache-2.0.txt` | Repository adapts statements into editable task templates; review source-file notices and attribution |
| Mathlib and Lean declarations/docs index | `data/corpus/mathlib-v4.33.1.json`, `_build/` | Mathlib and Lean v4.33.1; license copies in `licenses/Mathlib-Apache-2.0.txt` and `licenses/Lean-Apache-2.0.txt` | Every prose-bearing entry mapped to pinned source with retained headers in `licenses/Corpus-Attribution.txt`; signatures are pretty-printed declarations |
| Lean/Mathlib dependencies | Lean image Dockerfile, lakefile | Downloaded during image build, not a vendored dependency tree | Keep dependency revisions and licenses with a distributed image |
| Python, pytest, base operating-system images | Python image Dockerfile | Downloaded at build time; pytest 8.3.4 | Record image digests; distribution of images needs their own notices |
| Hosted model outputs | Runtime seeds under `data/seeds/` and `parabox/studies/transmission/assets/`, frozen note constants, historical documents, the excerpt in `report/decks/spread-of-misalignment/evidence/relay-example.json`, local `runs/` | Generated under provider-specific access terms; code license alone is insufficient | Review retained excerpts and seeds as well as any raw-transcript export; internal reviewer outputs are excluded |
| Bibliography and externally reported event counts | `report/decks/spread-of-misalignment/ref.bib` | Individual cited publications | Verify claims against sources; do not copy whole papers or imply endorsement |

The Python task definitions and analysis source are repository-authored
unless otherwise marked and are licensed under the root MIT license.
That license does not replace third-party terms. Imported Apache-2.0 material
keeps its existing license and attribution, unchanged by this export.
The package license expression `MIT AND Apache-2.0` reflects these bundled
materials; it does not offer a choice of license for every file.
License evidence above was inspected on 2026-10-12;
the two license copies above were fetched from the pinned references. Their
upstream byte hashes are respectively
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` and
`b40930bbcf80744c86c46a12bc9da056641d722716c378f5659b9e555ef833e1`.
All twelve imported Formal Conjectures statement headers were checked at
that revision. Their copyright notices, source mapping and adaptation notice
are preserved in `licenses/Formal-Conjectures-Attribution.txt`; the pinned
root `NOTICE` URL returned 404. The extracted corpus includes Lean core
docstrings as well as Mathlib text. All prose-bearing entries were located
in pinned sources; copyright and author headers are retained in
`licenses/Corpus-Attribution.txt`. The Lean license SHA-256 is
`8b28515ffffc5c0fe2807d8ae3735b00b324d9b7ce807dd63ff6ac8922fbce7e`.
Neither pinned Mathlib nor Lean tree has a root `NOTICE` file. Distribution
of their full runtimes/images needs a separate transitive-dependency review.
This inventory is not a legal certification.
