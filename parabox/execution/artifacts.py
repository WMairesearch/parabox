"""Explicit shared-state policies and content lineage."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath


def manifest(files: dict[str, bytes]) -> dict[str, str]:
    if len(files) > 4096:
        raise ValueError("Too many artifacts")
    result = {}
    total = 0
    for name, content in sorted(files.items()):
        path = PurePosixPath(name)
        if (not name or not path.parts or path.is_absolute() or ".." in path.parts or str(path) != name
                or "\x00" in name or len(path.parts) > 32 or not isinstance(content, bytes)):
            raise ValueError("Artifacts require confined canonical paths and bytes")
        total += len(content)
        if len(content) > 4 * 1024 * 1024 or total > 16 * 1024 * 1024:
            raise ValueError("Artifact byte limit exceeded")
        if any(str(parent) in files for parent in path.parents if str(parent) != "."):
            raise ValueError("Artifact path is both a file and a parent")
        result[name] = hashlib.sha256(content).hexdigest()
    return result


@dataclass
class Outcome:
    end: dict
    files: dict[str, bytes]
    accepted: bool | None = None


def handoff(previous: dict[str, bytes], outcomes: list[Outcome], *,
            policy: str) -> tuple[dict[str, bytes], dict]:
    before = manifest(previous)
    for outcome in outcomes:
        manifest(outcome.files)
        if outcome.end.get("normal") is not True:
            raise RuntimeError("Abnormal execution cannot supply shared state")
    if policy == "replace":
        if len(outcomes) != 1:
            raise ValueError("Replacement requires exactly one predecessor")
        files = dict(outcomes[0].files)
        native = {}
    elif policy in ("population_all", "population_accepted"):
        from parabox.studies.population.merge import merge_record
        if policy == "population_accepted" and any(
                type(outcome.accepted) is not bool for outcome in outcomes):
            raise ValueError("Acceptance-gated merge requires explicit final acceptance")
        files, native = merge_record(previous, [
            {"agent": index, "actor": outcome.end.get("actor"),
             "accepted": outcome.accepted, "received": previous, "written": outcome.files}
            for index, outcome in enumerate(outcomes)],
            "selected" if policy == "population_accepted" else "all")
    else:
        raise ValueError(f"Unsupported handoff policy: {policy}")
    after = manifest(files)
    return files, {"policy": policy, "incoming": before, "outgoing": after,
                   "contributors": [{"actor": outcome.end.get("actor"),
                                     "files": manifest(outcome.files)}
                                    for outcome in outcomes],
                   "deleted": sorted(set(before) - set(after)),
                   "modified": sorted(name for name in before.keys() & after.keys()
                                      if before[name] != after[name]),
                   "native": native}
