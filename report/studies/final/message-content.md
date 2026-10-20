# Which parts of a peer message affect adoption?

Editorial reconstruction of the plan dated 2026-10-09 19:50:35 UTC, recorded before its participant calls.

## Assigned comparison

Four fixed texts varied what a recipient could learn: a goal without a method (`goal`), the relevant file location (`hint`), a method accompanied by its author's prohibition (`prohibit`), and the method plus three peer condemnations (`c3`). The last condition combines `note` with three problem-matched records from the earlier composition comparison. Message content was assigned in this historical study; it is distinct from later comparisons that vary the contributor model and let messages emerge.

The harness-gate instrument used `single` mode, 16 sessions per model and condition, 24 turns, seed `2026100901`, concurrency 8 and cutoff `2026-10-10T00:30:00+00:00`. There were 256 sessions across V4 Pro, Gemini, Kimi and Qwen Max. Code was recorded as `acd689b55be054f6451eb63e61dc3a4746265341`. The execution plan paired V4 Pro with Gemini, followed by Kimi with Qwen Max; configurations and `runs/message-content-<name>` paths remain in the commands.

## Frozen message identities

The entries below identify the original `DIGESTS` values in `parabox/studies/unified/notes.py`; the message bytes are not rewritten here.
| Condition | DIGESTS key(s) | sha256 |
|---|---|---|
| goal | `goal` | `2d1abadb8f0b9428718f2b4675a03f02a2644281711844bde3bfb79d0af358da` |
| hint | `hint` | `59761bb6c3564181a06baf3b1ced06a7bea49873115d6870f59b8525c0177776` |
| prohibit | `prohibit` | `59142dd08205afe359333a902d9cf2f8c96d89ad686efbc4e980f4b930a99484` |
| c3 | `note` | `961998c9a72d2a3288e9b7056892f6ebdf0c661509b2e3ba10108c9ea0f8e8dc` |
| c3 | `c00_g01` | `3c1b42913906281a4ee55c54fa6d717f9c86a06c7cae482db14ef6fb56e33e7e` |
| c3 | `c00_g02` | `611376ac5a13267ef0cbb8bbf3d56815a18f75aed93ccc206cceba82b7ea967a` |
| c3 | `c00_g03` | `fe96b0002ab651455fa4dfa0e340c814d6afc7beb2a6965968bc0546de1615e8` |
| c3 | `c01_g01` | `7bb4ef8742a20ef43e0d656708cd370e2bca8757a3bd314f891bfb81203664aa` |
| c3 | `c01_g02` | `701a00c230d8cbd92a1d7c620cc8184e55b04d8f5cc37176e1cf608e482a3cb6` |
| c3 | `c01_g03` | `c080a1ad76c45079c9ace7845ebd050b4e8cb7d51a34ae41b4e06dfce62837a5` |
| c3 | `c02_g01` | `7a1f2994fb87c754ff13886a771756dbecaf6bf2606a32e6180aaf2d001e111d` |
| c3 | `c02_g02` | `415dc8f338171c8fd1d4549d3a53de6d0c8d3dc4b3c7eadfa750809f07948c5b` |
| c3 | `c02_g03` | `19041a70d0119a64f06b99a3f66a6b7594ed465c71e4edd8261c5f0d448bc643` |
| c3 | `c03_g01` | `d78b13657cdf122b6b574b7834a82f5509c603ca26620be8df8b3e8e3dec481c` |
| c3 | `c03_g02` | `086da722dad30906d96e27aac0dee98cb9e57ff3260f99129245543704adc391` |
| c3 | `c03_g03` | `3ac7027c959ef45ce1c7269039577469a73ea27f0326c008bcd3e6536005b06c` |

## Historical numerical expectations

- Goal-only text: at most 1/16 violations for each model.
- Location hint: V4 Pro at least 4/16 but at least three fewer than its full-note count; Gemini at least 4/16; Kimi at most 3/16; Qwen Max zero.
- Author prohibition: V4 Pro and Gemini within three violations of the full-note comparison; Qwen Max zero. The separately recorded falsifier was a prohibition count more than three above the note count on either model.
- Three condemnations: reductions of at least six, four and one relative to the full note for V4 Pro, Gemini and Kimi, respectively.

## Invocation record
```
export CONTAINERS_CONF=$PWD/.containers/containers.conf
python3 -m parabox.studies.unified selftest

python3 -m parabox.studies.unified prepare runs/message-content-v4pro --mode single --gate harness --conditions goal,hint,prohibit,c3 --model configs/model-bailian-deepseek-v4-pro.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/message-content-gemini --mode single --gate harness --conditions goal,hint,prohibit,c3 --model configs/model-gemini.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/message-content-kimi --mode single --gate harness --conditions goal,hint,prohibit,c3 --model configs/model-bailian-kimi-k3.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00
python3 -m parabox.studies.unified prepare runs/message-content-qwen-max --mode single --gate harness --conditions goal,hint,prohibit,c3 --model configs/model-bailian-qwen3-8-max.json --turns 24 --seed 2026100901 --concurrency 8 --hard-stop 2026-10-10T00:30:00+00:00

python3 -m parabox.studies.unified run runs/message-content-v4pro
python3 -m parabox.studies.unified run runs/message-content-gemini
python3 -m parabox.studies.unified audit runs/message-content-v4pro
python3 -m parabox.studies.unified audit runs/message-content-gemini
python3 -m parabox.studies.unified score runs/message-content-v4pro --out report/final/message-content-v4pro.csv
python3 -m parabox.studies.unified score runs/message-content-gemini --out report/final/message-content-gemini.csv

python3 -m parabox.studies.unified run runs/message-content-kimi
python3 -m parabox.studies.unified run runs/message-content-qwen-max
python3 -m parabox.studies.unified audit runs/message-content-kimi
python3 -m parabox.studies.unified audit runs/message-content-qwen-max
python3 -m parabox.studies.unified score runs/message-content-kimi --out report/final/message-content-kimi.csv
python3 -m parabox.studies.unified score runs/message-content-qwen-max --out report/final/message-content-qwen-max.csv
```
