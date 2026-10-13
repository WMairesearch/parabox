# Runtime inputs

This directory contains runtime inputs only. Presentations, protocols, results
and supporting evidence belong in [`report/`](../report/README.md).

| Files | Reason retained |
|---|---|
| `corpus/mathlib-v4.33.1.json` | Frozen input loaded by the search relay |
| `seeds/` | Inputs loaded by relay, board and transmission studies |

Raw runs remain local. Seeds include historical model-generated text; retaining
them for runtime compatibility does not waive the release rights/privacy review.
The transmission seed also has a byte-identical packaged copy under
`parabox/studies/transmission/assets/`, required by the unified runner's imports.
See [third-party notices](../THIRD_PARTY.md) and [evidence limits](../docs/reproducibility.md).
