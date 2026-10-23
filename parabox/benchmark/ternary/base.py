"""Host-side helpers for the ternary task runtime."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from parabox.model import Client, assistant_message, parse_args
from parabox.sandbox import Box, Limits
from parabox.util import now, save, sha256
from parabox.workspace import read_regular, write_regular

from . import fixture


CALL_LIMIT = 20


def archive(meta: Path, raw: bytes) -> str:
    digest = sha256(raw)
    destination = meta / "artifacts" / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(raw)
    return digest


def capture(workspace: Path, meta: Path, target: list[int]) -> tuple[bytes, dict]:
    try:
        raw = read_regular(workspace, "submission.json", limit=65536)
        record = {"sha256": archive(meta, raw), "feedback": fixture.evaluate(raw, target)}
        try:
            record["length"] = len(json.loads(raw))
        except (ValueError, TypeError, RecursionError):
            record["length"] = None
        return raw, record
    except (OSError, ValueError):
        return b"", {"sha256": None, "length": None,
                     "feedback": {"error": "Invalid submission file"}}


def shutdown(box: Box) -> dict:
    box.stop()
    result = subprocess.run(["podman", "container", "exists", box.name],
                            capture_output=True, text=True, timeout=10)
    return {"verified": result.returncode == 1, "checked_at": now(),
            "exists_exit_code": result.returncode}
