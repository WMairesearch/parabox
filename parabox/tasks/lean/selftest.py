"""Run the oracle files through the verifier and the audit inside the image."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from parabox.sandbox import Box, image_exists
from parabox.tasks.base import SessionState
from parabox.tasks.lean.task import IMAGE_DIR, ORACLE_DIR, PROBLEMS, LeanTask, problem_hashes
from parabox.util import sha256

# file, problem, verifier should accept, audit should find a violation
ORACLES = [
    (IMAGE_DIR / "Problems" / "Toy.lean", "toy", False, None),
    (ORACLE_DIR / "toy-genuine.lean", "toy", True, False),
    (ORACLE_DIR / "toy-exploit.lean", "toy", True, True),
    (ORACLE_DIR / "odd-perfect-exploit.lean", "odd_perfect", True, True),
]


def image_problem_hashes(image: str) -> dict[str, str]:
    out = {}
    for name, info in PROBLEMS.items():
        proc = subprocess.run(["podman", "run", "--rm", "--network", "none", image, "cat", f"/opt/parabox/Problems/{info['file']}"],
                              capture_output=True, check=True)
        out[name] = sha256(proc.stdout)
    return out


def selftest() -> dict:
    task = LeanTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    problems = []
    if image_problem_hashes(task.image) != problem_hashes():
        problems.append("problem files in the image differ from the repository")
    rows = []
    scratch = Path(tempfile.mkdtemp(prefix="parabox-selftest-"))
    try:
        for index, (path, problem, accept, violation) in enumerate(ORACLES):
            raw = path.read_bytes()
            work = scratch / f"s{index}"
            (work / "workspace").mkdir(parents=True)
            (work / "workspace" / "Problem.lean").write_bytes(raw)
            state = SessionState(problem=problem, workspace=work / "workspace", meta=work / "meta", shared=True, turn=1)
            box = Box(f"parabox-selftest-{index}", state.workspace, task.image)
            box.start()
            try:
                reply = task.call(box, "submit", {"method": "oracle"}, state)
            finally:
                box.stop()
            accepted = state.submissions[-1]["accepted"]
            row = {"oracle": path.name, "reply": reply.splitlines()[0], "accepted": accepted}
            if accepted != accept:
                problems.append(f"{path.name}: verifier accepted={accepted}, expected {accept}")
            if accept:
                judged = task.audit(raw, problem, work / "audit")
                row.update(violation=judged["violation"], reason=judged["reason"])
                if judged["violation"] is not violation:
                    problems.append(f"{path.name}: audit violation={judged['violation']}, expected {violation}")
            rows.append(row)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"oracles": rows, "problems": problems, "ok": not problems}
