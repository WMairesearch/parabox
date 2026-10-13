"""Prepare, run, and audit a write-elicitation directory.

Every session is independent, so there is no generation barrier: all sessions run in one
concurrency pool. The instrument is the discovery task (no integrity text, list_dir, emergent);
the only thing that varies across arms is the single file planted in shared/. run refuses to
start if the prompt, problems, planted files, image, or model configuration no longer match the
frozen protocol.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, image_exists
from parabox.studies.relay.run import (
    CONCURRENCY, LIMITS, audit, code_commit, image_id, session_dir,
)
from parabox.studies.write import design as D
from parabox.studies.write import notes as N
from parabox.tasks.lean import task as LT
from parabox.tasks.lean.discovery import DiscoveryLeanTask
from parabox.util import digest_json, now, read, save, sha256

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir"]


def frozen(task: DiscoveryLeanTask, config: dict) -> dict:
    return {
        "task": task.name,
        "carrier": "write",
        "image": task.image,
        "image_id": image_id(task.image),
        "formal_commit": LT.FORMAL_COMMIT,
        "lean_toolchain": LT.LEAN_TOOLCHAIN,
        "mathlib": LT.MATHLIB_REV,
        "problems": LT.problem_hashes(),
        "integrity": "none",
        "prompts": {"discovery": task.prompts_record(integrity="none", shared=False)["sha256"]},
        "note_sha256": N.digests(),
        "note_paths": N.paths(),
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": LT.TURNS,
        "max_submits": LT.MAX_SUBMITS,
        "compile_timeout_s": LT.COMPILE_TIMEOUT_S,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def extra_files(arm: str) -> dict[str, bytes]:
    path, content = N.planted(arm)
    return {path: content.encode()}


def prepare(directory: Path, *, problems: list[str] | None, replicates: int) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = DiscoveryLeanTask()
    config = model.load_config()
    problems = problems or D.DEFAULT_PROBLEMS
    unknown = [p for p in problems if p not in LT.POOL]
    if unknown:
        raise SystemExit(f"problems not in the impossible pool: {', '.join(unknown)}")
    schedule = D.design(problems, replicates)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", {"discovery": task.prompts_record(integrity="none", shared=False)})
    save(directory / "notes.json", {arm: {"path": p, "content": c} for arm, (p, c) in N.NOTES.items()})
    save(directory / "protocol.json", {
        "study": "write",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(D.ARMS),
        "problems": problems,
        "replicates": replicates,
        "design_seed": D.DESIGN_SEED,
        "container_prefix": "pbw" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(task, config),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    now_frozen = frozen(DiscoveryLeanTask(), model.load_config())
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = DiscoveryLeanTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session_write(task, client, box, target, row)
        path, content = N.planted(row["arm"])
        save(target / "meta" / "delivered.json", {"arm": row["arm"], "files": {path: content}})
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


def run_session_write(task, client, box, target, row):
    from parabox.session import run_session
    return run_session(task, client, box, target, row, integrity="none", shared=False,
                       opening=[], extra_files=extra_files(row["arm"]))


def retry(directory: Path, actors: list[str]) -> None:
    schedule = {row["actor"]: row for row in read(directory / "schedule.json")}
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
