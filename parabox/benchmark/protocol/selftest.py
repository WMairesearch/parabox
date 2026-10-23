"""Offline installed-package preparation check, without providers or containers."""

from __future__ import annotations

from pathlib import Path
import tempfile

from parabox.benchmark.protocol.config import default_spec
from parabox.benchmark.prepare import check, prepare
from parabox.benchmark.sources import initial_payload
from parabox.util import save


def selftest() -> dict:
    with tempfile.TemporaryDirectory(prefix="parabox-check-") as temporary:
        root = Path(temporary)
        model = root / "model.json"
        save(model, {"model": "offline-fixture", "api_key_env": "NOT_USED"})
        spec = default_spec({"candidate": str(model)}, str(model), "sha256:" + "0" * 64)
        directory = root / "prepared"
        prepare(directory, spec)
        result = check(directory)
        return {
            "ok": result["ok"], "planned_sessions": result["counts"]["total"],
            "source_blocks": len([initial_payload(block, "full_wiki") for block in range(3)]),
            "model_calls": 0, "containers_started": 0,
        }
