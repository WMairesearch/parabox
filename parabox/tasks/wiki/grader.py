"""Host-only grading with an explicit sandbox image and caller-owned cache."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import re

from parabox.util import digest_json, now, read, save, sha256
from parabox.workspace import read_regular
from . import evaluator, fixture
from .runtime import helpers
from .evaluation import scoring
from .evaluation.scoring import submission_score


def implementation_hashes() -> dict[str, str]:
    paths = [Path(__file__), *(Path(module.__file__) for module in
                              (evaluator, fixture, helpers, scoring))]
    return {path.name: sha256(path.read_bytes()) for path in paths}


def normalize_image(image: str) -> str:
    if not isinstance(image, str) or not re.fullmatch(r"(sha256:)?[0-9a-f]{64}", image):
        raise ValueError("An immutable image digest is required")
    return "sha256:" + image.removeprefix("sha256:")


def grade(raw: bytes, package: str, *, image: str, cache: Path) -> dict:
    image = normalize_image(image)
    cases = fixture.cases(package)
    binding = {"code_sha256": sha256(raw), "cases_sha256": digest_json(cases),
               "image": image, "implementation": implementation_hashes()}
    key = digest_json(binding)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        output = cache / f"{key}.json"
        if output.exists():
            record = read(output)
            if record["binding"] != binding:
                raise RuntimeError("Cached grading binding changed")
            if record["score"] != submission_score(record["evaluation"]["cases"], True):
                raise RuntimeError("Cached grading score differs from case outcomes")
            return record
        evaluation = evaluator.evaluate(image, raw, cases, cache / key)
        score = submission_score(evaluation["cases"], True)
        record = {"binding": binding, "evaluation": evaluation, "score": score,
                  "graded_at": now()}
        save(output, record)
        return record


def validate_fixtures(*, image: str, cache: Path, workers: int = 1) -> dict:
    if type(workers) is not int or not 1 <= workers <= 6:
        raise ValueError("Expected one to six workers")
    specs = [(package, score) for package in fixture.packages()
             for score in (30, 60, 90, 100)]

    def check(spec):
        package, expected = spec
        raw = (fixture.reference_source(package) if expected == 100 else
               fixture.starter_source(package, expected))
        result = grade(raw.encode(), package, image=image, cache=cache)
        if result["score"]["passed"] != expected:
            raise RuntimeError(f"Starter score mismatch for {package}/{expected}")
        return {"package": package, "expected": expected,
                "actual": result["score"]["passed"], "binding": result["binding"]}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(check, specs))
    return {"verified": True, "checked_at": now(), "fixtures": rows}


def session(directory: Path, *, image: str, cache: Path) -> dict:
    directory = Path(directory)
    image = normalize_image(image)
    implementation = implementation_hashes()
    end_raw = read_regular(directory, "end.json")
    end = json.loads(end_raw)
    if not end.get("shutdown_verified") or end.get("source"):
        raise ValueError("Expected ended ordinary session")
    package = end["package"]
    bindings = {}

    def evaluate(snapshot):
        digest = snapshot.get("sha256")
        if not digest:
            return {"code_score": 0, "passed": 0, "missing": True}
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(character not in "0123456789abcdef" for character in digest)):
            raise ValueError("Invalid candidate artifact digest")
        raw = read_regular(directory, "meta/artifacts/" + digest)
        if sha256(raw) != digest:
            raise RuntimeError("Candidate archive changed")
        result = grade(raw, package, image=image, cache=cache)
        bindings[digest] = result["binding"]
        return result["score"]

    initial = evaluate(end["initial_solution"])
    final = evaluate(end["final_solution"])
    first_change = None
    for path in sorted((directory / "meta/actions").glob("*.json")):
        action = read(path)
        if action["before"]["solution"].get("sha256") != action["after"]["solution"].get("sha256"):
            first_change = {"turn": action["turn"], "budget_used": action["charge"]["used"],
                            "score": evaluate(action["after"]["solution"])}
            break
    submitted = end.get("normal") and end.get("action") == "submit"
    record = {"actor": end["actor"], "model": end["model"], "package": package,
              "initial_score": initial, "final_score": final, "first_change": first_change,
              "earned_score": final["code_score"] if submitted else 0 if end.get("normal") else None,
              "qualified": bool(submitted and final["passed"] >= 60) if end.get("normal") else None,
              "normal": end.get("normal"), "action": end.get("action"),
              "budget_used": end["budget_used"], "end_sha256": digest_json(end),
              "end_file_sha256": sha256(end_raw), "image": image,
              "implementation": implementation, "grading_bindings": bindings,
              "graded_at": now()}
    if read_regular(directory, "end.json") != end_raw:
        raise RuntimeError("Session ending changed during grading")
    if implementation_hashes() != implementation:
        raise RuntimeError("Grading implementation changed during grading")
    save(directory / "grading.json", record)
    return record
