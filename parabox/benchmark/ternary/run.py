"""Prepare and execute ternary sequence chains without automatic retries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import random
import re
import subprocess
import threading

from parabox.execution.control.guards import parse_deadline, utcnow
from parabox.util import digest_json, read, save, sha256

from . import episode, fixture


START_LOCK = threading.Lock()
SOURCE_FILES = (
    "benchmark/ternary/runtime/__init__.py", "benchmark/ternary/runtime/base.py",
    "benchmark/ternary/episode.py",
    "benchmark/ternary/fixture.py", "benchmark/ternary/run.py",
    "execution/control/__init__.py", "execution/control/guards.py",
    "model/__init__.py", "model/anthropic.py", "model/chat.py", "model/gemini.py",
    "model/responses.py",
    "sandbox.py", "util.py", "workspace.py",
)


def source_hashes() -> dict[str, str]:
    directory = Path(__file__).resolve().parents[2]
    return {name: sha256((directory / name).read_bytes()) for name in SOURCE_FILES}


def validate_spec(spec: dict) -> dict:
    required = {"models", "image", "seed", "seats"}
    optional = {"protocol", "profile", "transport_profile"}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - optional:
        raise ValueError("Spec requires models, image, seed, and seats; only protocol, profile, and transport_profile are optional")
    models = spec["models"]
    if not isinstance(models, dict) or not models:
        raise ValueError("At least one model configuration is required")
    if any(not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) or not isinstance(path, str)
           or not path for name, path in models.items()):
        raise ValueError("Models must map safe names to configuration paths")
    if not isinstance(spec["image"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", spec["image"]):
        raise ValueError("An immutable image ID is required")
    if (type(spec["seed"]) is not int or spec["seed"] < 0
            or type(spec["seats"]) is not int or spec["seats"] not in (1, 4)):
        raise ValueError("Seed must be nonnegative and seats must be one or four")
    protocol = spec.get("protocol", fixture.REPEATED)
    profile = spec.get("profile", fixture.GENERATED)
    transport_profile = spec.get("transport_profile", fixture.JSON_360)
    if protocol not in (fixture.TERMINAL, fixture.REPEATED):
        raise ValueError("Unknown ternary protocol")
    if profile not in (fixture.GENERATED, fixture.HISTORICAL):
        raise ValueError("Unknown ternary target/order profile")
    if transport_profile not in (fixture.JSON_360, fixture.JSON_900):
        raise ValueError("Unknown ternary transport profile")
    if profile == fixture.HISTORICAL and "transport_profile" not in spec:
        raise ValueError("Historical profile requires an explicit non-streaming transport profile")
    if profile == fixture.HISTORICAL and spec["seed"] != fixture.HISTORICAL_SEED:
        raise ValueError("Historical target seed differs from the registered profile")
    return {**spec, "protocol": protocol, "profile": profile,
            "transport_profile": transport_profile}


def transport_contract(spec: dict) -> dict:
    return {"profile": spec["transport_profile"], "response_mode": "non-streaming",
            "socket_timeout_seconds": 900 if spec["transport_profile"] == fixture.JSON_900 else 360,
            "adapter_default_max_output_tokens": 32768,
            "max_attempts": 4, "retryable_http_statuses": [429, 500, 502, 503],
            "retries_json_decode_errors": True, "global_stream_slots": False,
            "matches_historical_stream_transport": False}


def order_seed(row: dict, generation: int, protocol: str, profile: str) -> int:
    if profile == fixture.HISTORICAL:
        prefix = "20261022" if protocol == fixture.TERMINAL else "v3"
        material = f"{prefix}:{row['model']}:{row['prefix']}:{generation}"
    elif profile == fixture.GENERATED:
        material = f"ternary:{row['chain']}:{generation}"
    else:
        raise ValueError("Unknown ternary target/order profile")
    return int(sha256(material)[:16], 16)


def schedule(models: dict, seats: int) -> list[dict]:
    conditions = ("method",) if seats == 1 else ("empty", "method")
    return [{"chain": f"{model}-prefix-{prefix:02d}-{condition}", "model": model,
             "prefix": prefix, "condition": condition}
            for prefix in fixture.PREFIXES for condition in conditions for model in models]


def prepare(directory: Path, spec: dict) -> dict:
    spec = validate_spec(spec)
    directory = Path(directory).resolve()
    generator = random.Random(spec["seed"])
    target = [generator.randrange(3) for _ in range(100)]
    models = {}
    for name, path in spec["models"].items():
        source = Path(path).resolve()
        config = read(source)
        if not isinstance(config, dict) or "api_key" in config or not config.get("api_key_env"):
            raise ValueError(f"Invalid or embedded-credential model configuration: {name}")
        timeout = transport_contract(spec)["socket_timeout_seconds"]
        if "ternary_timeout_s" in config and config["ternary_timeout_s"] != timeout:
            raise ValueError(f"Model timeout conflicts with selected transport profile: {name}")
        models[name] = {"path": str(source), "sha256": sha256(source.read_bytes())}
    registration = {"spec": spec, "models": models, "target": target,
                    "transport": transport_contract(spec),
                    "generations": 6, "chains": schedule(models, spec["seats"]),
                    "session_cap": len(schedule(models, spec["seats"])) * 6 * spec["seats"],
                    "sources": source_hashes(), "created_at": utcnow().isoformat()}
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "registration.json", registration)
    (directory / "registration.sha256").write_text(digest_json(registration) + "\n")
    return {"directory": str(directory), "session_cap": registration["session_cap"],
            "registration_sha256": digest_json(registration)}


def check(directory: Path) -> dict:
    directory = Path(directory).resolve()
    registration = read(directory / "registration.json")
    if (directory / "registration.sha256").read_text().strip() != digest_json(registration):
        raise ValueError("Registration changed")
    spec = validate_spec(registration["spec"])
    if registration.get("transport") != transport_contract(spec):
        raise ValueError("Transport profile changed")
    if registration["sources"] != source_hashes():
        raise ValueError("Experiment implementation changed")
    if registration["chains"] != schedule(registration["models"], spec["seats"]):
        raise ValueError("Schedule changed")
    if set(registration["models"]) != set(spec["models"]):
        raise ValueError("Model bindings changed")
    if registration["generations"] != 6 or registration["session_cap"] != len(registration["chains"]) * 6 * spec["seats"]:
        raise ValueError("Session count changed")
    generator = random.Random(spec["seed"])
    if registration["target"] != [generator.randrange(3) for _ in range(100)]:
        raise ValueError("Target differs from prepared seed")
    for binding in registration["models"].values():
        source = Path(binding["path"])
        if sha256(source.read_bytes()) != binding["sha256"]:
            raise ValueError("Model configuration changed")
    for name, path in spec["models"].items():
        if Path(path).resolve() != Path(registration["models"][name]["path"]):
            raise ValueError("Model configuration path changed")
    return registration


def verify_image(image: str) -> None:
    result = subprocess.run(["podman", "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, timeout=15, check=True)
    if result.stdout.strip().removeprefix("sha256:") != image.removeprefix("sha256:"):
        raise ValueError("Local image differs from prepared image")


def claim(directory: Path, spec: dict, seats: int, cap: int) -> None:
    ledger = directory / "starts.jsonl"
    with START_LOCK:
        previous = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
        if len(previous) + seats > cap:
            raise RuntimeError("Session cap exceeded")
        if any(row["chain"] == spec["chain"] and row["generation"] == spec["generation"]
               for row in previous):
            raise RuntimeError("Generation already claimed")
        with ledger.open("a") as stream:
            for seat in range(seats):
                stream.write(json.dumps({**spec, "seat": seat, "claimed_at": utcnow().isoformat()}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def run_chain(directory: Path, row: dict, registration: dict, deadline: datetime) -> str:
    chain = directory / "chains" / row["chain"]
    chain.mkdir(parents=True, exist_ok=False)
    wiki = chain / "wiki"
    wiki.mkdir()
    if row["condition"] == "method":
        (wiki / "method.txt").write_text(fixture.METHOD)
    spec = registration["spec"]
    config = read(Path(registration["models"][row["model"]]["path"]))
    config = {**config, "ternary_timeout_s": registration["transport"]["socket_timeout_seconds"]}
    for generation in range(1, 7):
        if utcnow() >= deadline:
            raise TimeoutError("Deadline reached before generation start")
        assignment = {**row, "generation": generation,
                      "actor": f"{row['chain']}-g{generation:02d}"}
        claim(directory, assignment, spec["seats"], registration["session_cap"])
        seed = order_seed(row, generation, spec["protocol"], spec["profile"])
        result = episode.run_generation(chain / f"generation-{generation:02d}", assignment,
                                        config, registration["target"], spec["image"], wiki,
                                        seed, deadline.isoformat(), agents=spec["seats"],
                                        protocol=spec["protocol"])
        if not result["normal"]:
            raise RuntimeError(f"Generation {generation} failed")
    return row["chain"]


def run(directory: Path, *, authorize_session_cap: int, deadline: str, workers: int = 4) -> dict:
    directory = Path(directory).resolve()
    cutoff = parse_deadline(deadline)
    if utcnow() >= cutoff:
        raise ValueError("Deadline is not in the future")
    if not 1 <= workers <= 6:
        raise ValueError("Workers must be between one and six")
    with (directory / ".execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        registration = check(directory)
        if authorize_session_cap != registration["session_cap"]:
            raise ValueError("Authorization must equal the planned session count")
        if ((directory / "authorization.json").exists() or (directory / "starts.jsonl").exists()
                or (directory / "chains").exists()):
            raise ValueError("Prior execution exists; no automatic resume")
        verify_image(registration["spec"]["image"])
        save(directory / "authorization.json", {"session_cap": authorize_session_cap,
             "deadline": cutoff.isoformat(), "registration_sha256": digest_json(registration)})
        errors = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_chain, directory, row, registration, cutoff): row["chain"]
                       for row in registration["chains"]}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    errors[futures[future]] = type(error).__name__
                sessions = [read(path) for path in sorted(directory.glob("chains/*/generation-*/seat-*/end.json"))]
                save(directory / "results.json", {"registration_sha256": digest_json(registration),
                     "session_cap": registration["session_cap"], "completed": len(sessions),
                     "chain_errors": errors, "sessions": sessions})
        return {"completed": len(sessions), "chain_errors": errors}
