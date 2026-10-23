"""Prepare and run the files-only push relay.

The relay's design, seed, generation barrier, retry, and audit are reused. The one change
from the pushed-library relay is the library content: only verifier-accepted files are
carried, not the method notes. The isolated arm is byte-for-byte the relay isolated arm,
so its 60 sessions may be copied from an earlier relay directory with --isolated-from.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, image_exists
from parabox.runner.session import run_session
from parabox.studies.relay import design as D
from parabox.studies.relay import library as Lib
from parabox.studies.relay.run import (
    CONCURRENCY, LIMITS, SEED_SHA, audit, chain_entries, code_commit, image_id,
    load_seed, retry, session_dir,
)
from parabox.tasks.lean import task as LT
from parabox.tasks.lean.files import FilesLeanTask
from parabox.util import digest_json, now, read, save

__all__ = ["prepare", "run", "retry", "audit", "delivery", "check_frozen", "session_dir"]

CARRY_METHOD = False
ISOLATED_KEYS = ("task", "image", "image_id", "formal_commit", "lean_toolchain", "mathlib", "problems",
                 "integrity", "seed_sha256", "model", "turns", "max_submits", "compile_timeout_s", "container")


def frozen(task: FilesLeanTask, integrity: str, config: dict) -> dict:
    return {
        "task": task.name,
        "carrier": "library_files",
        "carry_method": CARRY_METHOD,
        "image": task.image,
        "image_id": image_id(task.image),
        "formal_commit": LT.FORMAL_COMMIT,
        "lean_toolchain": LT.LEAN_TOOLCHAIN,
        "mathlib": LT.MATHLIB_REV,
        "problems": LT.problem_hashes(),
        "integrity": integrity,
        "prompts": {
            "shared": task.prompts_record(integrity=integrity, shared=True)["sha256"],
            "isolated": task.prompts_record(integrity=integrity, shared=False)["sha256"],
        },
        "seed_sha256": SEED_SHA,
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": LT.TURNS,
        "max_submits": LT.MAX_SUBMITS,
        "compile_timeout_s": LT.COMPILE_TIMEOUT_S,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def isolated_rows(schedule: list[dict]) -> list[dict]:
    return [row for row in schedule if row["arm"] == "isolated"]


def check_isolated_source(source: Path, protocol: dict, schedule: list[dict]) -> list[str]:
    """Reasons the source's isolated arm cannot stand in for this directory's. Empty means it can."""
    theirs = read(source / "protocol.json")
    problems = [f"frozen {key} differs" for key in ISOLATED_KEYS
                if theirs["frozen"].get(key) != protocol["frozen"].get(key)]
    if theirs["frozen"]["prompts"]["isolated"] != protocol["frozen"]["prompts"]["isolated"]:
        problems.append("isolated prompts differ")
    for key in ("blocks", "generations", "design_seed", "pool"):
        if theirs.get(key) != protocol.get(key):
            problems.append(f"{key} differs")
    if isolated_rows(read(source / "schedule.json")) != isolated_rows(schedule):
        problems.append("isolated schedule differs")
    for row in isolated_rows(schedule):
        end = session_dir(source, row["actor"]) / "end.json"
        if not end.exists() or not read(end).get("normal"):
            problems.append(f"{row['actor']} did not end normally in the source")
    return problems


def prepare(directory: Path, *, blocks: int, generations: int, integrity: str,
            isolated_from: Path | None = None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = FilesLeanTask()
    load_seed()
    config = model.load_config()
    chains, schedule = D.design(LT.POOL, blocks=blocks, generations=generations)
    protocol = {
        "study": "relay_files",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(D.ARMS),
        "blocks": blocks,
        "generations": generations,
        "design_seed": D.DESIGN_SEED,
        "pool": LT.POOL,
        "container_prefix": "pbf" + digest_json(str(directory.resolve()))[:6],
        "frozen": frozen(task, integrity, config),
    }
    if isolated_from is not None:
        problems = check_isolated_source(isolated_from, protocol, schedule)
        if problems:
            raise SystemExit(f"cannot reuse the isolated arm of {isolated_from}: " + "; ".join(problems))
        protocol["isolated_from"] = {
            "directory": str(isolated_from.resolve()),
            "sessions": {row["actor"]: digest_json(read(session_dir(isolated_from, row["actor"]) / "end.json"))
                         for row in isolated_rows(schedule)},
        }
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chains)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", {
        "shared": task.prompts_record(integrity=integrity, shared=True),
        "isolated": task.prompts_record(integrity=integrity, shared=False),
    })
    save(directory / "protocol.json", protocol)
    if isolated_from is not None:
        for row in isolated_rows(schedule):
            shutil.copytree(session_dir(isolated_from, row["actor"]), session_dir(directory, row["actor"]))


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    load_seed()
    now_frozen = frozen(FilesLeanTask(), protocol["frozen"]["integrity"], model.load_config())
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def delivery(directory: Path, row: dict, seed: str) -> list[str]:
    entries = Lib.entries_before(row["arm"], row["generation"], chain_entries(directory, row["chain"], row["generation"]))
    return Lib.opening(row["arm"], seed, entries, CARRY_METHOD)


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = FilesLeanTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    seed = load_seed()
    client = model.Client()
    integrity = protocol["frozen"]["integrity"]
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        opening = delivery(directory, row, seed)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        return run_session(task, client, box, target, row, integrity=integrity,
                           shared=D.SHARED[row["arm"]], opening=opening)

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
