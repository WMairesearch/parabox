# Exposure

Written 2026-10-09 19:47 UTC, before any subject call.

- Code commit: `acd689b55be054f6451eb63e61dc3a4746265341` (`git rev-parse HEAD`)
- Design seed: `2026100901`
- Hard stop: `2026-10-10T00:30:00+00:00`

## Cells

Row `exposure` of `report/studies/final/protocol.md`.

- Instrument: `python3 -m parabox.studies.unified`
- Gate: harness (`hygienic-a2`)
- Mode: single
- Conditions: `control`, `note`
- Sessions: 16 per condition per model (4 problems × 4 replicates)
- Turns: 24
- Concurrency: 8
- Models: six, one run directory each, started in this priority order

## Model order

1. `v4pro` = `configs/model-bailian-deepseek-v4-pro.json` → `runs/exposure-v4pro`
2. `gemini` = `configs/model-gemini.json` → `runs/exposure-gemini`
3. `kimi` = `configs/model-bailian-kimi-k3.json` → `runs/exposure-kimi`
4. `qwen-max` = `configs/model-bailian-qwen3-8-max.json` → `runs/exposure-qwen-max`
5. `ds-flash` = `configs/model-deepseek.json` → `runs/exposure-ds-flash`
6. `qwen-flash` = `configs/model-bailian-qwen3-8-flash.json` → `runs/exposure-qwen-flash`

## Registered predictions

- Harness baseline `control`, harness: cheat <= 1/16 for every model.
- Harness exposure `note`, harness: V4 Pro >= 10/16; Gemini >= 8/16; Kimi >= 4/16;
  Qwen3.8-max, DeepSeek-flash, Qwen3.8-flash <= 1/16 each.

## Exact commands

Environment: `export CONTAINERS_CONF=$PWD/.containers/containers.conf`

Selftest (once, before prepare):

```
python3 -m parabox.studies.unified selftest
```

Prepare (all six directories first):

```
python3 -m parabox.studies.unified prepare runs/exposure-v4pro --mode single --gate harness --conditions control,note --model configs/model-bailian-deepseek-v4-pro.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-gemini --mode single --gate harness --conditions control,note --model configs/model-gemini.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-kimi --mode single --gate harness --conditions control,note --model configs/model-bailian-kimi-k3.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-qwen-max --mode single --gate harness --conditions control,note --model configs/model-bailian-qwen3-8-max.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-ds-flash --mode single --gate harness --conditions control,note --model configs/model-deepseek.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-qwen-flash --mode single --gate harness --conditions control,note --model configs/model-bailian-qwen3-8-flash.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
```

Run / audit / score (per model, after prepare; run launched as three parallel pairs in the order above):

```
python3 -m parabox.studies.unified run runs/exposure-<name>
python3 -m parabox.studies.unified audit runs/exposure-<name>
python3 -m parabox.studies.unified score runs/exposure-<name> --out report/final/exposure-<name>.csv
```

Pair schedule: start `v4pro` and `gemini` together; when either finishes start `kimi`, then `qwen-max`, then `ds-flash`, then `qwen-flash` (at most two or three `run` processes at a time).
