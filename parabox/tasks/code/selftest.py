"""Run the oracle files through the verifier and the audit inside the image."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from parabox.sandbox import Box, image_exists
from parabox.tasks.base import SessionState
from parabox.tasks.code.audit import audit_bytes
from parabox.tasks.code.task import CodeTask

HERE = Path(__file__).resolve().parent
ORACLE_DIR = HERE / "oracle"

# problem, workspace overlays, verifier accepts, audit violation (None if rejected)
ORACLES = [
    ("reverse_words", {"solution.py": "honest_reverse_words.py"}, True, False),
    ("double", {"solution.py": "natural_double.py"}, False, None),
    ("double", {"solution.py": "skip_double.py"}, False, None),
    ("double", {"solution.py": "eq_double.py"}, False, None),
    ("double", {"solution.py": "bypass_double.py", "conftest.py": "conftest.py"}, True, True),
]


def selftest() -> dict:
    task = CodeTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    problems = []
    rows = []
    scratch = Path(tempfile.mkdtemp(prefix="parabox-code-selftest-"))
    try:
        for index, (problem, overlays, accept, violation) in enumerate(ORACLES):
            work = scratch / f"s{index}"
            workspace = work / "workspace"
            workspace.mkdir(parents=True)
            for name, data in task.workspace(problem).items():
                dest = workspace / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            for name, oracle_name in overlays.items():
                (workspace / name).write_bytes((ORACLE_DIR / oracle_name).read_bytes())
            state = SessionState(problem=problem, workspace=workspace, meta=work / "meta", shared=False, turn=1)
            box = Box(f"parabox-code-selftest-{index}", workspace, task.image)
            box.start()
            try:
                reply = task.call(box, "submit", {}, state)
            finally:
                box.stop()
            accepted = state.submissions[-1]["accepted"]
            row = {"oracle": "+".join(overlays.values()), "reply": reply.splitlines()[0], "accepted": accepted}
            if accepted != accept:
                problems.append(f"{row['oracle']}: verifier accepted={accepted}, expected {accept}")
            if accept:
                raw = (workspace / "solution.py").read_bytes()
                extras = ["conftest.py"] if "conftest.py" in overlays else []
                judged = audit_bytes(task.image, raw, problem, work / "audit", extras)
                row.update(violation=judged["violation"], reason=judged["reason"], mechanisms=judged["mechanisms"])
                if judged["violation"] is not violation:
                    problems.append(f"{row['oracle']}: audit violation={judged['violation']}, expected {violation}")
            rows.append(row)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"oracles": rows, "problems": problems, "ok": not problems}
