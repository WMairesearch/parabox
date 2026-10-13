"""Prepare, run, and audit a code-domain mechanism-span directory.

Every session is independent. The only thing that varies across arms is the
verifier configuration and the workspace files that cell plants (oracle /
grade store / score file). run refuses to start if the prompt, problems,
verifier, image, or model configuration no longer match the frozen protocol.
"""
from __future__ import annotations

import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, image_exists
from parabox.studies.mechspan_code import design as D
from parabox.studies.relay.run import LIMITS, code_commit, image_id, session_dir
from parabox.tasks.code import audit as A
from parabox.tasks.code.mechspan import (
    ARMS, VALID_ARMS, MechspanCodeTask, verifier_config, workspace_files,
)
from parabox.tasks.code.problems import IMPOSSIBLE, problem_hashes
from parabox.tasks.code.task import MAX_SUBMITS, TURNS
from parabox.util import digest_json, now, read, save, sha256

CONCURRENCY = 4

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir", "CONCURRENCY"]


def workspace_hashes() -> dict[str, dict[str, str]]:
    return {
        arm: {name: sha256(b"".join(workspace_files(arm, name).values())) for name in IMPOSSIBLE}
        for arm in VALID_ARMS
    }


def frozen(config: dict) -> dict:
    prompts = {}
    for arm in VALID_ARMS:
        prompts[arm] = MechspanCodeTask(arm).prompts_record(integrity="none", shared=False)["sha256"]
    task = MechspanCodeTask("A2")
    return {
        "task": task.name,
        "carrier": "mechspan_code",
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "workspaces": workspace_hashes(),
        "integrity": "none",
        "prompts": prompts,
        "verifier": {arm: verifier_config(arm) for arm in VALID_ARMS},
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def prepare(directory: Path, *, problems: list[str] | None, replicates: int,
            arms: list[str] | None = None, seed: int | None = None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    config = model.load_config()
    problems = problems or D.DEFAULT_PROBLEMS
    unknown = [p for p in problems if p not in IMPOSSIBLE]
    if unknown:
        raise SystemExit(f"problems not in the impossible pool: {', '.join(unknown)}")
    chosen_arms = list(arms) if arms else list(ARMS)
    bad_arms = [arm for arm in chosen_arms if arm not in VALID_ARMS]
    if bad_arms:
        raise SystemExit(f"unknown arms: {', '.join(bad_arms)}")
    seed = D.DESIGN_SEED if seed is None else seed
    schedule = D.design(problems, replicates, seed=seed, arms=chosen_arms)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", {
        arm: MechspanCodeTask(arm).prompts_record(integrity="none", shared=False)
        for arm in chosen_arms
    })
    save(directory / "protocol.json", {
        "study": "mechspan_code",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": chosen_arms,
        "problems": problems,
        "replicates": replicates,
        "design_seed": seed,
        "container_prefix": "pmc" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(config),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    now_frozen = frozen(model.load_config())
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    if not image_exists(MechspanCodeTask.image):
        raise SystemExit(f"image {MechspanCodeTask.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")

    def one(row: dict) -> dict:
        task = MechspanCodeTask(row["arm"])
        target = session_dir(directory, row["actor"])
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session_mechspan(task, client, box, target, row)
        save(target / "meta" / "verifier.json", verifier_config(row["arm"]))
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


def run_session_mechspan(task, client, box, target, row):
    from parabox.session import run_session
    return run_session(task, client, box, target, row, integrity="none", shared=False,
                       opening=[], extra_files={})


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


def audit(directory: Path) -> dict:
    """Audit every verifier-accepted file. The result never reaches a participant."""
    task = MechspanCodeTask("A2")
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
