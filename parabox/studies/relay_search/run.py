"""Prepare and run a search relay directory.

Every arm gets the same tool and the same text; only the starting index differs. The index
is delivered through the board channel: isolated gets the frozen corpus alone, static adds
the seed, dynamic adds the seed and the chain's earlier accepted files. A session reads the
index only by calling search. This phase has no write tool.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, image_exists
from parabox.runner.session import run_session
from parabox.studies.relay.run import (
    CONCURRENCY, LIMITS, SEED_SHA, audit, code_commit, image_id, load_seed, retry, session_dir,
)
from parabox.studies.relay_search import design as D
from parabox.studies.relay_search.corpus import CORPUS_SHA, load_corpus
from parabox.tasks.lean import task as LT
from parabox.tasks.lean.board import make_record
from parabox.tasks.lean.search import SearchLeanTask
from parabox.util import digest_json, now, read, save

__all__ = ["prepare", "run", "retry", "audit", "index_for", "check_frozen", "session_dir"]

SEED_TITLE = "Seed recipe"


def frozen(task: SearchLeanTask, integrity: str, config: dict) -> dict:
    return {
        "task": task.name,
        "carrier": "search",
        "image": task.image,
        "image_id": image_id(task.image),
        "formal_commit": LT.FORMAL_COMMIT,
        "lean_toolchain": LT.LEAN_TOOLCHAIN,
        "mathlib": LT.MATHLIB_REV,
        "problems": LT.problem_hashes(),
        "integrity": integrity,
        "prompts": {"search": task.prompts_record(integrity=integrity, shared=True)["sha256"]},
        "seed_sha256": SEED_SHA,
        "corpus_sha256": CORPUS_SHA,
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": LT.TURNS,
        "max_submits": LT.MAX_SUBMITS,
        "compile_timeout_s": LT.COMPILE_TIMEOUT_S,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def corpus_records() -> list[dict]:
    records, seq = [], 0
    for entry in load_corpus():
        seq += 1
        records.append(make_record(seq, "corpus", 0, entry["title"], entry["body"], author="corpus", turn=0))
    return records


def index_for(directory: Path, row: dict, seed: str) -> list[dict]:
    """isolated: corpus alone. static: corpus and the seed. dynamic: plus the chain's earlier files."""
    records = corpus_records()
    if row["arm"] == "isolated":
        return records
    records.append(make_record(len(records) + 1, "seed", 0, SEED_TITLE, seed, author="seed", turn=0))
    if row["arm"] == "static":
        return records
    for g in range(1, row["generation"]):
        path = session_dir(directory, f"{row['chain']}-g{g:02d}") / "meta" / "contribution.json"
        if not path.exists():
            raise RuntimeError(f"{row['chain']} generation {g} has no contribution record")
        records += read(path)
    return records


def prepare(directory: Path, *, blocks: int, generations: int, integrity: str) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = SearchLeanTask()
    load_seed()
    load_corpus()
    config = model.load_config()
    chains, schedule = D.design(LT.POOL, blocks=blocks, generations=generations)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chains)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", {"search": task.prompts_record(integrity=integrity, shared=True)})
    save(directory / "protocol.json", {
        "study": "relay_search",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(D.ARMS),
        "blocks": blocks,
        "generations": generations,
        "design_seed": D.DESIGN_SEED,
        "pool": LT.POOL,
        "container_prefix": "pbs" + digest_json(str(directory.resolve()))[:6],
        "frozen": frozen(task, integrity, config),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    load_seed()
    load_corpus()
    now_frozen = frozen(SearchLeanTask(), protocol["frozen"]["integrity"], model.load_config())
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = SearchLeanTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    seed = load_seed()
    client = model.Client()
    integrity = protocol["frozen"]["integrity"]
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        index = index_for(directory, row, seed)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        return run_session(task, client, box, target, row, integrity=integrity,
                           shared=True, opening=[], board=index)

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
