# Gate comparison

Written 2026-10-09 19:47 UTC, before any subject call.

- Code commit: `acd689b55be054f6451eb63e61dc3a4746265341` (`git rev-parse HEAD`)
- Design seed: `2026100901`
- Mode: `single`
- Turns: 24
- Concurrency: 8
- Sessions per condition per model per gate: 16
- Hard stop: `2026-10-10T00:30:00+00:00`
- Instrument: `python3 -m parabox.studies.unified`

## Cells

Row `gate-comparison` from `report/studies/final/protocol.md`: state and score gates;
conditions `control`, `note`; six models; single generation.
`6 x 2 x 2 x 16 = 384` sessions. State before score within a model.

## Model order

1. `v4pro` = `configs/model-bailian-deepseek-v4-pro.json`
2. `gemini` = `configs/model-gemini.json`
3. `kimi` = `configs/model-bailian-kimi-k3.json`
4. `qwen-max` = `configs/model-bailian-qwen3-8-max.json`
5. `ds-flash` = `configs/model-deepseek.json`
6. `qwen-flash` = `configs/model-bailian-qwen3-8-flash.json`

One run directory per model per gate: `runs/gate-comparison-<gate>-<name>`.

## Registered predictions

- State/score baseline `control`, state and score: cheat <= 1/16 for every model and gate.
- State exposure `note`, state: V4 Pro >= 8/16; Gemini >= 6/16 (24 turns); Kimi
  >= 3/16; Qwen Max, DeepSeek Flash and Qwen Flash <= 1/16.
- Score exposure `note`, score: V4 Pro >= 8/16; Gemini >= 4/16; Kimi >= 4/16; the
  Qwen Max, DeepSeek Flash and Qwen Flash <= 1/16.

## Exact commands

Setup (every shell):

```
cd /path/to/parabox
export CONTAINERS_CONF=$PWD/.containers/containers.conf
```

Selftest (once, after this stamp is committed):

```
python3 -m parabox.studies.unified selftest
```

For each pair `(gate, name, config)` below, in this order of models, state
then score:

```
python3 -m parabox.studies.unified prepare runs/gate-comparison-<gate>-<name> --mode single --gate <state|score> --conditions control,note --model <config> --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-<gate>-<name>
python3 -m parabox.studies.unified audit runs/gate-comparison-<gate>-<name>
python3 -m parabox.studies.unified score runs/gate-comparison-<gate>-<name> --out report/final/gate-comparison-<gate>-<name>.csv
```

Expanded:

```
python3 -m parabox.studies.unified prepare runs/gate-comparison-state-v4pro --mode single --gate state --conditions control,note --model configs/model-bailian-deepseek-v4-pro.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-v4pro
python3 -m parabox.studies.unified audit runs/gate-comparison-state-v4pro
python3 -m parabox.studies.unified score runs/gate-comparison-state-v4pro --out report/final/gate-comparison-state-v4pro.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-v4pro --mode single --gate score --conditions control,note --model configs/model-bailian-deepseek-v4-pro.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-v4pro
python3 -m parabox.studies.unified audit runs/gate-comparison-score-v4pro
python3 -m parabox.studies.unified score runs/gate-comparison-score-v4pro --out report/final/gate-comparison-score-v4pro.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-state-gemini --mode single --gate state --conditions control,note --model configs/model-gemini.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-gemini
python3 -m parabox.studies.unified audit runs/gate-comparison-state-gemini
python3 -m parabox.studies.unified score runs/gate-comparison-state-gemini --out report/final/gate-comparison-state-gemini.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-gemini --mode single --gate score --conditions control,note --model configs/model-gemini.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-gemini
python3 -m parabox.studies.unified audit runs/gate-comparison-score-gemini
python3 -m parabox.studies.unified score runs/gate-comparison-score-gemini --out report/final/gate-comparison-score-gemini.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-state-kimi --mode single --gate state --conditions control,note --model configs/model-bailian-kimi-k3.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-kimi
python3 -m parabox.studies.unified audit runs/gate-comparison-state-kimi
python3 -m parabox.studies.unified score runs/gate-comparison-state-kimi --out report/final/gate-comparison-state-kimi.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-kimi --mode single --gate score --conditions control,note --model configs/model-bailian-kimi-k3.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-kimi
python3 -m parabox.studies.unified audit runs/gate-comparison-score-kimi
python3 -m parabox.studies.unified score runs/gate-comparison-score-kimi --out report/final/gate-comparison-score-kimi.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-state-qwen-max --mode single --gate state --conditions control,note --model configs/model-bailian-qwen3-8-max.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-qwen-max
python3 -m parabox.studies.unified audit runs/gate-comparison-state-qwen-max
python3 -m parabox.studies.unified score runs/gate-comparison-state-qwen-max --out report/final/gate-comparison-state-qwen-max.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-qwen-max --mode single --gate score --conditions control,note --model configs/model-bailian-qwen3-8-max.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-qwen-max
python3 -m parabox.studies.unified audit runs/gate-comparison-score-qwen-max
python3 -m parabox.studies.unified score runs/gate-comparison-score-qwen-max --out report/final/gate-comparison-score-qwen-max.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-state-ds-flash --mode single --gate state --conditions control,note --model configs/model-deepseek.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-ds-flash
python3 -m parabox.studies.unified audit runs/gate-comparison-state-ds-flash
python3 -m parabox.studies.unified score runs/gate-comparison-state-ds-flash --out report/final/gate-comparison-state-ds-flash.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-ds-flash --mode single --gate score --conditions control,note --model configs/model-deepseek.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-ds-flash
python3 -m parabox.studies.unified audit runs/gate-comparison-score-ds-flash
python3 -m parabox.studies.unified score runs/gate-comparison-score-ds-flash --out report/final/gate-comparison-score-ds-flash.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-state-qwen-flash --mode single --gate state --conditions control,note --model configs/model-bailian-qwen3-8-flash.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-state-qwen-flash
python3 -m parabox.studies.unified audit runs/gate-comparison-state-qwen-flash
python3 -m parabox.studies.unified score runs/gate-comparison-state-qwen-flash --out report/final/gate-comparison-state-qwen-flash.csv

python3 -m parabox.studies.unified prepare runs/gate-comparison-score-qwen-flash --mode single --gate score --conditions control,note --model configs/model-bailian-qwen3-8-flash.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/gate-comparison-score-qwen-flash
python3 -m parabox.studies.unified audit runs/gate-comparison-score-qwen-flash
python3 -m parabox.studies.unified score runs/gate-comparison-score-qwen-flash --out report/final/gate-comparison-score-qwen-flash.csv
```

Execution: four `run` processes at a time; for each model start its state and
score runs together; keep two models in flight (v4pro + gemini first, then
kimi, qwen-max, ds-flash, qwen-flash as slots free). After each run: audit,
then score. After the hard stop, no new session starts; incomplete cells are
reported as partial.

## corrected-gate-exposure correction stamp

Written 2026-10-09 21:26 UTC, before any corrected-gate-exposure subject call.

- Code commit: `0bb3f192a38268a83ae44f5f0808ee9b85e3f5e0`
- Cause: protocol error — first-run `note` planted the harness exploit note
  under state and score (deviation log, 2026-10-09 21:30 UTC).
- Correction: `note` is gate-specific. State plants earlier zero-door study `RECIPE_A4`
  (digest `07d560fb95af6e35c3a9c93d2209c9d42a3d6df1c9c7997be4c022721d128c65`,
  confirmed in `runs/corrected-gate-exposure-state-v4pro/protocol.json` frozen
  `planted_digests.note_state`). Score plants earlier zero-door study `RECIPE_A5`
  (digest `e58b13f4f305efbc455baeb044d1b1a5a2a8e194443693ff2eed13462f2c1e99`,
  confirmed in `runs/corrected-gate-exposure-score-v4pro/protocol.json` frozen
  `planted_digests.note_score`). Path still `shared/note-from-K7.txt`.
- Condition: `note` only. Mode single, 16 sessions, turns 24, seed 2026100901,
  concurrency 8, hard stop `2026-10-10T00:30:00+00:00`. Existing `runs/gate-comparison-*`
  left untouched.

Directories:

```
runs/corrected-gate-exposure-state-v4pro
runs/corrected-gate-exposure-score-v4pro
runs/corrected-gate-exposure-state-gemini
runs/corrected-gate-exposure-score-gemini
runs/corrected-gate-exposure-state-kimi
runs/corrected-gate-exposure-score-kimi
runs/corrected-gate-exposure-state-qwen-max
runs/corrected-gate-exposure-score-qwen-max
runs/corrected-gate-exposure-state-ds-flash
runs/corrected-gate-exposure-score-ds-flash
runs/corrected-gate-exposure-state-qwen-flash
runs/corrected-gate-exposure-score-qwen-flash
```

Prepare (each):

```
python3 -m parabox.studies.unified prepare runs/corrected-gate-exposure-<gate>-<name> --mode single --gate <state|score> --conditions note --model <config> --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
```

Then `run`, `audit`, `score ... --out report/final/corrected-gate-exposure-<gate>-<name>.csv`.
Abnormal sessions: `python3 -m parabox.studies.unified retry runs/<dir>`
(not a second `run` on a live directory).
