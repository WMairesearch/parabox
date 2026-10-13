# Chain pilot

Written 2026-10-09 19:48 UTC, before any subject call.

- Code commit: `acd689b55be054f6451eb63e61dc3a4746265341`
- Design seed: `2026100901`
- Instrument: `python3 -m parabox.studies.unified`
- Gate: `harness`
- Mode: `chain`
- Lineages: 4
- Generations: 4
- Sessions per condition per model: 16
- Turns: 24
- Concurrency: 8
- Hard stop: `2026-10-10T00:30:00+00:00`

## Cells

Row `chain-pilot` from `report/studies/final/protocol.md`: harness gate; chains `control`, `note`, 4 x 4, V4 Pro, Gemini, Kimi; `inject` chains, V4 Pro and Gemini. 3 x 32 + 2 x 16 = 128 sessions.

Eight run directories (one model per condition):

| Directory | Condition | Model name | Config |
|---|---|---|---|
| `runs/chain-pilot-note-v4pro` | `note` | v4pro | `configs/model-bailian-deepseek-v4-pro.json` |
| `runs/chain-pilot-note-gemini` | `note` | gemini | `configs/model-gemini.json` |
| `runs/chain-pilot-note-kimi` | `note` | kimi | `configs/model-bailian-kimi-k3.json` |
| `runs/chain-pilot-control-v4pro` | `control` | v4pro | `configs/model-bailian-deepseek-v4-pro.json` |
| `runs/chain-pilot-control-gemini` | `control` | gemini | `configs/model-gemini.json` |
| `runs/chain-pilot-control-kimi` | `control` | kimi | `configs/model-bailian-kimi-k3.json` |
| `runs/chain-pilot-inject-v4pro` | `inject` | v4pro | `configs/model-bailian-deepseek-v4-pro.json` |
| `runs/chain-pilot-inject-gemini` | `inject` | gemini | `configs/model-gemini.json` |

`inject` is a `note` chain with one condemnation (`C00_G01`) added at the generation-3 barrier.

## Order

Protocol order: `note` before `control`; `inject` last. Model order inside an condition: V4 Pro, Gemini, Kimi.

All eight directories are prepared and their `run` processes are started within the first 10 minutes so generations proceed in parallel across conditions (each generation is sequential inside an condition; four sessions per generation per condition).

## Exact commands

Setup (once):

```
cd /path/to/parabox
export CONTAINERS_CONF=$PWD/.containers/containers.conf
python3 -m parabox.studies.unified selftest
```

For each directory below, the same prepare / run / audit / score sequence. Prepare template:

```
python3 -m parabox.studies.unified prepare runs/chain-pilot-<condition>-<name> --mode chain --gate harness --conditions <condition> --model <config> --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/chain-pilot-<condition>-<name>
python3 -m parabox.studies.unified audit runs/chain-pilot-<condition>-<name>
python3 -m parabox.studies.unified score runs/chain-pilot-<condition>-<name> --out report/final/chain-pilot-<condition>-<name>.csv
```

Concrete prepare commands, in protocol order:

```
python3 -m parabox.studies.unified prepare runs/chain-pilot-note-v4pro --mode chain --gate harness --conditions note --model configs/model-bailian-deepseek-v4-pro.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-note-gemini --mode chain --gate harness --conditions note --model configs/model-gemini.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-note-kimi --mode chain --gate harness --conditions note --model configs/model-bailian-kimi-k3.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-control-v4pro --mode chain --gate harness --conditions control --model configs/model-bailian-deepseek-v4-pro.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-control-gemini --mode chain --gate harness --conditions control --model configs/model-gemini.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-control-kimi --mode chain --gate harness --conditions control --model configs/model-bailian-kimi-k3.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-inject-v4pro --mode chain --gate harness --conditions inject --model configs/model-bailian-deepseek-v4-pro.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-pilot-inject-gemini --mode chain --gate harness --conditions inject --model configs/model-gemini.json --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
```

Run / audit / score for the same eight directories:

```
python3 -m parabox.studies.unified run runs/chain-pilot-note-v4pro
python3 -m parabox.studies.unified run runs/chain-pilot-note-gemini
python3 -m parabox.studies.unified run runs/chain-pilot-note-kimi
python3 -m parabox.studies.unified run runs/chain-pilot-control-v4pro
python3 -m parabox.studies.unified run runs/chain-pilot-control-gemini
python3 -m parabox.studies.unified run runs/chain-pilot-control-kimi
python3 -m parabox.studies.unified run runs/chain-pilot-inject-v4pro
python3 -m parabox.studies.unified run runs/chain-pilot-inject-gemini
python3 -m parabox.studies.unified audit runs/chain-pilot-note-v4pro
python3 -m parabox.studies.unified score runs/chain-pilot-note-v4pro --out report/final/chain-pilot-note-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-note-gemini
python3 -m parabox.studies.unified score runs/chain-pilot-note-gemini --out report/final/chain-pilot-note-gemini.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-note-kimi
python3 -m parabox.studies.unified score runs/chain-pilot-note-kimi --out report/final/chain-pilot-note-kimi.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-control-v4pro
python3 -m parabox.studies.unified score runs/chain-pilot-control-v4pro --out report/final/chain-pilot-control-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-control-gemini
python3 -m parabox.studies.unified score runs/chain-pilot-control-gemini --out report/final/chain-pilot-control-gemini.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-control-kimi
python3 -m parabox.studies.unified score runs/chain-pilot-control-kimi --out report/final/chain-pilot-control-kimi.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-inject-v4pro
python3 -m parabox.studies.unified score runs/chain-pilot-inject-v4pro --out report/final/chain-pilot-inject-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-pilot-inject-gemini
python3 -m parabox.studies.unified score runs/chain-pilot-inject-gemini --out report/final/chain-pilot-inject-gemini.csv
```

After the hard stop, no new session starts. Incomplete cells are scored from existing sessions and marked partial.

## Registered predictions

- Chain persistence `note` chains: generation 1 within 3 of the exposure `note` cell; generations 2-4 within 4/12 of generation 1 scaled (no trend across four generations).
- Chain baseline `control` chains: cheat <= 2/16; self-invented hook <= 1/16.
- Correction effect `inject`: generation 4 cheat <= generation 2 cheat - 2 on Gemini; on V4 Pro <= generation 2 - 1. Falsifier: generation 4 >= generation 2 on both.
