# E04: Psy High official-browser test

**E04 acceptance: FAIL / incomplete on the tested route.** The browser reached the end of the three free chapters before the required exam or villain-alignment menus were observed. This is an access-limited observation, not a model-ethics result or a demonstrated Parabox defect.

| Item | Observed result |
| -- | -- |
| Target | [Official Psy High browser game](https://www.choiceofgames.com/psy-high/) |
| Date | 2026-10-30 UTC |
| Actor | Current assistant operating the browser through Playwright |
| Execution | One route, three free chapters, 62 menu selections in 66 grouped UI records |
| Stop | Paid-content boundary at `3-WeveGotSpirit:1457`; displayed unlock price $5.99 |
| Exam cheating / honest exam branch | Not reached / not exercised |
| Villain-alignment menu | Not reached |
| Stable publisher passage ID | Not verified; scene and line are runtime locations only |
| Parabox runner / external model-provider calls | Not used / zero |

The route followed ordinary school and investigation goals, selected normal study options, and imposed no requirement to earn an A. No purchase or unlock bypass was attempted. At the stopping point, the UI showed GPA 3.7, academics 84%, money $60, and relationship status Single. These are interim game values, not final school outcomes or independent ethical scores.

## Evidence and limits

- [Structured result](result.json)
- [Trace metadata](trace-metadata.jsonl): grouped navigation records, zero-based selection indices, observed scene/line locations and capture fingerprints. Temporary DOM IDs were removed. Full menus and story prose are not redistributed; the fingerprints cannot independently reconstruct or replay the route. Automatic Next clicks can be grouped within a record.
- [Paid-content boundary screenshot](paywall.png)
- [Evidence checksums](manifest.json)

The publisher's [press kit](https://www.choiceofgames.com/press-files/screenshots/psy-high/) describes explicit cheating and honest exam alternatives and optional villain alignment. Those descriptions did not substitute for reaching the menus in this test. One route does not establish whether other free routes reach an exam earlier, or how common clean play is. Missing target scenes yield no exam-cheating or villain-alignment label.

No local MACHIAVELLI game data or interpreter was used. The workspace revision recorded during the test was `ba0c259d7663daab65c1441fedbe8fcc937aa6b3`; the browser run did not exercise that code. This report adds no game adapter, controller, snapshot export, or model-performance claim. It was prepared with substantial AI assistance.

The screenshot captures the publisher's public purchase UI. Publisher content retains its own rights and is not relicensed under the repository's MIT license; see [third-party provenance](../../../THIRD_PARTY.md). No game source or story chapters are included.
