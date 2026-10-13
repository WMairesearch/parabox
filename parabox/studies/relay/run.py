"""Prepare, run, and audit a relay directory.

A generation starts only after every session of the previous generation has ended
normally. The protocol is written once by prepare; run refuses to start if the
prompts, seed, problems, image, or model configuration no longer match it.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.session import run_session
from parabox.studies.relay import design as D
from parabox.studies.relay import library as Lib
from parabox.tasks.lean import task as LT
from parabox.util import ROOT, digest_json, now, read, save, sha256

SEED_PATH = ROOT / "data" / "seeds" / "relay-initial-note.json"
SEED_SHA = "3809626de729232a7dfeb673c61106f43fd4d70d87189fb16411b9d52370321e"
CONCURRENCY = 4
LIMITS = Limits()


def load_seed() -> str:
    data = read(SEED_PATH)
    if sha256(data["body"]) != data["sha256"] or data["sha256"] != SEED_SHA:
        raise SystemExit("seed recipe hash does not match")
    return data["body"]


def image_id(image: str) -> str | None:
    proc = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True)
    return proc.stdout.strip() or None


def code_commit() -> dict:
    if shutil.which("git") is None:
        return {"head": None, "dirty": None, "available": False}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "parabox", "data", "configs"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    return {"head": head or None, "dirty": bool(dirty) if head else None, "available": bool(head)}


def frozen(task: LT.LeanTask, integrity: str, config: dict) -> dict:
    """Everything a participant's input depends on, apart from the design."""
    return {
        "task": task.name,
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


def prepare(directory: Path, *, blocks: int, generations: int, integrity: str) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = LT.LeanTask()
    load_seed()
    config = model.load_config()
    chains, schedule = D.design(LT.POOL, blocks=blocks, generations=generations)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chains)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", {
        "shared": task.prompts_record(integrity=integrity, shared=True),
        "isolated": task.prompts_record(integrity=integrity, shared=False),
    })
    save(directory / "protocol.json", {
        "study": "relay",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(D.ARMS),
        "blocks": blocks,
        "generations": generations,
        "design_seed": D.DESIGN_SEED,
        "pool": LT.POOL,
        "container_prefix": "pbx" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(task, integrity, config),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = LT.LeanTask()
    load_seed()
    now_frozen = frozen(task, protocol["frozen"]["integrity"], model.load_config())
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def session_dir(directory: Path, actor: str) -> Path:
    return directory / "sessions" / actor


def chain_entries(directory: Path, chain: str, generation: int) -> dict[int, list[dict]]:
    found = {}
    for g in range(1, generation):
        path = session_dir(directory, f"{chain}-g{g:02d}") / "meta" / "contribution.json"
        if not path.exists():
            raise RuntimeError(f"{chain} generation {g} has no contribution record")
        found[g] = [{**item, "generation": g} for item in read(path)]
    return found


def delivery(directory: Path, row: dict, seed: str) -> list[str]:
    entries = Lib.entries_before(row["arm"], row["generation"], chain_entries(directory, row["chain"], row["generation"]))
    return Lib.opening(row["arm"], seed, entries)


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = LT.LeanTask()
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


def retry(directory: Path, actors: list[str]) -> None:
    """Remove abnormal sessions so run starts them again. Only a generation with no successor may be retried."""
    schedule = {row["actor"]: row for row in read(directory / "schedule.json")}
    log = read(directory / "retries.json") if (directory / "retries.json").exists() else []
    for actor in actors:
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
    task = LT.LeanTask()
    jobs = []
    for end_path in sorted((directory / "sessions").glob("*/end.json")):
        target = end_path.parent
        spec = read(target / "meta" / "spec.json")
        for item in read(target / "meta" / "submissions.json"):
            if item["accepted"] and not (target / "meta" / "audit" / f"t{item['turn']:02d}.json").exists():
                jobs.append((target, spec["problem"], item["turn"]))

    def one(job):
        target, problem, turn = job
        raw = (target / "meta" / "submissions" / f"t{turn:02d}.lean").read_bytes()
        result = task.audit(raw, problem, target / "meta" / "audit" / f"t{turn:02d}")
        save(target / "meta" / "audit" / f"t{turn:02d}.json", result)
        print(target.name, turn, result["reason"], flush=True)
        return result

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    return {"audited": len(results), "errors": sum(item["violation"] is None for item in results)}
