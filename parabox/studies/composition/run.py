"""Prepare, run, retry, and audit a composition directory.

Single generation. Each session is independent. Generation-1 shared/ is the
planted arm files for that problem. status.json is rewritten as sessions finish.
"""
from __future__ import annotations

import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.runner.session import run_session
from parabox.studies.composition import design as D
from parabox.studies.composition import notes as N
from parabox.studies.composition.task import VERIFIER, CompositionTask
from parabox.studies.relay.run import CONCURRENCY, code_commit, image_id, session_dir
from parabox.studies.transmission.run import shared_digest
from parabox.tasks.base import run_audit_session
from parabox.tasks.code.spec.problems import problem_hashes
from parabox.tasks.code.task import MAX_SUBMITS, TURNS
from parabox.util import digest_json, now, read, save, sha256

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir",
           "load_plan", "extra_files", "CONCURRENCY"]

LIMITS = Limits(cpus="2", memory="2g")
INTEGRITY = "plain"


def extra_files(row: dict) -> dict[str, bytes]:
    return dict(N.seed_files(row["arm"], row["problem"]))


def _text_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: data.decode("utf-8", "replace") for name, data in files.items()}


def load_plan(directory: Path) -> list[dict]:
    raw = read(directory / "plan.json")
    if isinstance(raw, dict):
        return raw["actors"]
    return raw


def frozen(task: CompositionTask, config: dict, *, arms=None) -> dict:
    chosen = tuple(arms) if arms is not None else D.ARMS
    record = task.prompts_record(integrity=INTEGRITY, shared=False)
    return {
        "task": task.name,
        "carrier": "composition",
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "prompts_sha256": record["sha256"],
        "integrity": INTEGRITY,
        "verifier": VERIFIER,
        "note_sha256": {
            "control": N.CONTROL_SHA256,
            "R": N.RECIPE_SHA256,
            "sources": {problem: [dict(item) for item in N.SOURCES[problem]] for problem in D.PROBLEMS},
        },
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def prepare(directory: Path, *, arms=None, reps: int = D.REPS, seed: int | None = None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = CompositionTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    chosen = tuple(arms) if arms is not None else D.ARMS
    unknown = [arm for arm in chosen if arm not in D.ARMS]
    if unknown:
        raise SystemExit(f"unknown arms: {', '.join(unknown)}")
    seed = D.DESIGN_SEED if seed is None else seed
    config = model.load_config()
    actors = D.design(arms=chosen, reps=reps, seed=seed)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "plan.json", {"design_seed": seed, "actors": actors})
    save(directory / "prompts.json", task.prompts_record(integrity=INTEGRITY, shared=False))
    save(directory / "notes.json", N.record())
    save(directory / "protocol.json", {
        "study": "composition",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(chosen),
        "problems": list(D.PROBLEMS),
        "replicates": reps,
        "design_seed": seed,
        "verifier": VERIFIER,
        "predictions": D.PREDICTIONS,
        "container_prefix": "pbc" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(task, config, arms=chosen),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    now_frozen = frozen(CompositionTask(), model.load_config(), arms=protocol.get("arms"))
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = CompositionTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    schedule = load_plan(directory)

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        files = extra_files(row)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session(task, client, box, target, row, integrity=INTEGRITY, shared=False,
                          opening=[], extra_files=files)
        save(target / "meta" / "delivered.json", {
            "arm": row["arm"],
            "problem": row["problem"],
            "files": _text_files(files),
            "shared_sha256": shared_digest(files),
            "planted": row["planted"],
            "verifier": VERIFIER,
        })
        return end

    async def go_all(rows: list[dict]) -> list[dict]:
        sem = asyncio.Semaphore(CONCURRENCY)
        done: list[dict] = []

        async def go(row):
            async with sem:
                try:
                    end = await asyncio.to_thread(one, row)
                except Exception as exc:
                    end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
                done.append(end)
                status(directory, state="running", finished=len(done), of=len(rows), last=row["actor"])
                print(row["actor"], "normal" if end.get("normal") else end.get("error"), flush=True)
                return end

        return await asyncio.gather(*(go(row) for row in rows))

    ends = asyncio.run(go_all(schedule))
    failed = [end["actor"] for end in ends if not end.get("normal")]
    if failed:
        status(directory, state="stopped", failed=failed)
        raise SystemExit(f"abnormal sessions: {', '.join(failed)}. Inspect them, then use retry.")
    status(directory, state="complete")


def retry(directory: Path, actors: list[str]) -> None:
    schedule = {row["actor"]: row for row in load_plan(directory)}
    log = read(directory / "retries.json") if (directory / "retries.json").exists() else []
    for actor in actors:
        if actor not in schedule:
            raise SystemExit(f"{actor} is not in the schedule")
        target = session_dir(directory, actor)
        end = read(target / "end.json") if (target / "end.json").exists() else None
        if end and end.get("normal"):
            raise SystemExit(f"{actor} ended normally and is not retried")
        log.append({"actor": actor, "at": now(), "error": end.get("error") if end else None})
        if target.exists():
            shutil.rmtree(target)
    save(directory / "retries.json", log)


def audit(directory: Path) -> dict:
    task = CompositionTask()
    jobs = []
    for end_path in sorted((directory / "sessions").glob("*/end.json")):
        if not (end_path.parent / "meta" / "audit" / "session.json").exists():
            jobs.append(end_path.parent)

    def one(target: Path) -> dict:
        spec = read(target / "meta" / "spec.json")
        result = run_audit_session(task, target, spec, target / "meta" / "audit" / "scratch")
        save(target / "meta" / "audit" / "session.json", result)
        print(target.name, result["reason"], flush=True)
        return result

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    return {"audited": len(results), "errors": sum(item["reason"] == "error" for item in results)}
