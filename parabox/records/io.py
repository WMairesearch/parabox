"""Read-only source verification and non-overwriting evidence export."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .schema import Source, parse, validate


def read_bundle(path: str | Path, *, root: str | Path = ".",
                verify_sources: bool = True, allow_external: bool = False) -> dict:
    bundle = parse(Path(path).read_bytes(), "json")
    validate(bundle)
    if verify_sources:
        loaded = {}
        base = Path(root).resolve()
        for expected in bundle["sources"]:
            path = Path(expected["path"])
            actual = (path if path.is_absolute() else base / path).resolve()
            if not allow_external and not actual.is_relative_to(base):
                raise ValueError("External evidence requires explicit allow_external")
            source = Source(actual, root=base, role=expected["role"], format=expected["format"])
            if source.record != expected:
                raise ValueError(f"Evidence source changed: {expected['path']}")
            loaded[source.id] = source
        validate(bundle, sources=loaded)
    return bundle


def write_bundle(path: str | Path, bundle: dict) -> None:
    validate(bundle)
    destination = Path(path)
    raw = (json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".evidence-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
