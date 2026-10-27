"""Prepare, run, and audit a transmission directory.

A generation starts only after every session of the previous generation has ended
normally. Generation 1 is seeded with the planted arm file. Later generations of
the same chain receive a byte-identical copy of the previous session's shared/.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.runner.session import run_session
from parabox.studies.relay.run import CONCURRENCY, code_commit, image_id, session_dir
from parabox.studies.composition.task import VERIFIER as HYGIENIC_VERIFIER, CompositionTask
from parabox.studies.transmission import design as D
from parabox.studies.transmission import notes as N
from parabox.studies.transmission.task import VERIFIER as DEFAULT_VERIFIER, TransmissionCodeTask
from parabox.tasks.base import run_audit_session
from parabox.tasks.code.spec.problems import problem_hashes
from parabox.tasks.code.task import MAX_SUBMITS, TURNS
from parabox.util import digest_json, now, read, save, sha256
from parabox.workspace import snapshot_regular

__all__ = ["prepare", "run", "retry", "audit", "check_frozen", "session_dir",
           "extra_files", "shared_snapshot", "shared_digest", "apply_barrier",
           "DEFAULT_VERIFIER", "HYGIENIC_VERIFIER", "verifier_tag", "make_task",
           "task_for", "protocol_verifier", "session_spec"]

LIMITS = Limits(cpus="2", memory="2g")
INTEGRITY = "plain"


def verifier_tag(kind: str | None) -> str:
    if kind in (None, DEFAULT_VERIFIER):
        return DEFAULT_VERIFIER
    if kind in ("hygienic", HYGIENIC_VERIFIER):
        return HYGIENIC_VERIFIER
    raise SystemExit(f"unknown verifier {kind!r}")


def make_task(verifier: str | None) -> TransmissionCodeTask:
    tag = verifier_tag(verifier)
    if tag == HYGIENIC_VERIFIER:
        return CompositionTask()
    return TransmissionCodeTask()


def protocol_verifier(protocol: dict) -> str:
    return protocol.get("verifier") or protocol.get("frozen", {}).get("verifier") or DEFAULT_VERIFIER


def task_for(protocol: dict) -> TransmissionCodeTask:
    return make_task(protocol_verifier(protocol))


def session_spec(row: dict, verifier: str | None) -> dict:
    if not verifier:
        return dict(row)
    return {**row, "verifier": verifier}


def shared_snapshot(target: Path) -> dict[str, bytes]:
    shared = target / "workspace" / "shared"
    return {"shared/" + relative: content for relative, content in snapshot_regular(shared).items()}


def shared_digest(files: dict[str, bytes]) -> str:
    return digest_json({name: sha256(data) for name, data in sorted(files.items())})


def apply_barrier(files: dict[str, bytes], row: dict) -> dict[str, bytes]:
    step = D.barrier_action(row["arm"], row["generation"])
    if step is None:
        return files
    if step["action"] == "wipe":
        return {}
    if step["action"] == "inject":
        out = dict(files)
        out[step["path"]] = N.CONDEMN.encode()
        return out
    raise ValueError(f"unknown barrier action {step['action']!r}")


def extra_files(directory: Path, row: dict) -> dict[str, bytes]:
    if row["generation"] == 1:
        files = dict(N.seed_files(row["arm"]))
    else:
        prev = session_dir(directory, f"{row['chain']}-g{row['generation'] - 1:02d}")
        if not (prev / "end.json").exists():
            raise RuntimeError(f"{row['chain']} generation {row['generation'] - 1} has no end record")
        files = shared_snapshot(prev)
    return apply_barrier(files, row)


def _text_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: data.decode("utf-8", "replace") for name, data in files.items()}


def frozen(task: TransmissionCodeTask, config: dict, *, arms=None, verifier=None) -> dict:
    chosen = tuple(arms) if arms is not None else D.ARMS
    record = task.prompts_record(integrity=INTEGRITY, shared=False)
    out = {
        "task": task.name,
        "carrier": "transmission",
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "prompts_sha256": record["sha256"],
        "integrity": INTEGRITY,
        "note_sha256": N.digests(chosen),
        "note_paths": N.paths(chosen),
        "interventions": D.intervention_record(chosen),
        "condemn_sha256": N.CONDEMN_SHA256,
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
    }
    if verifier is not None and verifier != DEFAULT_VERIFIER:
        out["verifier"] = verifier
    return out


def prepare(directory: Path, *, chains: int = D.CHAINS, generations: int = D.GENERATIONS,
            arms=None, verifier=None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    tag = verifier_tag(verifier)
    task = make_task(tag)
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    chosen = tuple(arms) if arms is not None else D.ARMS
    config = model.load_config()
    chain_rows, schedule = D.design(chains=chains, generations=generations, arms=chosen)
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "chains.json", chain_rows)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", task.prompts_record(integrity=INTEGRITY, shared=False))
    all_notes = {**N.NOTES, **N.INTERVENTION_NOTES}
    notes = {arm: {"path": p, "content": c} for arm, (p, c) in all_notes.items() if arm in chosen}
    if any(D.barrier_action(arm, 3) and D.barrier_action(arm, 3)["action"] == "inject"
           for arm in chosen):
        notes["condemn"] = {
            "path": N.CONDEMN_PATH,
            "content": N.CONDEMN,
            "source_session": N.CONDEMN_SOURCE_SESSION,
            "source_run": N.CONDEMN_SOURCE_RUN,
            "sha256": N.CONDEMN_SHA256,
        }
    save(directory / "notes.json", notes)
    frozen_tag = tag if tag != DEFAULT_VERIFIER else None
    save(directory / "protocol.json", {
        "study": "transmission",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "arms": list(chosen),
        "chains": chains,
        "generations": generations,
        "problems": [D.assign_problem(i) for i in range(chains)],
        "assignment": D.assignment_record(chains),
        "design_seed": D.DESIGN_SEED,
        "predictions": D.predictions_for(chosen, chains, generations),
        "interventions": D.intervention_record(chosen),
        "container_prefix": "pbt" + sha256(str(directory.resolve()))[:6],
        "verifier": tag,
        "frozen": frozen(task, config, arms=chosen, verifier=frozen_tag),
    })


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = task_for(protocol)
    tag = protocol_verifier(protocol)
    frozen_tag = tag if tag != DEFAULT_VERIFIER else None
    now_frozen = frozen(task, model.load_config(), arms=protocol.get("arms"), verifier=frozen_tag)
    changed = [key for key in now_frozen if now_frozen[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def run(directory: Path) -> None:
    protocol = check_frozen(directory)
    task = task_for(protocol)
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    client = model.Client()
    prefix = protocol["container_prefix"]
    schedule = read(directory / "schedule.json")
    tag = protocol.get("verifier")

    def one(row: dict) -> dict:
        target = session_dir(directory, row["actor"])
        files = extra_files(directory, row)
        box = Box(f"{prefix}-{row['actor']}", target / "workspace", task.image, LIMITS)
        end = run_session(task, client, box, target, session_spec(row, tag),
                          integrity=INTEGRITY, shared=False, opening=[], extra_files=files)
        step = D.barrier_action(row["arm"], row["generation"])
        save(target / "meta" / "delivered.json", {
            "arm": row["arm"],
            "generation": row["generation"],
            "files": _text_files(files),
            "shared_sha256": shared_digest(files),
            "barrier_action": step,
        })
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
    task_for(read(directory / "protocol.json"))
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
    task = task_for(read(directory / "protocol.json"))
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
