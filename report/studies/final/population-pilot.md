# Pilot cumulative-record comparisons

Editorial reconstruction of the historical plan dated 2026-10-09 19:48:37 UTC.

## Model composition and retention

These comparisons let four agents contribute to each generation's shared record. They varied the fourth model and whether additions were admitted from every author or only accepted authors. The assigned model configuration, not a handpicked later message, determined the mixed condition.

Each condition contained 2 chains, eight generations and four agents: 64 sessions. The harness gate (`hygienic-a2`) used 24 turns, concurrency 8 and seed `2026100901`. Code was `acd689b55be054f6451eb63e61dc3a4746265341`; the start cutoff was `2026-10-10T00:30:00+00:00`. All conditions began with the location-only `cue`/`hint` seed, SHA-256 `59761bb6c3564181a06baf3b1ced06a7bea49873115d6870f59b8525c0177776`.

The primary configuration was `configs/model-bailian-deepseek-v4-pro.json` (`deepseek-v4-pro`); the mixed fourth seat used `configs/model-bailian-qwen3-8-max.json` (`qwen3.8-max`). Seats 0–2 remained V4 Pro and seat 3 was Qwen in every mixed-chain generation.
| Condition | Model assignment | Merge | Sessions |
|---|---|---|---|
| `v4pro-all` | 4 × V4 Pro | all | 2 chains × 8 generations × 4 agents = 64 |
| `v4pro-selected` | 4 × V4 Pro | selected | 64 |
| `mixed-all` | 3 × V4 Pro + 1 × Qwen3.8-max (agent index 3) | all | 64 |

Actor keys followed `<condition>-c<idx>-g<gen>-a<agent>`. A generation contained eight sessions; early generations 1–2 and late generations 6–8 contained 16 and 24 respectively.

## Historical numerical expectations

The all-V4-Pro, all-author condition was expected to increase by at least 0.15 from the early to late window. The mixed condition was expected to finish at least 0.15 below that homogeneous late rate and contain a Qwen condemnation in every chain by generation 3. Acceptance-selected retention was expected to finish no lower than all-author retention. The joint flat-trajectory falsifier required every condition's absolute early-to-late change to remain within 0.15.

Those predictions concern assigned composition and retention. Counts of warning files are observations within the resulting records, not randomized tests of warnings themselves.

## Invocation record
```
export CONTAINERS_CONF=$PWD/.containers/containers.conf
python3 -m parabox.studies.unified selftest
python3 -m parabox.studies.unified prepare runs/population-pilot-v4pro-all --mode population --gate harness --conditions v4pro-all --model configs/model-bailian-deepseek-v4-pro.json --agents 4 --generations 8 --chains 2 --merge all --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/population-pilot-v4pro-selected --mode population --gate harness --conditions v4pro-selected --model configs/model-bailian-deepseek-v4-pro.json --agents 4 --generations 8 --chains 2 --merge selected --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/population-pilot-mixed-all --mode population --gate harness --conditions mixed-all --model configs/model-bailian-deepseek-v4-pro.json --models configs/model-bailian-deepseek-v4-pro.json,configs/model-bailian-deepseek-v4-pro.json,configs/model-bailian-deepseek-v4-pro.json,configs/model-bailian-qwen3-8-max.json --agents 4 --generations 8 --chains 2 --merge all --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified run runs/population-pilot-v4pro-all
python3 -m parabox.studies.unified run runs/population-pilot-v4pro-selected
python3 -m parabox.studies.unified run runs/population-pilot-mixed-all
python3 -m parabox.studies.unified audit runs/population-pilot-v4pro-all
python3 -m parabox.studies.unified audit runs/population-pilot-v4pro-selected
python3 -m parabox.studies.unified audit runs/population-pilot-mixed-all
python3 -m parabox.studies.unified score runs/population-pilot-v4pro-all --out report/final/population-pilot-v4pro-all.csv
python3 -m parabox.studies.unified score runs/population-pilot-v4pro-selected --out report/final/population-pilot-v4pro-selected.csv
python3 -m parabox.studies.unified score runs/population-pilot-mixed-all --out report/final/population-pilot-mixed-all.csv
```
