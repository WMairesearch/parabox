"""Offline projection of executed ternary and function runs into a portable evidence bundle."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from parabox.util import digest_json, read, sha256

from .records import load

KNOWN_ERRORS = ("Three consecutive truncated or tool-free responses", "Generation interrupted")


def _error_type(error):
    if error is None or error in KNOWN_ERRORS:
        return error
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\(", error)
    return match.group(1) if match else "unrecognized"


def _model(path: Path, digest: str, alias: str, secrets: set[str]) -> dict:
    summary = {"alias": alias, "config_sha256": digest}
    try:
        raw = path.read_bytes()
    except OSError:
        return {**summary, "config_available": False}
    if sha256(raw) != digest:
        raise ValueError(f"Model configuration changed since preparation: {alias}")
    config = json.loads(raw)
    if config.get("api_key_env") and os.environ.get(config["api_key_env"]):
        secrets.add(os.environ[config["api_key_env"]])
    return {**summary, "config_available": True, "model": config.get("model"),
            "wire": config.get("wire", "chat"), "request_body": config.get("request_body"),
            "endpoint_host": urlparse(config.get("base_url") or "").hostname}


def _relative_sources(bindings: dict) -> dict:
    from parabox.benchmark.prepare import SOURCE_FILES

    result = {}
    for name in SOURCE_FILES:
        matches = [digest for path, digest in bindings.items() if path.endswith("/" + name)]
        if len(matches) != 1:
            raise ValueError(f"Source binding missing or ambiguous: {name}")
        result[name] = matches[0]
    return result


def _ternary(directory: Path, rows: list[dict], secrets: set[str]) -> dict:
    from parabox.benchmark.ternary.run import source_hashes, validate_spec

    registration = read(directory / "registration.json")
    if (directory / "registration.sha256").read_text().strip() != digest_json(registration):
        raise ValueError("Registration changed")
    authorization = directory / "authorization.json"
    if not authorization.exists() or read(authorization).get("registration_sha256") != digest_json(registration):
        raise ValueError("Run was not executed under this registration")
    spec = validate_spec(registration["spec"])
    chains = {row["chain"]: row for row in registration["chains"]}
    for row in rows:
        planned = chains.get(row["chain"])
        if planned is None or any(row[key] != planned[key] for key in ("model", "prefix", "condition")):
            raise ValueError(f"Session outside the registered schedule: {row['id']}")
        if row["seats"] != spec["seats"]:
            raise ValueError("Session population differs from registration")
        row["end"]["error"] = _error_type(row["end"].get("error"))
    results = directory / "results.json"
    return {
        "experiment": "ternary", "protocol": "ternary-" + spec["protocol"],
        "spec": {**spec, "models": {alias: f"configs/{alias}.json" for alias in spec["models"]}},
        "published_profile": spec["profile"] == "historical-v1" and spec["transport_profile"] == "json-900-v1",
        "planned_sessions": registration["session_cap"], "exported_sessions": len(rows),
        "models": [_model(Path(binding["path"]), binding["sha256"], alias, secrets)
                   for alias, binding in sorted(registration["models"].items())],
        "registration_sha256": digest_json(registration),
        "target_sha256": digest_json(registration["target"]),
        "transport": registration["transport"],
        "sources": registration["sources"],
        "sources_match_installed": registration["sources"] == source_hashes(),
        "chain_errors": read(results)["chain_errors"] if results.exists() else None,
    }


def _function(directory: Path, rows: list[dict], secrets: set[str]) -> dict:
    from parabox.benchmark.prepare import source_bindings
    from parabox.benchmark.protocol.design import build_plan

    manifest, spec = read(directory / "manifest.json"), read(directory / "spec.json")
    plan, materials = read(directory / "plan.json"), read(directory / "materials.json")
    for label, value in (("spec", spec), ("plan", plan), ("materials", materials)):
        if manifest.get(label + "_sha256") != digest_json(value):
            raise ValueError(f"{label} digest mismatch")
    if not spec.get("function_profile") or any(row["component"] != "core" for row in plan["sessions"]):
        raise ValueError("Only function and ternary runs can be exported")
    if plan != build_plan(spec):
        raise ValueError("Plan differs from the declared design")
    bound = digest_json(manifest)
    for name, missing in (("end.json", "Run was not executed under this manifest"),
                          ("grading.json", "Run `grade` before export")):
        path = directory / "execution" / name
        if not path.exists() or read(path).get("manifest_sha256") != bound:
            raise ValueError(missing)
    grading = read(directory / "execution/grading.json")
    aliases = {path: alias for alias, path in spec["candidates"].items()}
    if spec["reference_config"] is not None:
        aliases.setdefault(spec["reference_config"], "reference")
    models = {configured: _model(Path(binding["path"]), binding["sha256"], aliases[configured], secrets)
              for configured, binding in manifest["models"].items()}
    assignments = {(row["chain"], row["generation"], row["seat"]): row for row in plan["sessions"]}
    for row in rows:
        assignment = assignments[row["chain"], row["generation"], row["seat"]]
        row["participant_model"] = manifest["models"][assignment["model_config"]]["model"]
    sources = _relative_sources(manifest["sources"])
    return {
        "experiment": "function", "protocol": "function-" + spec["function_profile"],
        "spec": {**spec, "candidates": {alias: f"configs/{alias}.json" for alias in spec["candidates"]},
                 "reference_config": None if spec["reference_config"] is None else "configs/reference.json"},
        "published_profile": True,
        "planned_sessions": plan["counts"]["total"], "exported_sessions": len(rows),
        "models": sorted(models.values(), key=lambda item: item["alias"]),
        "manifest_sha256": bound, "image": spec["image"],
        "grading": {"image": grading["image"], "graded": grading["graded"],
                    "unavailable": grading["unavailable"], "implementation": grading["implementation"]},
        "sources": sources,
        "sources_match_installed": sources == _relative_sources(source_bindings()),
    }


def export(directories: list[Path], output: Path) -> dict:
    output = Path(output)
    if output.exists():
        raise ValueError("Evidence destination already exists")
    rows, runs, secrets = [], [], set()
    forbidden = {str(Path.home())}
    for directory in directories:
        directory = Path(directory).resolve()
        forbidden.add(str(directory))
        manifest, loaded = load(directory)
        if manifest["schema"] != "local-run":
            raise ValueError(f"Expected an executed run directory: {directory.name}")
        if (directory / "registration.json").exists():
            run = _ternary(directory, loaded, secrets)
            forbidden.update(str(Path(binding["path"]).parent)
                             for binding in read(directory / "registration.json")["models"].values())
        else:
            run = _function(directory, loaded, secrets)
            forbidden.update(str(Path(binding["path"]).parent)
                             for binding in read(directory / "manifest.json")["models"].values())
        run["normal_sessions"] = sum(row["end"].get("normal") is True for row in loaded)
        runs.append(run)
        rows.extend(loaded)
    identities = Counter(row["id"] for row in rows)
    if duplicated := sorted(identity for identity, count in identities.items() if count > 1):
        raise ValueError(f"Runs overlap; duplicate session {duplicated[0]}")
    files = {
        "sessions.jsonl": "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
                                  for row in sorted(rows, key=lambda row: row["id"])),
        "protocols.json": json.dumps({
            "runs": runs,
            "content": "Per-session outcomes, evaluator feedback and source digests; transcripts, "
                       "workspaces and participant code remain in the source runs.",
            "errors": "Ternary session errors are reduced to the exception type.",
        }, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    }
    text = "".join(files.values())
    for value in sorted(forbidden | secrets, key=len, reverse=True):
        if len(value) >= 5 and value in text:
            raise ValueError("Export would contain a host path or credential; nothing was written")
    output.mkdir(parents=True)
    for name, content in files.items():
        (output / name).write_text(content)
    planned = sum(run["planned_sessions"] for run in runs)
    manifest = {"schema": "parabox-evidence-v1", "sessions": len(rows), "planned_sessions": planned,
                "protocol_counts": dict(sorted(Counter(row["protocol"] for row in rows).items())),
                "files": {name: sha256((output / name).read_bytes()) for name in sorted(files)}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    from .analyze import analyze
    (output / "summary.json").write_text(json.dumps(analyze(output), indent=2, sort_keys=True) + "\n")
    manifest["files"]["summary.json"] = sha256((output / "summary.json").read_bytes())
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"sessions": len(rows), "planned_sessions": planned,
            "protocol_counts": manifest["protocol_counts"],
            "runs": [{key: run[key] for key in ("experiment", "protocol", "planned_sessions",
                                                "exported_sessions", "normal_sessions",
                                                "published_profile", "sources_match_installed")}
                     for run in runs]}
