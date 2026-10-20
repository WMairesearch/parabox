# Replicating relay and correction

Editorial reconstruction of the historical pre-call record dated 2026-10-10 00:34 UTC.

## Inheritance and comparison

Each lineage received either the control notice or the method note at its start. Successors inherited the previous shared directory, so later behavior could depend on both the original note and participant changes. The correction condition (`inject`) added one existing condemnation, `C00_G01`, at the generation-3 barrier of a note lineage.

V4 Pro, Gemini and Kimi supplied control and note chains; V4 Pro and Gemini also supplied correction chains. There were 10 lineages and four generations per condition/model, 40 sessions per cell and 320 overall. The harness gate, 24-turn allowance, seed `2026100901` and concurrency 8 were fixed. Recorded code: `f9a745247142cab09cd27262d8920d2ecdee34d5`; cutoff: `2026-10-10T04:30:00+00:00`. The instrument was `python3 -m parabox.studies.unified` in `chain` mode.

The replication moved V4 Pro to the official DeepSeek endpoint, `api.deepseek.com`, model `deepseek-v4-pro`, using `configs/model-deepseek-v4-pro.json` rather than Bailian. Its selftest returned `{"ok": true, "problems": []}`. Preparation and launch of the eight directories were scheduled within 15 minutes. Generation barriers preserved predecessor order within each lineage while allowing independent conditions to progress concurrently.

## Configurations
| Directory | Condition | Model name | Config |
|---|---|---|---|
| `runs/chain-replication-note-v4pro` | `note` | v4pro | `configs/model-deepseek-v4-pro.json` |
| `runs/chain-replication-note-gemini` | `note` | gemini | `configs/model-gemini.json` |
| `runs/chain-replication-note-kimi` | `note` | kimi | `configs/model-bailian-kimi-k3.json` |
| `runs/chain-replication-control-v4pro` | `control` | v4pro | `configs/model-deepseek-v4-pro.json` |
| `runs/chain-replication-control-gemini` | `control` | gemini | `configs/model-gemini.json` |
| `runs/chain-replication-control-kimi` | `control` | kimi | `configs/model-bailian-kimi-k3.json` |
| `runs/chain-replication-inject-v4pro` | `inject` | v4pro | `configs/model-deepseek-v4-pro.json` |
| `runs/chain-replication-inject-gemini` | `inject` | gemini | `configs/model-gemini.json` |

## Recorded expectations and denominators

The historical persistence prediction compared generation 1 with the earlier 16-session exposure cell using a three-count tolerance, then compared generations 2–4 with the generation-1 rate using the original 4/12 tolerance. Baseline targets were at most 2/16 violations and 1/16 self-invented hooks. The correction prediction required generation 4 to be at least two violations below generation 2 for Gemini and at least one below it for V4 Pro; increases or equality on both models were the recorded falsifier.

The replication changed the generation denominator to 10 and the cell total to 40; the contemporaneous population extension used 40 sessions per generation. The carried-over count tolerances therefore require the explicit scaling documented in the results, rather than silently treating 16 and 40 as interchangeable.

## Invocation record

After the 2026-10-10 04:30 UTC cutoff, new starts were prohibited and unfinished cells were to retain partial status.
```
cd /path/to/parabox
export CONTAINERS_CONF=$PWD/.containers/containers.conf
python3 -m parabox.studies.unified selftest
```

```
python3 -m parabox.studies.unified prepare runs/chain-replication-<condition>-<model> --mode chain --gate harness --conditions <condition> --model <config> --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
```

```
python3 -m parabox.studies.unified prepare runs/chain-replication-note-v4pro --mode chain --gate harness --conditions note --model configs/model-deepseek-v4-pro.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-note-gemini --mode chain --gate harness --conditions note --model configs/model-gemini.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-note-kimi --mode chain --gate harness --conditions note --model configs/model-bailian-kimi-k3.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-control-v4pro --mode chain --gate harness --conditions control --model configs/model-deepseek-v4-pro.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-control-gemini --mode chain --gate harness --conditions control --model configs/model-gemini.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-control-kimi --mode chain --gate harness --conditions control --model configs/model-bailian-kimi-k3.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-inject-v4pro --mode chain --gate harness --conditions inject --model configs/model-deepseek-v4-pro.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
python3 -m parabox.studies.unified prepare runs/chain-replication-inject-gemini --mode chain --gate harness --conditions inject --model configs/model-gemini.json --lineages 10 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T04:30:00+00:00
```

```
python3 -m parabox.studies.unified run runs/chain-replication-note-v4pro
python3 -m parabox.studies.unified run runs/chain-replication-note-gemini
python3 -m parabox.studies.unified run runs/chain-replication-note-kimi
python3 -m parabox.studies.unified run runs/chain-replication-control-v4pro
python3 -m parabox.studies.unified run runs/chain-replication-control-gemini
python3 -m parabox.studies.unified run runs/chain-replication-control-kimi
python3 -m parabox.studies.unified run runs/chain-replication-inject-v4pro
python3 -m parabox.studies.unified run runs/chain-replication-inject-gemini
python3 -m parabox.studies.unified audit runs/chain-replication-note-v4pro
python3 -m parabox.studies.unified score runs/chain-replication-note-v4pro --out report/final/chain-replication-note-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-replication-note-gemini
python3 -m parabox.studies.unified score runs/chain-replication-note-gemini --out report/final/chain-replication-note-gemini.csv
python3 -m parabox.studies.unified audit runs/chain-replication-note-kimi
python3 -m parabox.studies.unified score runs/chain-replication-note-kimi --out report/final/chain-replication-note-kimi.csv
python3 -m parabox.studies.unified audit runs/chain-replication-control-v4pro
python3 -m parabox.studies.unified score runs/chain-replication-control-v4pro --out report/final/chain-replication-control-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-replication-control-gemini
python3 -m parabox.studies.unified score runs/chain-replication-control-gemini --out report/final/chain-replication-control-gemini.csv
python3 -m parabox.studies.unified audit runs/chain-replication-control-kimi
python3 -m parabox.studies.unified score runs/chain-replication-control-kimi --out report/final/chain-replication-control-kimi.csv
python3 -m parabox.studies.unified audit runs/chain-replication-inject-v4pro
python3 -m parabox.studies.unified score runs/chain-replication-inject-v4pro --out report/final/chain-replication-inject-v4pro.csv
python3 -m parabox.studies.unified audit runs/chain-replication-inject-gemini
python3 -m parabox.studies.unified score runs/chain-replication-inject-gemini --out report/final/chain-replication-inject-gemini.csv
```
