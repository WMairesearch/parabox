"""Prepare, run, and audit a population-chain directory.

A generation of a chain starts only after every agent of the previous generation
has ended normally. All K agents of a generation receive a byte-identical copy
of the merged record. After the barrier, writes are merged under the arm rule.
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.runner.session import run_session
from parabox.studies.relay.run import CONCURRENCY, code_commit, image_id, session_dir
from parabox.studies.population import design as D
from parabox.studies.population.merge import final_accepted, merge_record, snapshot_shared
from parabox.studies.transmission import notes as N
from parabox.studies.transmission.run import shared_digest
from parabox.studies.transmission.task import TransmissionCodeTask
from parabox.tasks.base import run_audit_session
from parabox.tasks.code.spec.problems import problem_hashes
from parabox.tasks.code.task import MAX_SUBMITS, TURNS
from parabox.util import digest_json, now, read, save, sha256

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir",
           "extra_files", "write_record", "record_snapshot", "merge_generation"]

LIMITS = Limits(cpus="2", memory="2g")
INTEGRITY = "plain"


def record_dir(directory: Path, chain: str, generation: int) -> Path:
    return directory / "records" / f"{chain}-g{generation:02d}"


def merge_path(directory: Path, chain: str, generation: int) -> Path:
    return directory / "merges" / f"{chain}-g{generation:02d}.json"


def record_snapshot(directory: Path, chain: str, generation: int) -> dict[str, bytes]:
    folder = record_dir(directory, chain, generation)
    out = {}
    if not folder.exists():
        return out
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(folder)).replace("\\", "/")
        out[rel] = path.read_bytes()
    return out


def write_record(directory: Path, chain: str, generation: int, files: dict[str, bytes]) -> None:
    dest = record_dir(directory, chain, generation)
    if dest.exists():
        shutil.rmtree(dest)
    for name, data in files.items():
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def seed_files() -> dict[str, bytes]:
    return dict(N.seed_files("control"))


def extra_files(directory: Path, row: dict) -> dict[str, bytes]:
    if row["generation"] == 1:
        return seed_files()
    prev = record_dir(directory, row["chain"], row["generation"] - 1)
    if not prev.exists():
        raise RuntimeError(f"{row['chain']} generation {row['generation'] - 1} has no merged record")
    files = record_snapshot(directory, row["chain"], row["generation"] - 1)
    if not files and not any(prev.iterdir()):
        return {}
    return files


def _text_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: data.decode("utf-8", "replace") for name, data in files.items()}


def frozen(task: TransmissionCodeTask, config: dict, *, arms=None, agents: int = D.AGENTS) -> dict:
    chosen = tuple(arms) if arms is not None else D.ARMS
    record = task.prompts_record(integrity=INTEGRITY, shared=False)
    return {
        "task": task.name,
        "carrier": "population",
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "prompts_sha256": record["sha256"],
        "integrity": INTEGRITY,
        "note_sha256": {"control": sha256(N.CONTROL)},
        "note_paths": {"control": N.CONTROL_PATH},
        "agents": agents,
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }


def prepare(directory: Path, *, chains: int = D.CHAINS, generations: int = D.GENERATIONS,
            agents: int = D.AGENTS, arms=None, predictions=None,
            concurrency_per_arm: int | None = None, hard_stop: str | None = None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = TransmissionCodeTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    chosen = tuple(arms) if arms is not None else D.ARMS
    config = model.load_config()
    chain_rows, schedule = D.design(chains=chains, generations=generations, agents=agents, arms=chosen)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chain_rows)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", task.prompts_record(integrity=INTEGRITY, shared=False))
    save(directory / "notes.json", {
        "control": {"path": N.CONTROL_PATH, "content": N.CONTROL, "sha256": sha256(N.CONTROL)},
    })
    save(directory / "protocol.json", {
        "study": "population",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(chosen),
        "chains": chains,
        "generations": generations,
        "agents": agents,
        "problems": [D.assign_problem(i) for i in range(chains)],
        "assignment": D.assignment_record(chains=chains, generations=generations, agents=agents, arms=chosen),
        "design_seed": D.DESIGN_SEED,
        "predictions": predictions if predictions is not None else D.PREDICTIONS,
        "concurrency_per_arm": concurrency_per_arm,
        "hard_stop": hard_stop,
        "container_prefix": "pbp" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(task, config, arms=chosen, agents=agents),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    now_frozen = frozen(
        TransmissionCodeTask(), model.load_config(),
        arms=protocol.get("arms"), agents=protocol.get("agents", D.AGENTS),
    )
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def merge_generation(directory: Path, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("no rows to merge")
    chain = rows[0]["chain"]
    arm = rows[0]["arm"]
    generation = rows[0]["generation"]
    received = extra_files(directory, rows[0])
    agents = []
    for row in rows:
        target = session_dir(directory, row["actor"])
        submissions = []
        sub_path = target / "meta" / "submissions.json"
        if sub_path.exists():
            submissions = read(sub_path)
        agents.append({
            "agent": row["agent"],
            "actor": row["actor"],
            "accepted": final_accepted(submissions),
            "received": received,
            "written": snapshot_shared(target),
        })
    record, meta = merge_record(received, agents, arm)
    meta.update({
        "chain": chain,
        "generation": generation,
        "shared_sha256": shared_digest(record),
        "n_received": len(received),
    })
    write_record(directory, chain, generation, record)
    save(merge_path(directory, chain, generation), meta)
    return meta


def extend(directory: Path, *, generations: int, arms: list[str]) -> list[dict]:
    """Append later generations on existing chains. Does not rewrite finished sessions or merges."""
    protocol = read(directory / "protocol.json")
    if protocol.get("study") != "population":
        raise SystemExit("not a population directory")
    schedule = read(directory / "schedule.json")
    have = {(row["actor"]) for row in schedule}
    _, planned = D.design(
        chains=protocol["chains"], generations=generations, agents=protocol["agents"],
        arms=protocol.get("arms"),
    )
    added = [row for row in planned if row["arm"] in arms and row["actor"] not in have
             and row["generation"] > protocol["generations"]]
    if not added:
        raise SystemExit("no new sessions to append")
    schedule.extend(added)
    save(directory / "schedule.json", schedule)
    note = {
        "appended_at": now(),
        "arms": list(arms),
        "generations": generations,
        "original_generations": protocol["generations"],
        "added": [row["actor"] for row in added],
        "note": "extension; finished gens 1-6 sessions and merges are not rewritten",
    }
    save(directory / "extension.json", note)
    if (directory / "status.json").exists():
        status(directory, state="extend", added=len(added), generations=generations, arms=list(arms))
    return added


def _deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def past_deadline(raw: str | None) -> bool:
    cut = _deadline(raw)
    return cut is not None and datetime.now(timezone.utc) >= cut


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    schedule = read(directory / "schedule.json")
    pending = [row for row in schedule if not (session_dir(directory, row["actor"]) / "end.json").exists()]
    if (directory / "status.json").exists():
        current = read(directory / "status.json")
        if current.get("state") == "complete" and not pending:
            print(f"{directory} is already complete", flush=True)
            return
    task = TransmissionCodeTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    per_arm = protocol.get("concurrency_per_arm") or CONCURRENCY
    hard_stop = protocol.get("hard_stop")

    def client_for(row: dict):
        path = row.get("model")
        if not path:
            return client
        from pathlib import Path as _Path
        return model.Client(model.load_config(_Path(path)))

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        files = extra_files(directory, row)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session(task, client_for(row), box, target, row, integrity=INTEGRITY, shared=False,
                          opening=[], extra_files=files)
        save(target / "meta" / "delivered.json", {
            "arm": row["arm"],
            "generation": row["generation"],
            "agent": row["agent"],
            "chain": row["chain"],
            "files": _text_files(files),
            "shared_sha256": shared_digest(files),
        })
        return end

    async def run_rows(rows: list[dict], g: int, arm: str, sem: asyncio.Semaphore) -> list[dict]:
        done: list[dict] = []

        async def go(row):
            async with sem:
                try:
                    end = await asyncio.to_thread(one, row)
                except Exception as exc:
                    end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
                done.append(end)
                status(directory, state="running", generation=g, arm=arm,
                       finished=len(done), of=len(rows), last=row["actor"])
                print(row["actor"], "normal" if end.get("normal") else end.get("error"), flush=True)
                return end

        return await asyncio.gather(*(go(row) for row in rows))

    def finish_generation(rows: list[dict], g: int, ends: list[dict]) -> None:
        failed = [end.get("actor", "?") for end in ends if not end.get("normal")]
        if failed:
            status(directory, state="stopped", generation=g, failed=failed)
            raise SystemExit(f"generation {g} has abnormal sessions: {', '.join(failed)}. Inspect them, then use retry.")
        for chain in D.chains_in(rows):
            if merge_path(directory, chain, g).exists():
                print(f"{chain} g{g:02d} merge already on disk", flush=True)
                continue
            merge_generation(directory, [row for row in rows if row["chain"] == chain])
        print(f"generation {g} {rows[0]['arm']} barrier", flush=True)

    stopped = {"hard": False}

    async def run_arm(arm: str) -> None:
        sem = asyncio.Semaphore(per_arm)
        arm_rows = [row for row in schedule if row["arm"] == arm]
        for g, rows in enumerate(D.by_generation(arm_rows), start=1):
            if past_deadline(hard_stop):
                stopped["hard"] = True
                status(directory, state="hard_stop", arm=arm, stopped_before_generation=g)
                print(f"hard stop before {arm} generation {g}", flush=True)
                return
            need = [row for row in rows if not (session_dir(directory, row["actor"]) / "end.json").exists()]
            if need:
                ends = await run_rows(rows, g, arm, sem)
            else:
                ends = [read(session_dir(directory, row["actor"]) / "end.json") for row in rows]
            finish_generation(rows, g, ends)

    async def main():
        arms = list(dict.fromkeys(row["arm"] for row in schedule))
        if protocol.get("concurrency_per_arm"):
            await asyncio.gather(*(run_arm(arm) for arm in arms))
        else:
            sem = asyncio.Semaphore(CONCURRENCY)
            for g, rows in enumerate(D.by_generation(schedule), start=1):
                if past_deadline(hard_stop):
                    stopped["hard"] = True
                    status(directory, state="hard_stop", stopped_before_generation=g)
                    print(f"hard stop before generation {g}", flush=True)
                    return
                need = [row for row in rows if not (session_dir(directory, row["actor"]) / "end.json").exists()]
                if need:
                    ends = await run_rows(rows, g, "all-arms", sem)
                else:
                    ends = [read(session_dir(directory, row["actor"]) / "end.json") for row in rows]
                finish_generation(rows, g, ends)

    asyncio.run(main())
    if stopped["hard"]:
        status(directory, state="hard_stop")
        return
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
        later = list((directory / "sessions").glob(f"{row['chain']}-g{row['generation'] + 1:02d}-a*"))
        if later:
            raise SystemExit(f"{actor} already has a successor")
        log.append({"actor": actor, "at": now(), "error": end.get("error") if end else None})
        if target.exists():
            shutil.rmtree(target)
        merged = merge_path(directory, row["chain"], row["generation"])
        if merged.exists():
            merged.unlink()
        rec = record_dir(directory, row["chain"], row["generation"])
        if rec.exists():
            shutil.rmtree(rec)
    save(directory / "retries.json", log)
    if (directory / "status.json").exists():
        current = read(directory / "status.json")
        current["state"] = "retry"
        save(directory / "status.json", current)


def audit(directory: Path) -> dict:
    task = TransmissionCodeTask()
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

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    return {"audited": len(results), "errors": sum(item["reason"] == "error" for item in results)}
