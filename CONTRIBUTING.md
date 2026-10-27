# Contributing

Keep changes focused and reproducible. Explain the problem, the proposed change and the checks you ran in a pull request. For a bug, include a small reproduction and relevant versions with credentials and private content removed.

## Local checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m parabox.benchmark selftest
.venv/bin/python -m unittest discover -s tests -t .
```

Markdown keeps each paragraph on one line; GitHub renders line breaks inside paragraphs in issue and pull request bodies. CI checks this with [mdformat](https://github.com/hukkin/mdformat) using `.mdformat.toml`. To format staged Markdown on every commit:

```sh
.venv/bin/python -m pip install pre-commit
.venv/bin/pre-commit install
```

`.venv/bin/pre-commit run --all-files` formats everything once.

Historical studies are checkout-only. Their limited smoke tests run separately with `.venv/bin/python -m unittest discover -s parabox/studies/tests -t .`.

Python 3.12+ is required. Container tests also need Podman and the documented image. Default tests must not call paid providers. Consult the [experiment design](docs/experiments.md) before changing task or transport contracts. Preserve frozen experiments; protocol changes belong in a new run.

## Sign-off and attribution

Read [DCO 1.1](DCO), then sign off each commit using your own identity:

```sh
git commit -s -m "Describe the change"
```

The sign-off certifies your right to submit the contribution. Your name and email become public. There is no separate CLA or copyright transfer. Original contributions use [MIT](LICENSE); imported material retains its own terms and must be recorded in [THIRD_PARTY.md](THIRD_PARTY.md).

Add or correct your public credit in [AUTHORS.md](AUTHORS.md). Disclose substantial AI assistance and check the resulting work. This repository's code, documentation and analysis include AI assistance.

Never submit credentials or unreviewed private transcripts. Follow [SECURITY.md](SECURITY.md) for sensitive reports.
