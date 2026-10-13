# Contributing

Use Python 3.12+. For code organization, see [architecture](docs/architecture.md).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -t .
```

Container tests also need Podman and the documented image. Default tests must
not call model providers or incur charges.

## Submit a change

1. Explain the change and include relevant tests and their results in your PR.
2. Read the [DCO](DCO), then sign off each commit with your own identity:

   ```sh
   git commit -s -m "Describe the change"
   ```

The sign-off declares that you have the right to submit the contribution;
your name and email become public. No separate CLA or copyright transfer is
required. Original contributions use [MIT](LICENSE); imported material keeps
its license and attribution in [THIRD_PARTY.md](THIRD_PARTY.md).

Never include credentials or unreviewed private transcripts. Preserve existing
experiment evidence; protocol changes need a new run. Disclose substantial AI
assistance and validate its output. This project's code, docs and analysis
include AI assistance.

For bugs, include a minimal reproduction and relevant versions, without secrets.
You may add or correct your public name in [AUTHORS.md](AUTHORS.md).
