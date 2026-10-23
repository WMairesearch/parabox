"""Explicitly authorized recipient execution with actual predecessor exports."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import threading

from parabox.benchmark.sources import NOTE, export_wiki
from parabox.execution import BoundOutcomeEngine, FrozenWikiEngine, Invocation, StartLedger, run_sequential
from parabox.execution.artifacts import manifest as file_manifest
from parabox.execution.guards import parse_deadline, utcnow
from parabox.util import digest_json, read, save, sha256
from parabox.workspace import read_regular
from .design import TRANSPORTS
from .prepare import check


def verify_image(image):
    result = subprocess.run(["podman", "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, check=True, timeout=15)
    if result.stdout.strip().removeprefix("sha256:") != image.removeprefix("sha256:"):
        raise ValueError("Local image differs from registered immutable image")


def transport_payload(files, founder_hash, *, transport, position):
    if transport not in TRANSPORTS or type(position) is not int or position < 1:
        raise ValueError("Expected a supported transport and successor position")
    before = file_manifest(files)
    delivered = dict(files)
    removed = None
    if transport == "historical-withdrawal" and position == 1 and founder_hash is not None:
        if before.get(NOTE) == founder_hash:
            removed = sha256(delivered.pop(NOTE))
    return delivered, {"transport": transport, "position": position,
                       "predecessor_files": before, "delivered_files": file_manifest(delivered),
                       "source_note_hash": founder_hash, "removed_note_original_hash": removed}


def load_files(directory, mapping):
    files = {}
    for name, digest in mapping.items():
        raw = read_regular(directory, "artifacts/" + digest)
        if sha256(raw) != digest:
            raise ValueError("Prepared artifact changed")
        files[name] = raw
    file_manifest(files)
    return files


def run(directory: Path, *, authorize_session_cap: int, deadline: str,
        wiki_engine=None, image_verifier=None, clock=utcnow) -> dict:
    directory = Path(directory).resolve()
    verified = check(directory)
    spec, plan = read(directory / "spec.json"), read(directory / "plan.json")
    prepared, materials = read(directory / "manifest.json"), read(directory / "materials.json")
    cap = plan["counts"]["total"]
    if type(authorize_session_cap) is not int or authorize_session_cap != cap:
        raise ValueError("Explicit authorization must equal the exact planned session count")
    cutoff = parse_deadline(deadline)
    if clock() >= cutoff:
        raise ValueError("Execution deadline must be in the future")
    deadline = cutoff.isoformat()
    execution = directory / "execution"
    if execution.exists():
        raise ValueError("Execution already exists; no resume or retries")
    (image_verifier or verify_image)(spec["image"])
    execution.mkdir()
    authorization = {"session_cap": cap, "deadline": deadline,
                     "manifest_sha256": verified["manifest_sha256"], "created_at": clock().isoformat(),
                     "no_retries": True}
    save(execution / "authorization.json", authorization)
    frozen = dict(prepared["sources"])
    frozen.update({binding["path"]: binding["sha256"] for binding in prepared["models"].values()})
    paths = [directory / name for name in ("spec.json", "plan.json", "materials.json", "manifest.json")]
    paths += [directory / "artifacts" / digest for digest in prepared["artifacts"]]
    paths.append(execution / "authorization.json")
    frozen.update({str(path): sha256(path.read_bytes()) for path in paths})
    known = {row["actor"]: row for row in plan["sessions"]}
    ledger = StartLedger(execution / "starts.sqlite3", cap=cap, deadline=deadline, frozen=frozen, planned=known)
    engine = BoundOutcomeEngine(wiki_engine if wiki_engine is not None else
                                FrozenWikiEngine(variant="budget20", frozen=frozen))
    slots = threading.BoundedSemaphore(spec["workers_total"])

    def launch(row):
        with slots:
            if clock() >= cutoff:
                return {"state": "unstarted_deadline"}
            actor = row["actor"]
            try:
                seed = materials["founders"][f"{row['block']}:{row['condition']}"]
                if row["position"] == 0:
                    incoming = load_files(directory, seed["files"])
                    provenance = {"kind": "founder", "source": seed,
                                  "delivered_files": file_manifest(incoming)}
                else:
                    parent = known[f"{row['chain']}-{row['position'] - 1:02d}"]
                    end, exported = export_wiki(execution / "sessions" / parent["actor"])
                    if any(end.get(key) != value for key, value in parent.items()):
                        raise ValueError("Predecessor identity differs from plan")
                    incoming, provenance = transport_payload(exported, seed["source_note_hash"],
                        transport=spec["transport"], position=row["position"])
                    provenance.update(predecessor=parent["actor"], end_sha256=digest_json(end))
                save(execution / "provenance" / actor / "incoming.json", provenance)
                invocation = Invocation(actor, execution / "sessions" / actor, row, {
                    "config": read(Path(prepared["models"][row["model"]]["path"])),
                    "image": spec["image"], "deadline": deadline,
                    "files": load_files(directory, materials["surfaces"][actor]["workspace"])})
                result = run_sequential([invocation], engine=engine, ledger=ledger, initial=incoming)
                end, exported = export_wiki(invocation.directory)
                if (any(end.get(key) != value for key, value in row.items())
                        or file_manifest(exported) != file_manifest(result["files"])):
                    raise ValueError("Completed export differs from invocation outcome")
                save(execution / "provenance" / actor / "outgoing.json", {
                    "files": file_manifest(exported), "end_sha256": digest_json(end),
                    "deleted": sorted(set(incoming) - set(exported))})
                return {"state": "completed", "normal": True}
            except Exception as error:
                entry = next((entry for entry in ledger.rows() if entry["key"] == actor), None)
                return {"state": "technical_failure" if entry else "unavailable_execution",
                        "ledger_state": entry["state"] if entry else None,
                        "error_type": type(error).__name__}

    def pipeline(model):
        states, failed = {}, set()
        for position in range(spec["positions"]):
            wave = [known[actor] for actor in plan["wave_orders"][model][str(position)]]
            pending = []
            for row in wave:
                if row["chain"] in failed:
                    states[row["actor"]] = {"state": "unavailable_predecessor"}
                else:
                    pending.append(row)
            with ThreadPoolExecutor(max_workers=spec["workers_per_model"]) as pool:
                results = list(pool.map(launch, pending))
            for row, result in zip(pending, results, strict=True):
                states[row["actor"]] = result
                if result["state"] != "completed":
                    failed.add(row["chain"])
            save(execution / "waves" / model / f"{position:02d}.json", {
                "actors": [row["actor"] for row in wave],
                "states": {row["actor"]: states[row["actor"]] for row in wave}})
        return states

    with ThreadPoolExecutor(max_workers=len(spec["models"])) as pool:
        states = {actor: state for result in pool.map(pipeline, sorted(spec["models"]))
                  for actor, state in result.items()}
    result = {"manifest_sha256": verified["manifest_sha256"],
              "authorization_sha256": digest_json(authorization), "planned": cap,
              "states": states, "ledger": ledger.rows(),
              "completed": sum(value["state"] == "completed" for value in states.values()),
              "grading": "not_run; use the separate grade command"}
    save(execution / "end.json", result)
    return result
