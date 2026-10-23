"""Optional host-only grading of saved ordinary wiki sessions."""
from pathlib import Path

from parabox.tasks.wiki import grader
from parabox.util import read, save
from .prepare import check
from .run import verify_image


def grade(directory: Path, *, image_verifier=None):
    directory = Path(directory).resolve()
    verified = check(directory)
    execution = directory / "execution"
    ended = read(execution / "end.json")
    if ended["manifest_sha256"] != verified["manifest_sha256"]:
        raise ValueError("Execution differs from prepared study")
    image = read(directory / "spec.json")["image"]
    (image_verifier or verify_image)(image)
    rows = []
    for row in read(directory / "plan.json")["sessions"]:
        target = execution / "sessions" / row["actor"]
        result = {"actor": row["actor"], "status": "unavailable"}
        try:
            if ended["states"][row["actor"]]["state"] != "completed":
                raise ValueError("Execution did not complete normally")
            end = read(target / "end.json")
            if any(end.get(key) != value for key, value in row.items()):
                raise ValueError("Terminal identity mismatch")
            result.update(status="graded", result=grader.session(target, image=image,
                                                                 cache=execution / "grading-cache"))
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            result.update(status="unavailable", reason=type(error).__name__)
        rows.append(result)
    result = {"manifest_sha256": verified["manifest_sha256"], "sessions": rows,
              "graded": sum(row["status"] == "graded" for row in rows)}
    save(execution / "grading.json", result)
    return result
