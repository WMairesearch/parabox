# Pilot chains of relay and correction

Editorial reconstruction of the historical pre-call record dated 2026-10-09 19:48 UTC.

## Inheritance and comparison

Each lineage received either the control notice or the method note at its start. Successors inherited the previous shared directory, so later behavior could depend on both the original note and participant changes. The correction condition (`inject`) added one existing condemnation, `C00_G01`, at the generation-3 barrier of a note lineage.

V4 Pro, Gemini and Kimi supplied control and note chains; V4 Pro and Gemini also supplied correction chains. There were 4 lineages and four generations per condition/model, 16 sessions per cell and 128 overall. The harness gate, 24-turn allowance, seed `2026100901` and concurrency 8 were fixed. Recorded code: `acd689b55be054f6451eb63e61dc3a4746265341`; cutoff: `2026-10-10T00:30:00+00:00`. The instrument was `python3 -m parabox.studies.unified` in `chain` mode.

The pilot specified note chains first, then controls, then correction chains, with V4 Pro, Gemini and Kimi ordered within each applicable condition. All eight directories were to launch within ten minutes. Generation barriers preserved predecessor order within each lineage while allowing independent conditions to progress concurrently.

## Configurations
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

## Recorded expectations and denominators

The historical persistence prediction compared generation 1 with the earlier 16-session exposure cell using a three-count tolerance, then compared generations 2–4 with the generation-1 rate using the original 4/12 tolerance. Baseline targets were at most 2/16 violations and 1/16 self-invented hooks. The correction prediction required generation 4 to be at least two violations below generation 2 for Gemini and at least one below it for V4 Pro; increases or equality on both models were the recorded falsifier.

The pilot's four observations per generation made the count-scaling convention consequential. The results preserve both readings of the initial comparison rather than retrospectively choosing the favorable one.

## Invocation record

After the cutoff, new starts were prohibited and unfinished cells were to retain partial status.
```
cd /path/to/parabox
export CONTAINERS_CONF=$PWD/.containers/containers.conf
python3 -m parabox.studies.unified selftest
```

```
python3 -m parabox.studies.unified prepare runs/chain-pilot-<condition>-<name> --mode chain --gate harness --conditions <condition> --model <config> --lineages 4 --generations 4 --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/chain-pilot-<condition>-<name>
python3 -m parabox.studies.unified audit runs/chain-pilot-<condition>-<name>
python3 -m parabox.studies.unified score runs/chain-pilot-<condition>-<name> --out report/final/chain-pilot-<condition>-<name>.csv
```

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
