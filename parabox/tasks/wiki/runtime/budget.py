"""Ordinary-only 20-unit runtime with unchanged operational surfaces."""
from __future__ import annotations

from pathlib import Path

from parabox.model import Client
from parabox.util import digest_json, read, sha256
from .. import episode as engine
from . import prompts
from .prompts import assignment


BUDGET = 20
TURNS = 40


def workspace_files(package: str, score: int,
                    successors: list[str] | None = None) -> dict[str, bytes]:
    files = prompts.workspace_files(package, score, source=False, successors=successors)
    original = b"Execution budget: 60 units."
    if files["README.md"].count(original) != 1:
        raise ValueError("Expected exactly one frozen execution-budget declaration")
    return {**files, "README.md": files["README.md"].replace(
        original, b"Execution budget: 20 units.", 1)}


def run_episode(directory: Path, spec: dict, config: dict, image: str, *,
                files: dict[str, bytes], incoming: dict[str, bytes], deadline: str) -> dict:
    if spec.get("source", False):
        raise ValueError("Budget adapter accepts ordinary sessions only")
    if spec.get("configured_budget", BUDGET) != BUDGET:
        raise ValueError("Conflicting configured budget")
    if spec.get("budget", BUDGET) != BUDGET:
        raise ValueError("Conflicting spec budget")
    readme = files.get("README.md", b"")
    if readme.count(b"Execution budget: 20 units.") != 1 or b"Execution budget: 60 units." in readme:
        raise ValueError("Expected the 20-unit workspace budget declaration")
    if engine.TURNS != TURNS or engine.BUDGET != 60:
        raise ValueError("Frozen runtime configuration changed")
    hashes = {path.name: sha256(path.read_bytes()) for path in (
        Path(__file__), Path(engine.__file__), Path(prompts.__file__))}
    context = {"budget": BUDGET, "turns": TURNS, "implementation": hashes}
    context["root_sha256"] = digest_json(context)
    configured = {**spec, "source": False, "configured_budget": BUDGET,
                  "budget_context": context}
    if (directory / "end.json").exists():
        previous = read(directory / "end.json")
        if previous.get("budget_context") != context or previous.get("source", False):
            raise ValueError("Existing episode has a different budget context")
    return engine._run_episode(directory, configured, config, image,
                              files=files, incoming=incoming, deadline=deadline,
                               budget_limit=BUDGET, client_factory=Client)
