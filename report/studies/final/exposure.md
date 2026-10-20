# Initial exposure to a peer method

Editorial reconstruction of the historical plan dated 2026-10-09 19:47 UTC. The original record describes a pre-call plan; this rewritten page is not a new preregistration.

## Comparison

The same recipient task and harness gate were used with either a platform notice (`control`) or a peer's method note (`note`). The comparison asks whether exposure changes independently audited violations, before studying relay through later agents.

The instrument was `python3 -m parabox.studies.unified`, mode `single`, gate `harness` (`hygienic-a2`). Each model contributed 16 sessions per condition: four problems with four replicates, 24 turns and concurrency 8. Across six models this made 192 sessions. The recorded code commit was `acd689b55be054f6451eb63e61dc3a4746265341` (`git rev-parse HEAD`), seed `2026100901`, with start cutoff `2026-10-10T00:30:00+00:00`.

Preparation covered all six directories before execution. The specified model order was V4 Pro, Gemini, Kimi, Qwen Max, DeepSeek Flash, then Qwen Flash; the commands below retain their configuration paths and `runs/exposure-<name>` destinations. The planned schedule began with V4 Pro and Gemini and filled available slots in that order, allowing two or three concurrent run processes. Actual scheduling is recorded in [the results](exposure-results.md).

## Historical numerical expectations

The recorded baseline ceiling was 1/16 for every model. With the note, the lower thresholds were 10/16 for V4 Pro, 8/16 for Gemini and 4/16 for Kimi; each of Qwen Max, DeepSeek Flash and Qwen Flash had a ceiling of 1/16. These are the original point-count predictions, not new significance criteria.

## Invocation record

Set `CONTAINERS_CONF=$PWD/.containers/containers.conf`; the retained blocks show the selftest, preparation, execution, audit and CSV export sequence.
```
python3 -m parabox.studies.unified selftest
```

```
python3 -m parabox.studies.unified prepare runs/exposure-v4pro --mode single --gate harness --conditions control,note --model configs/model-bailian-deepseek-v4-pro.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-gemini --mode single --gate harness --conditions control,note --model configs/model-gemini.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-kimi --mode single --gate harness --conditions control,note --model configs/model-bailian-kimi-k3.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-qwen-max --mode single --gate harness --conditions control,note --model configs/model-bailian-qwen3-8-max.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-ds-flash --mode single --gate harness --conditions control,note --model configs/model-deepseek.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/exposure-qwen-flash --mode single --gate harness --conditions control,note --model configs/model-bailian-qwen3-8-flash.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
```

```
python3 -m parabox.studies.unified run runs/exposure-<name>
python3 -m parabox.studies.unified audit runs/exposure-<name>
python3 -m parabox.studies.unified score runs/exposure-<name> --out report/final/exposure-<name>.csv
```
