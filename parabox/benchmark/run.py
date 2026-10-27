"""Explicitly authorized new execution; no retries, resume or inline grading."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import subprocess

from parabox.benchmark.prepare import check
from parabox.benchmark.protocol.prompts import core_task
from parabox.execution import (
    BoundOutcomeEngine, CoreEngine, DeadlineClient, FrozenWikiEngine, Invocation, StartLedger,
    run_population, run_sequential,
)
from parabox.execution.artifacts import manifest as file_manifest
from parabox.execution.control.guards import parse_deadline, utcnow
from parabox.util import digest_json, read, save, sha256


def verify_image(image: str):
    result = subprocess.run(["podman", "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, timeout=15, check=True)
    actual = result.stdout.strip().removeprefix("sha256:")
    if actual != image.removeprefix("sha256:"):
        raise ValueError("Local image differs from prepared image")


def withdraw_note(files: dict[str, bytes], founder_hash: str | None) -> tuple[dict, dict]:
    delivered = dict(files)
    before = file_manifest(files)
    note = "shared/wiki/NOTES.md"
    removed = None
    if founder_hash is not None and before.get(note) == founder_hash:
        removed = sha256(delivered.pop(note))
    return delivered, {"predecessor_files": before, "delivered_files": file_manifest(delivered),
                       "source_note_hash": founder_hash, "removed_note_original_hash": removed}


def _load_files(directory, mapping):
    files = {}
    for name, digest in mapping.items():
        raw = (directory / "artifacts" / digest).read_bytes()
        if sha256(raw) != digest:
            raise ValueError("Prepared artifact changed")
        files[name] = raw
    file_manifest(files)
    return files


def _engines(spec, models, frozen, deadline):
    from parabox.model import Client
    from parabox.sandbox import Box, Limits

    def factory(invocation):
        task = core_task(invocation.spec)
        task.image = spec["image"]
        config = read(Path(models[invocation.spec["model_config"]]["path"]))
        client = DeadlineClient(Client(config), deadline)
        workspace = Path(invocation.directory) / "workspace"
        box = Box("session-" + sha256(str(invocation.directory.resolve()))[:20],
                  workspace, spec["image"], limits=Limits(cpus="2", memory="2g"))
        return {"task": task, "client": client, "box": box,
                "integrity": "plain", "shared": False, "opening": []}

    return CoreEngine(factory), FrozenWikiEngine(variant="budget20", frozen=frozen)


def run(directory: Path, *, authorize_session_cap: int, deadline: str,
        core_engine=None, wiki_engine=None, image_verifier=None, clock=utcnow) -> dict:
    directory = Path(directory).resolve()
    checked = check(directory)
    plan, spec = read(directory / "plan.json"), read(directory / "spec.json")
    prepared, materials = read(directory / "manifest.json"), read(directory / "materials.json")
    cap = plan["counts"]["total"]
    if type(authorize_session_cap) is not int or authorize_session_cap != cap:
        raise ValueError("Explicit session authorization must equal the exact planned count")
    cutoff = parse_deadline(deadline)
    if clock() >= cutoff:
        raise ValueError("Execution deadline is not in the future")
    execution = directory / "execution"
    if execution.exists():
        raise ValueError("Execution already exists; no resume or retries")
    if (core_engine is None) != (wiki_engine is None):
        raise ValueError("Inject both engines or neither")
    (image_verifier or verify_image)(spec["image"])
    execution.mkdir()
    authorization = {"session_cap": cap, "deadline": cutoff.isoformat(),
                     "manifest_sha256": checked["manifest_sha256"],
                     "created_at": clock().isoformat(), "no_retries": True}
    save(execution / "authorization.json", authorization)
    frozen = dict(prepared["sources"])
    for binding in prepared["models"].values():
        frozen[binding["path"]] = binding["sha256"]
    paths = [directory / name for name in ("spec.json", "plan.json", "materials.json", "manifest.json")]
    paths += [directory / "artifacts" / digest for digest in prepared["artifacts"]]
    paths.append(execution / "authorization.json")
    frozen.update({str(path): sha256(path.read_bytes()) for path in paths})
    rows = {row["actor"]: row for row in plan["sessions"]}
    ledger = StartLedger(execution / "starts.sqlite3", cap=cap, deadline=deadline,
                         frozen=frozen, planned=rows)
    if core_engine is None:
        core_engine, wiki_engine = _engines(spec, prepared["models"], frozen, deadline)
    core_engine, wiki_engine = BoundOutcomeEngine(core_engine), BoundOutcomeEngine(wiki_engine)
    states, chain_files, failed_chains = {}, {}, set()
    for wave in plan["waves"]:
        groups = OrderedDict()
        for actor in wave["actors"]:
            row = rows[actor]
            groups.setdefault(row["chain"], []).append(row)
        wave_records = []
        for chain, group in groups.items():
            group.sort(key=lambda row: row.get("seat", 0))
            if chain in failed_chains or any(
                    states.get(parent, {}).get("state") != "completed"
                    for row in group for parent in row["depends_on"]):
                for row in group:
                    states[row["actor"]] = {"state": "unavailable_predecessor"}
                failed_chains.add(chain)
                continue
            if clock() >= cutoff:
                for row in group:
                    states[row["actor"]] = {"state": "unstarted_deadline"}
                failed_chains.add(chain)
                continue
            first = group[0]
            try:
                invocations = [Invocation(row["actor"], execution / "sessions" / row["actor"], row)
                               for row in group]
                if first["component"] == "core":
                    if first.get("function_profile"):
                        surface = materials["surfaces"][first["actor"]]["workspace"]
                        seed = _load_files(directory, {name: digest for name, digest in surface.items()
                                                       if name.startswith("shared/")})
                        incoming = dict(chain_files.get(chain, seed))
                    else:
                        incoming = dict(chain_files.get(chain, {})) if first["condition"] == "cumulative" else {}
                    if first["transport"] == "replace":
                        result = run_sequential(invocations, engine=core_engine, ledger=ledger, initial=incoming)
                    else:
                        result = run_population([invocations], engine=core_engine, ledger=ledger,
                                                initial=incoming, policy="population_all", workers=len(group))
                    transition = {"incoming": file_manifest(incoming),
                                  "lineage": result["lineage"]}
                    chain_files[chain] = result["files"] if first["transport"] != "none" else {}
                else:
                    seed = materials["wiki_seeds"][f"{first['block']}:{first['condition']}"]
                    if first["position"] == 0:
                        incoming = _load_files(directory, seed["files"])
                        transition = {"source": seed["provenance"], "delivered_files": file_manifest(incoming)}
                    else:
                        if first["withdraw"]:
                            incoming, transition = withdraw_note(chain_files[chain], seed["original_note_sha256"])
                        else:
                            incoming = dict(chain_files[chain])
                            transition = {"predecessor_files": file_manifest(incoming),
                                          "delivered_files": file_manifest(incoming),
                                          "source_note_hash": seed["original_note_sha256"],
                                          "removed_note_original_hash": None}
                        transition["predecessor_actor"] = first["incoming_from"][0]
                    invocations[0].options = {
                        "config": read(Path(prepared["models"][first["model_config"]]["path"])),
                        "image": spec["image"],
                        "files": _load_files(directory, materials["surfaces"][first["actor"]]["workspace"]),
                        "deadline": deadline,
                    }
                    result = run_sequential(invocations, engine=wiki_engine, ledger=ledger, initial=incoming)
                    chain_files[chain] = result["files"]
                    transition["lineage"] = result["lineage"]
                for row, outcome in zip(group, result["outcomes"], strict=True):
                    if outcome.end.get("actor") != row["actor"]:
                        raise ValueError("Outcome identity differs from the planned actor")
                    states[row["actor"]] = {"state": "completed", "normal": outcome.end.get("normal")}
                wave_records.append({"chain": chain, "actors": [row["actor"] for row in group],
                                     "transition": transition, "outgoing": file_manifest(chain_files[chain])})
            except Exception as error:
                claimed = {entry["key"]: entry for entry in ledger.rows()}
                for row in group:
                    entry = claimed.get(row["actor"])
                    known_normal = (entry is not None and entry["state"] == "completed"
                                    and (entry.get("detail") or {}).get("normal") is True)
                    states[row["actor"]] = {
                        "state": "completed" if known_normal else
                                 "technical_failure" if entry else "unavailable_execution",
                        "ledger_state": entry["state"] if entry else None,
                        "normal": True if known_normal else None,
                        "error_type": type(error).__name__,
                        "chain_export_unavailable": True,
                    }
                failed_chains.add(chain)
        save(execution / "waves" / f"{wave['id']}.json", {
            "wave": wave, "records": wave_records,
            "states": {actor: states[actor] for actor in wave["actors"]}})
        save(execution / "status.json", {"states": states, "last_wave": wave["id"]})
    result = {
        "states": states, "ledger": ledger.rows(), "planned": cap,
        "completed": sum(value["state"] == "completed" for value in states.values()),
        "grading": "not_run; acceptance is not independent audit or legitimate utility",
        "manifest_sha256": checked["manifest_sha256"],
        "authorization_sha256": digest_json(authorization),
    }
    save(execution / "end.json", result)
    return result
