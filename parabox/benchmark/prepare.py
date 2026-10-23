"""Offline preparation and integrity checking, never session execution."""

from __future__ import annotations

import json
from pathlib import Path

from parabox.benchmark.protocol.config import validate_spec
from parabox.benchmark.protocol.design import build_plan
from parabox.benchmark.protocol.prompts import core_task
from parabox.util import ROOT, digest_json, read, save, sha256


SOURCE_FILES = (
    "parabox/__init__.py", "parabox/tasks/__init__.py",
    "parabox/tasks/code/__init__.py",
    "parabox/tasks/code/spec/__init__.py",
    "parabox/benchmark/__init__.py", "parabox/benchmark/protocol/__init__.py",
    "parabox/benchmark/protocol/config.py",
    "parabox/benchmark/protocol/design.py", "parabox/benchmark/protocol/prompts.py",
    "parabox/benchmark/prepare.py", "parabox/benchmark/__main__.py",
    "parabox/benchmark/run.py", "parabox/benchmark/sources.py",
    "parabox/benchmark/assets/wiki-founders.json",
    "parabox/execution/__init__.py", "parabox/execution/control/__init__.py",
    "parabox/execution/artifacts.py",
    "parabox/execution/engines.py", "parabox/execution/control/ledger.py",
    "parabox/execution/merge.py",
    "parabox/execution/control/guards.py", "parabox/execution/control/runtime.py",
    "parabox/execution/orchestration.py", "parabox/runner/__init__.py",
    "parabox/runner/session.py",
    "parabox/sandbox.py", "parabox/workspace.py", "parabox/util.py",
    "parabox/model/__init__.py", "parabox/model/chat.py", "parabox/model/gemini.py",
    "parabox/tasks/base.py", "parabox/tasks/code/task.py",
    "parabox/tasks/code/spec/prompts.py", "parabox/tasks/code/spec/problems.py",
    "parabox/tasks/code/verify.py", "parabox/tasks/code/audit.py",
    "parabox/tasks/wiki/__init__.py", "parabox/tasks/wiki/runtime/__init__.py",
    "parabox/tasks/wiki/evaluation/__init__.py",
    "parabox/tasks/wiki/runtime/budget.py",
    "parabox/tasks/wiki/episode.py", "parabox/tasks/wiki/runtime/prompts.py",
    "parabox/tasks/wiki/fixture.py", "parabox/tasks/wiki/runtime/service.py",
    "parabox/tasks/wiki/evaluation/scoring.py", "parabox/tasks/wiki/runtime/helpers.py",
)


def source_bindings() -> dict[str, str]:
    return {str((ROOT / name).resolve()): sha256((ROOT / name).read_bytes())
            for name in SOURCE_FILES}


def model_bindings(spec: dict) -> dict:
    bindings = {}
    for configured in sorted(set([spec["reference_config"], *spec["candidates"].values()])):
        path = Path(configured).resolve()
        raw = path.read_bytes()
        config = json.loads(raw)
        if not isinstance(config, dict) or not isinstance(config.get("model"), str):
            raise ValueError("Expected a model configuration with a model identifier")
        if any(key in config for key in ("api_key", "access_token", "token", "password", "secret")):
            raise ValueError("Use environment-based credentials, not embedded credentials")
        bindings[configured] = {"path": str(path), "sha256": sha256(raw), "model": config["model"]}
    return bindings


def render_materials(plan: dict) -> tuple[dict, dict[str, bytes]]:
    from parabox.tasks.wiki.runtime import budget
    from parabox.tasks.wiki.episode import SYSTEM, TOOLS
    from parabox.tasks.wiki.runtime.prompts import assignment
    from parabox.benchmark.sources import initial_payload

    artifacts, surfaces, seeds = {}, {}, {}

    def store_files(files):
        result = {}
        for name, raw in sorted(files.items()):
            digest = sha256(raw)
            artifacts[digest] = raw
            result[name] = digest
        return result

    for row in plan["sessions"]:
        if row["component"] == "core":
            task = core_task(row)
            prompts = task.prompts_record()["payload"]
            files = task.workspace(row["problem"])
        else:
            prompts = {
                "system": SYSTEM, "task": assignment(row["package"], False), "tools": TOOLS,
            }
            files = budget.workspace_files(row["package"], row["score"], row["successors"])
            if row["position"] == 0:
                key = f"{row['block']}:{row['condition']}"
                if key not in seeds:
                    payload = initial_payload(row["block"], row["condition"], checkpoint_author=0)
                    seeds[key] = {
                        "files": store_files(payload["files"]),
                        "provenance": payload["provenance"],
                        "original_note_sha256": (
                            sha256(payload["files"]["shared/wiki/NOTES.md"])
                            if "shared/wiki/NOTES.md" in payload["files"] else None),
                    }
        surfaces[row["actor"]] = {"prompts": prompts, "workspace": store_files(files)}
    return {"surfaces": surfaces, "wiki_seeds": seeds}, artifacts


def _manifest(spec, plan, models, bindings, materials, artifacts):
    return {
        "schema_version": 1, "state": "prepared_not_authorized",
        "spec_sha256": digest_json(spec), "plan_sha256": digest_json(plan),
        "materials_sha256": digest_json(materials), "sources": bindings, "models": models,
        "artifacts": sorted(artifacts), "image": spec["image"],
        "image_locally_verified": False,
        "execution": {
            "runner": "parabox.benchmark.run.run",
            "core_engine": "parabox.execution.CoreEngine",
            "core_task_factory": "parabox.benchmark.protocol.prompts.core_task",
            "wiki_engine": "parabox.execution.FrozenWikiEngine",
            "wiki_variant": "budget20",
            "ledger_planned": "map each plan.sessions actor to its entire row",
            "ledger_cap": plan["counts"]["total"],
            "requires": ["fresh_authorization", "timezone_aware_deadline",
                         "local_image_id_verification", "verified_source_bindings"],
            "wiki_withdrawal": ("actual predecessor bytes; remove unchanged founder NOTES.md only"
                                if spec["wiki"]["withdraw_after_position"] == 0 else
                                "actual predecessor bytes; preserve agent edits and deletions; no researcher withdrawal"),
            "grading": "separate host-only stage; no grading during prepare/check",
        },
    }
def prepare(directory: Path, spec: dict) -> dict:
    spec = validate_spec(spec)
    plan = build_plan(spec)
    models = model_bindings(spec)
    bindings = source_bindings()
    materials, artifacts = render_materials(plan)
    if source_bindings() != bindings:
        raise ValueError("Implementation changed during preparation")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "spec.json", spec)
    save(directory / "plan.json", plan)
    save(directory / "materials.json", materials)
    for digest, raw in artifacts.items():
        destination = directory / "artifacts" / digest
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(raw)
    manifest = _manifest(spec, plan, models, bindings, materials, artifacts)
    save(directory / "manifest.json", manifest)
    return manifest


def check(directory: Path) -> dict:
    directory = Path(directory)
    manifest = read(directory / "manifest.json")
    spec = validate_spec(read(directory / "spec.json"))
    plan = read(directory / "plan.json")
    materials = read(directory / "materials.json")
    if manifest.get("state") != "prepared_not_authorized":
        raise ValueError("Expected an offline preparation manifest")
    if plan != build_plan(spec):
        raise ValueError("Plan differs from the declared design")
    for label, value in (("spec", spec), ("plan", plan), ("materials", materials)):
        if manifest.get(label + "_sha256") != digest_json(value):
            raise ValueError(f"{label} digest mismatch")
    if manifest.get("sources") != source_bindings():
        raise ValueError("Implementation bindings changed")
    if manifest.get("models") != model_bindings(spec):
        raise ValueError("Model configurations changed")
    expected_materials, artifacts = render_materials(plan)
    if materials != expected_materials or manifest.get("artifacts") != sorted(artifacts):
        raise ValueError("Operational surfaces or source payload bindings changed")
    for digest, raw in artifacts.items():
        stored = (directory / "artifacts" / digest).read_bytes()
        if stored != raw or sha256(stored) != digest:
            raise ValueError("Artifact binding mismatch")
    if manifest.get("image") != spec["image"] or manifest.get("image_locally_verified") is not False:
        raise ValueError("Unexpected image binding or verification claim")
    if manifest.get("execution", {}).get("ledger_cap") != len(plan["sessions"]):
        raise ValueError("Execution cap mismatch")
    if manifest != _manifest(spec, plan, model_bindings(spec), source_bindings(),
                             expected_materials, artifacts):
        raise ValueError("Manifest differs from the execution contract")
    return {"ok": True, "state": "prepared_not_authorized", "counts": plan["counts"],
            "holdout": spec["holdout"], "manifest_sha256": digest_json(manifest)}
