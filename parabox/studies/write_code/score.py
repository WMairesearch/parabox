"""Descriptors for a code-domain write run. Reuses the Lean write stance classifier."""
from __future__ import annotations

from pathlib import Path

from parabox.studies.write import score as S
from parabox.studies.write_code import notes as N


def session_record(directory: Path, row: dict) -> dict | None:
    return S.session_record(directory, row, notes=N)


def records(directory: Path) -> list[dict]:
    return S.records(directory, notes=N)


def descriptors(directory: Path) -> dict:
    return S.descriptors(directory, notes=N)


def report(directory: Path) -> dict:
    return S.report(directory, notes=N)
