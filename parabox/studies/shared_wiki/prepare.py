"""Offline source, model, founder, and participant-material binding."""
from __future__ import annotations

import json
from pathlib import Path

from parabox.benchmark import sources
from parabox.tasks.wiki import episode
from parabox.tasks.wiki.runtime import budget
from parabox.tasks.wiki.runtime.prompts import assignment
from parabox.util import ROOT, digest_json, read, save, sha256
from parabox.workspace import read_regular
from .design import build_plan, validate_spec


def source_bindings() -> dict:
    names = {"parabox/__init__.py", "parabox/studies/__init__.py", "parabox/tasks/__init__.py",
             "parabox/benchmark/__init__.py", "parabox/benchmark/sources.py",
             "parabox/benchmark/assets/wiki-founders.json", "parabox/sandbox.py",
             "parabox/workspace.py", "parabox/util.py"}
    for directory in ("parabox/studies/shared_wiki", "parabox/tasks/wiki",
                      "parabox/execution", "parabox/model"):
        names.update(str(path.relative_to(ROOT)) for path in (ROOT / directory).glob("*.py"))
    return {str((ROOT / name).resolve()): sha256((ROOT / name).read_bytes()) for name in sorted(names)}


def model_bindings(spec: dict) -> dict:
    result = {}
    for name, configured in spec["models"].items():
        path = Path(configured).resolve()
        raw = path.read_bytes()
        config = json.loads(raw)
        if not isinstance(config, dict) or not isinstance(config.get("model"), str) or not config["model"]:
            raise ValueError("Model configuration needs a nonempty model identifier")
        if any(key in config for key in ("api_key", "access_token", "token", "password", "secret")):
            raise ValueError("Use environment-based credentials, not embedded secrets")
        result[name] = {"path": str(path), "sha256": sha256(raw), "model": config["model"]}
    return result


def render_materials(spec, plan):
    artifacts, surfaces, founders = {}, {}, {}

    def store(files):
        hashes = {}
        for name, raw in sorted(files.items()):
            digest = sha256(raw)
            artifacts[digest] = raw
            hashes[name] = digest
        return hashes

    for block in spec["blocks"]:
        for condition in spec["conditions"]:
            payload = sources.initial_payload(block, condition, checkpoint_author=0)
            founders[f"{block}:{condition}"] = {**payload, "files": store(payload["files"])}
    for row in plan["sessions"]:
        surfaces[row["actor"]] = {
            "prompts": {"system": episode.SYSTEM, "user": assignment(row["package"]), "tools": episode.TOOLS},
            "workspace": store(budget.workspace_files(row["package"], row["score"], row["successors"]))}
    return {"surfaces": surfaces, "founders": founders}, artifacts


def manifest(spec, plan, models, bindings, materials, artifacts):
    return {"schema_version": 1, "state": "prepared_not_authorized",
            "spec_sha256": digest_json(spec), "plan_sha256": digest_json(plan),
            "materials_sha256": digest_json(materials), "models": models, "sources": bindings,
            "artifacts": sorted(artifacts), "image": spec["image"], "image_locally_verified": False,
            "session_cap": plan["counts"]["total"], "transport": spec["transport"],
            "execution": "Explicit exact-cap authorization and future timezone-aware deadline; no resume or retries"}


def prepare(directory: Path, spec: dict) -> dict:
    spec = validate_spec(spec)
    spec["models"] = {name: str(Path(path).resolve()) for name, path in spec["models"].items()}
    plan = build_plan(spec)
    models, bindings = model_bindings(spec), source_bindings()
    materials, artifacts = render_materials(spec, plan)
    if bindings != source_bindings() or models != model_bindings(spec):
        raise ValueError("Sources or model configs changed during preparation")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for name, value in (("spec", spec), ("plan", plan), ("materials", materials)):
        save(directory / f"{name}.json", value)
    for digest, raw in artifacts.items():
        destination = directory / "artifacts" / digest
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(raw)
    record = manifest(spec, plan, models, bindings, materials, artifacts)
    save(directory / "manifest.json", record)
    return record


def check(directory: Path) -> dict:
    directory = Path(directory)
    spec = validate_spec(read(directory / "spec.json"))
    plan = build_plan(spec)
    materials, artifacts = render_materials(spec, plan)
    expected = manifest(spec, plan, model_bindings(spec), source_bindings(), materials, artifacts)
    if (read(directory / "manifest.json") != expected or read(directory / "plan.json") != plan
            or read(directory / "materials.json") != materials):
        raise ValueError("Prepared source, configuration, plan, or surface binding changed")
    for digest, raw in artifacts.items():
        if read_regular(directory, "artifacts/" + digest) != raw:
            raise ValueError("Prepared artifact changed")
    return {"ok": True, "state": "prepared_not_authorized", "counts": plan["counts"],
            "manifest_sha256": digest_json(expected)}
