"""Prepare, run, and audit a zero-door transmission directory.

Generation 1 is seeded with the planted arm file for this door. Later generations
of the same chain receive a byte-identical copy of the previous session's shared/.
The session task is DoorChainTask(door): mechspan A4 or A5 plus the transmission
task text. Barrier mechanics are the transmission study's (none on control/recipe).
"""
from __future__ import annotations

import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.session import run_session
from parabox.studies.relay.run import CONCURRENCY, code_commit, image_id, session_dir
from parabox.studies.transmission.run import apply_barrier, shared_digest, shared_snapshot
from parabox.studies.transmission_door import design as D
from parabox.studies.transmission_door import notes as N
from parabox.studies.transmission_door.task import DoorChainTask
from parabox.tasks.code import audit as A
from parabox.tasks.code.mechspan import verifier_config, workspace_files
from parabox.tasks.code.problems import IMPOSSIBLE, problem_hashes
from parabox.tasks.code.task import MAX_SUBMITS, TURNS
from parabox.util import digest_json, now, read, save, sha256

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir",
           "extra_files", "shared_snapshot", "shared_digest", "apply_barrier",
           "CONCURRENCY"]

LIMITS = Limits(cpus="2", memory="2g")
INTEGRITY = "plain"


def extra_files(directory: Path, row: dict, door: str) -> dict[str, bytes]:
    if row["generation"] == 1:
        files = dict(N.seed_files(row["arm"], door))
    else:
        prev = session_dir(directory, f"{row['chain']}-g{row['generation'] - 1:02d}")
        if not (prev / "end.json").exists():
            raise RuntimeError(f"{row['chain']} generation {row['generation'] - 1} has no end record")
        files = shared_snapshot(prev)
    return apply_barrier(files, row)


def _text_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: data.decode("utf-8", "replace") for name, data in files.items()}


def workspace_hashes(door: str) -> dict[str, str]:
    return {name: sha256(b"".join(workspace_files(door, name).values())) for name in IMPOSSIBLE}


def frozen(door: str, config: dict, *, arms=None) -> dict:
    chosen = tuple(arms) if arms is not None else D.ARMS
    task = DoorChainTask(door)
    record = task.prompts_record(integrity=INTEGRITY, shared=False)
    return {
        "task": task.name,
        "carrier": "transmission_door",
        "door": door,
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "workspaces": workspace_hashes(door),
        "prompts_sha256": record["sha256"],
        "integrity": INTEGRITY,
        "note_sha256": N.digests(door, chosen),
        "note_paths": N.paths(door, chosen),
        "verifier": verifier_config(door),
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def prepare(directory: Path, *, door: str, chains: int = D.CHAINS, generations: int = D.GENERATIONS,
            arms=None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    if door not in D.DOORS:
        raise SystemExit(f"door must be A4 or A5, got {door!r}")
    task = DoorChainTask(door)
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    chosen = tuple(arms) if arms is not None else D.ARMS
    unknown = [arm for arm in chosen if arm not in D.ARMS]
    if unknown:
        raise SystemExit(f"unknown arms: {', '.join(unknown)}")
    config = model.load_config()
    chain_rows, schedule = D.design(chains=chains, generations=generations, arms=chosen)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chain_rows)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", task.prompts_record(integrity=INTEGRITY, shared=False))
    save(directory / "notes.json", N.record(door))
    save(directory / "protocol.json", {
        "study": "transmission_door",
        "door": door,
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(chosen),
        "chains": chains,
        "generations": generations,
        "problems": [D.assign_problem(i) for i in range(chains)],
        "assignment": D.assignment_record(chains),
        "design_seed": D.DESIGN_SEED,
        "predictions": D.PREDICTIONS,
        "falsifier": D.FALSIFIER,
        "container_prefix": "pzd" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(door, config, arms=chosen),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    door = protocol["door"]
    now_frozen = frozen(door, model.load_config(), arms=protocol.get("arms"))
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    door = protocol["door"]
    task = DoorChainTask(door)
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        files = extra_files(directory, row, door)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session(task, client, box, target, row, integrity=INTEGRITY, shared=False,
                          opening=[], extra_files=files)
        step = D.barrier_action(row["arm"], row["generation"])
        save(target / "meta" / "delivered.json", {
            "arm": row["arm"],
            "door": door,
            "generation": row["generation"],
            "files": _text_files(files),
            "shared_sha256": shared_digest(files),
            "barrier_action": step,
        })
        save(target / "meta" / "verifier.json", verifier_config(door))
        return end

    async def generation(rows: list[dict], g: int) -> list[dict]:
        sem = asyncio.Semaphore(CONCURRENCY)
        done: list[dict] = []

        async def go(row):
            async with sem:
                try:
                    end = await asyncio.to_thread(one, row)
                except Exception as exc:
                    end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
                done.append(end)
                status(directory, state="running", generation=g, finished=len(done), of=len(rows), last=row["actor"])
                print(row["actor"], "normal" if end.get("normal") else end.get("error"), flush=True)
                return end

        return await asyncio.gather(*(go(row) for row in rows))

    for g, rows in enumerate(D.by_generation(schedule), start=1):
        ends = asyncio.run(generation(rows, g))
        failed = [end["actor"] for end in ends if not end.get("normal")]
        if failed:
            status(directory, state="stopped", generation=g, failed=failed)
            raise SystemExit(f"generation {g} has abnormal sessions: {', '.join(failed)}. Inspect them, then use retry.")
        print(f"generation {g} barrier", flush=True)
    status(directory, state="complete")


def retry(directory: Path, actors: list[str]) -> None:
    schedule = {row["actor"]: row for row in read(directory / "schedule.json")}
    log = read(directory / "retries.json") if (directory / "retries.json").exists() else []
    for actor in actors:
        if actor not in schedule:
            raise SystemExit(f"{actor} is not in the schedule")
        row = schedule[actor]
        target = session_dir(directory, actor)
        end = read(target / "end.json") if (target / "end.json").exists() else None
        if end and end.get("normal"):
            raise SystemExit(f"{actor} ended normally and is not retried")
        later = session_dir(directory, f"{row['chain']}-g{row['generation'] + 1:02d}")
        if later.exists():
            raise SystemExit(f"{actor} already has a successor")
        log.append({"actor": actor, "at": now(), "error": end.get("error") if end else None})
        if target.exists():
            shutil.rmtree(target)
    save(directory / "retries.json", log)


def audit(directory: Path) -> dict:
    """Audit every verifier-accepted file. The result never reaches a participant."""
    door = read(directory / "protocol.json")["door"]
    task = DoorChainTask(door)
    jobs = []
    for end_path in sorted((directory / "sessions").glob("*/end.json")):
        target = end_path.parent
        spec = read(target / "meta" / "spec.json")
        for item in read(target / "meta" / "submissions.json"):
            if item["accepted"] and not (target / "meta" / "audit" / f"t{item['turn']:02d}.json").exists():
                jobs.append((target, spec["problem"], item))

    def one(job):
        target, problem, item = job
        raw = (target / "meta" / "submissions" / f"t{item['turn']:02d}.py").read_bytes()
        result = A.audit_bytes(
            task.image, raw, problem,
            target / "meta" / "audit" / f"t{item['turn']:02d}",
            item.get("extras") or [],
        )
        save(target / "meta" / "audit" / f"t{item['turn']:02d}.json", result)
        print(target.name, item["turn"], result["reason"], flush=True)
        return result

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    return {"audited": len(results), "errors": sum(item["violation"] is None for item in results)}
