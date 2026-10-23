"""Offline registration and explicitly authorized, non-resumable execution."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import subprocess

from parabox.model import load_config
from parabox.util import digest_json, now, read, save, sha256
from parabox.workspace import snapshot_regular, write_regular

from . import fixture, runtime


def bindings() -> dict:
    package = Path(__file__).resolve().parent
    root = package.parents[2]
    paths = list(package.glob("*.py")) + [root / name for name in (
        "parabox/__init__.py", "parabox/studies/__init__.py", "parabox/util.py",
        "parabox/sandbox.py", "parabox/workspace.py", "parabox/model/__init__.py",
        "parabox/model/chat.py", "parabox/model/gemini.py")]
    return {str(path.relative_to(root)): sha256(path.read_bytes()) for path in sorted(paths)}


def default_spec(models: dict, image: str, scoring="final", agents=1) -> dict:
    spec = {"schema": 1, "models": models, "image": image, "scoring": scoring,
            "agents": agents, "generations": 6, "prefixes": list(fixture.PREFIXES),
            "conditions": ["method"] if agents == 1 else ["method", "empty"],
            "seed": 20261019, "order_seed": 20261020}
    validate_spec(spec)
    return spec


def validate_spec(spec):
    fields = {"schema", "models", "image", "scoring", "agents", "generations",
              "prefixes", "conditions", "seed", "order_seed"}
    if not isinstance(spec, dict) or set(spec) != fields or spec["schema"] != 1:
        raise ValueError("Expected a complete study specification with schema 1")
    if not isinstance(spec["image"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", spec["image"]):
        raise ValueError("Image must be a full sha256 image ID")
    if spec["scoring"] not in ("final", "mean") or type(spec["agents"]) is not int or spec["agents"] not in (1, 4):
        raise ValueError("Expected final or mean scoring and one or four agents")
    if type(spec["generations"]) is not int or spec["generations"] < 1:
        raise ValueError("Expected a positive generation count")
    for name in ("seed", "order_seed"):
        if type(spec[name]) is not int or spec[name] < 0:
            raise ValueError("Seeds must be nonnegative integers")
    prefixes = spec["prefixes"]
    if (not isinstance(prefixes, list) or not prefixes
            or any(type(prefix) is not int or prefix not in fixture.PREFIXES for prefix in prefixes)
            or len(set(prefixes)) != len(prefixes)):
        raise ValueError("Expected unique prefixes selected from 1, 40, 85")
    conditions = spec["conditions"]
    if (not isinstance(conditions, list) or not conditions
            or any(condition not in ("method", "empty") for condition in conditions)
            or len(set(conditions)) != len(conditions)):
        raise ValueError("Expected unique method or empty initial conditions")
    if not isinstance(spec["models"], dict) or not spec["models"]:
        raise ValueError("At least one model configuration is required")
    for name, path in spec["models"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) or not isinstance(path, str) or not path:
            raise ValueError("Expected safe model names and configuration paths")


def chains(spec):
    return [{"chain": f"{model}-prefix-{prefix:02d}-{condition}", "model": model,
             "prefix": prefix, "condition": condition, "scoring": spec["scoring"]}
            for prefix in spec["prefixes"] for condition in spec["conditions"] for model in spec["models"]]


def schedule(spec):
    return [{**chain, "generation": generation, "seat": seat,
             "actor": f"{chain['chain']}-{generation:02d}-{seat}"}
            for chain in chains(spec) for generation in range(1, spec["generations"] + 1)
            for seat in range(spec["agents"])]


def materials(spec, target):
    files = {}
    for prefix in spec["prefixes"]:
        for name, raw in fixture.participant_files(prefix, target, spec["scoring"]).items():
            files[f"prefix-{prefix:02d}/{name}"] = raw
    files["initial-method/method.txt"] = fixture.METHOD.encode()
    files["prompts.json"] = fixture.encode({"system": fixture.SYSTEM,
        "user": fixture.assignment(spec["scoring"]), "tools": fixture.tools(spec["scoring"])})
    return files


def config_valid(config):
    if not isinstance(config, dict) or "api_key" in config:
        raise ValueError("Use api_key_env; do not embed credentials")
    if any(not isinstance(config.get(name), str) or not config[name]
           for name in ("model", "api_key_env", "base_url")):
        raise ValueError("Configuration requires model, api_key_env, and base_url")
    if config.get("wire") not in (None, "chat", "gemini"):
        raise ValueError("Unsupported model wire format")


def prepare(spec_path: Path, directory: Path) -> dict:
    spec_path, directory = Path(spec_path), Path(directory)
    spec = read(spec_path)
    validate_spec(spec)
    configs = {}
    for name, path in spec["models"].items():
        configs[name] = load_config(spec_path.resolve().parent / path)
        config_valid(configs[name])
    target = fixture.make_target(spec["seed"])
    files = materials(spec, target)
    registration = {"study": "costly_information", "created_at": now(), "spec": spec,
        "configs": configs, "config_hashes": {name: digest_json(config) for name, config in configs.items()},
        "target_sha256": sha256(fixture.encode(target)), "bindings": bindings(),
        "materials": {name: sha256(raw) for name, raw in files.items()},
        "schedule": schedule(spec), "session_cap": len(schedule(spec)),
        "call_limit": fixture.CALL_LIMIT,
        "target_policy": "One fixed IID ternary target shared across all cells; no independent task replication",
        "source": "Researcher-authored method exposure; not an authentic predecessor record"}
    directory.mkdir(parents=True, exist_ok=False)
    host = directory / "host"
    host.mkdir(mode=0o700)
    write_regular(host, "target.json", fixture.encode(target))
    material_root = directory / "materials"
    material_root.mkdir()
    for name, raw in files.items():
        write_regular(material_root, name, raw)
    save(directory / "registration.json", registration)
    (directory / "registration.sha256").write_text(digest_json(registration) + "\n")
    return {"registration_sha256": digest_json(registration), "session_cap": registration["session_cap"]}


def checked(directory: Path) -> dict:
    directory = Path(directory)
    registration = read(directory / "registration.json")
    if (directory / "registration.sha256").read_text().strip() != digest_json(registration):
        raise RuntimeError("Registration digest mismatch")
    spec = registration["spec"]
    validate_spec(spec)
    if registration["bindings"] != bindings():
        raise RuntimeError("Source changed after preparation")
    if set(registration["configs"]) != set(spec["models"]):
        raise RuntimeError("Model allocation changed")
    for name, config in registration["configs"].items():
        config_valid(config)
        if digest_json(config) != registration["config_hashes"][name]:
            raise RuntimeError("Configuration changed")
    target = fixture.make_target(spec["seed"])
    if ((directory / "host/target.json").read_bytes() != fixture.encode(target)
            or registration["target_sha256"] != sha256(fixture.encode(target))):
        raise RuntimeError("Target changed")
    expected_files = materials(spec, target)
    if (registration["materials"] != {name: sha256(raw) for name, raw in expected_files.items()}
            or snapshot_regular(directory / "materials") != expected_files):
        raise RuntimeError("Participant materials changed")
    expected_schedule = schedule(spec)
    if (registration["schedule"] != expected_schedule or registration["session_cap"] != len(expected_schedule)
            or registration["call_limit"] != fixture.CALL_LIMIT or registration["study"] != "costly_information"):
        raise RuntimeError("Registered allocation changed")
    return registration


def verify_image(image):
    result = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", image],
                            check=True, capture_output=True, text=True, timeout=30)
    if result.stdout.strip().removeprefix("sha256:") != image.removeprefix("sha256:"):
        raise RuntimeError("Container image does not match registration")


def execution_guard(directory, registration_sha256, deadline):
    runtime.require_time(deadline)
    if digest_json(checked(directory)) != registration_sha256:
        raise RuntimeError("Prepared registration changed during execution")
    runtime.require_time(deadline)


def claim_start(directory, registration, actor_spec, deadline, authorized_cap):
    execution_guard(directory, digest_json(registration), deadline)
    if type(authorized_cap) is not int or authorized_cap != registration["session_cap"]:
        raise RuntimeError("Authorization must equal the registered session cap")
    with (directory / ".claims.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "starts.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        digest = digest_json(registration)
        known = {row["actor"]: row for row in registration["schedule"]}
        if len(rows) >= authorized_cap or actor_spec != known.get(actor_spec["actor"]):
            raise RuntimeError("Start outside authorized allocation")
        actors = set()
        for sequence, row in enumerate(rows, 1):
            if (row["sequence"] != sequence or row["registration_sha256"] != digest
                    or row["spec"] != known.get(row["actor"]) or row["actor"] in actors):
                raise RuntimeError("Invalid claim ledger")
            actors.add(row["actor"])
        if actor_spec["actor"] in actors:
            raise RuntimeError("Actor already claimed; no retries")
        runtime.require_time(deadline)
        row = {"sequence": len(rows) + 1, "actor": actor_spec["actor"], "spec": actor_spec,
               "claimed_at": now(), "registration_sha256": digest, "deadline": deadline}
        with path.open("a") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return row


def run(directory: Path, authorized_cap: int, deadline: str):
    directory = Path(directory).resolve()
    with (directory / ".execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        registration = checked(directory)
        if type(authorized_cap) is not int or authorized_cap != registration["session_cap"]:
            raise RuntimeError("Authorization must equal the registered session cap")
        runtime.require_time(deadline)
        if any((directory / name).exists() for name in ("execution.json", "execution-start.json", "starts.jsonl", "chains")):
            raise RuntimeError("Execution already attempted; no resume or retries")
        spec = registration["spec"]
        registration_sha256 = digest_json(registration)
        verify_image(spec["image"])
        runtime.require_time(deadline)
        with (directory / "execution-start.json").open("x") as stream:
            json.dump({"registration_sha256": digest_json(registration), "authorized_session_cap": authorized_cap,
                       "deadline": deadline, "started_at": now()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        target = read(directory / "host/target.json")
        results = []
        for chain_index, chain in enumerate(chains(spec)):
            root = directory / "chains" / chain["chain"]
            wiki = root / "wiki"
            wiki.mkdir(parents=True, exist_ok=False)
            if chain["condition"] == "method":
                write_regular(wiki, "method.txt", fixture.METHOD.encode())
            blocked = False
            for generation in range(1, spec["generations"] + 1):
                generation_spec = {**chain, "generation": generation}
                if blocked:
                    results.append({**generation_spec, "normal": False, "status": "blocked_by_predecessor"})
                    continue
                result = runtime.run_generation(
                    root / f"generation-{generation:02d}", generation_spec,
                    registration["configs"][chain["model"]], target, spec["image"], wiki,
                    spec["order_seed"] + chain_index * spec["generations"] + generation,
                    spec["agents"], deadline,
                    lambda actor_spec: claim_start(directory, registration, actor_spec, deadline, authorized_cap),
                    lambda: execution_guard(directory, registration_sha256, deadline))
                results.append(result)
                blocked = not result["normal"]
        result = {"registration_sha256": digest_json(registration), "ended_at": now(), "generations": results,
                  "claimed_starts": len((directory / "starts.jsonl").read_text().splitlines())
                  if (directory / "starts.jsonl").exists() else 0}
        save(directory / "execution.json", result)
        return result
